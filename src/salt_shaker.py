import logging
import os
import sys
import re
import tempfile
import shutil
import stat
import errno

from git import Repo
from git.exc import GitCommandError
from textwrap import dedent
from fabric.api import local, task, env

import resolve_deps

SSH_WRAPPER_SCRIPT = """#!/bin/bash
ssh -o VisualHostKey=no "$@"
"""

class GitSshEnvWrapper(object):
    def __enter__(self):
        """
        Setup SSH to remove VisualHostKey - it breaks GitPython's attempt to
        parse git output :(

        Will delete file once the object gets GC'd
        """

        self.old_env_value = os.environ.get('GIT_SSH', None)

        self.git_ssh_wrapper = tempfile.NamedTemporaryFile(prefix='cotton-git-ssh')

        self.git_ssh_wrapper.write(SSH_WRAPPER_SCRIPT)
        self.git_ssh_wrapper.file.flush()
        os.fchmod(self.git_ssh_wrapper.file.fileno(), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.git_ssh_wrapper.file.close()

        os.environ['GIT_SSH'] = self.git_ssh_wrapper.name

    def __exit__(self, exc_type, exc_value, traceback):
        if self.old_env_value is not None:
            os.environ['GIT_SSH'] = self.old_env_value
        else:
            os.environ.pop('GIT_SSH')


class Shaker(object):
    """
    Recursively walk formula-requirements.txt and manully pull in those
    versions of the specified formulas.

    How it works
    ------------

    Salt Shaker works by creating an extra file root that must be copied up to
    your salt server and added to the master config.

    Setup
    ~~~~~

    **1. Define the vendor_formulas task**

    In your fabfile you will need to add a snippet like this to vendor the
    formulas just before you rsync them to the server::

        @task
        def vendor_formulas():
            from cotton.salt_shaker import Shaker
            shaker = Shaker(root_dir=os.path.dirname(env.real_fabfile))
            shaker.install_requirements()

    We recommend that you call this at the start of your rsync task too.

    **2. Rsync the managed root to the salt master **

    You will also need to ensure that you rsync the ``vendor/_root`` directory
    up to your salt master, with symlinks resolved, not copied as is::

        vendor_formulas()
        sudo('mkdir -p /srv/salt-formulas')
        smart_rsync_project('/srv/salt-formulas', 'vendor/_root/', for_user='root', extra_opts='-L', delete=True)

    Your complete rsync task will now look something like this::

        @task
        def rsync():
            vendor_formulas()

            sudo('mkdir -p /srv/salt /srv/salt-formulas /srv/pillar')

            smart_rsync_project('/srv/salt-formulas', 'vendor/_root/', for_user='root', extra_opts='-L', delete=True)
            smart_rsync_project('/srv/salt', 'salt/', for_user='root', extra_opts='-L', delete=True)
            smart_rsync_project('/srv/pillar', '{}/'.format(get_pillar_location()), for_user='root', extra_opts='-L', delete=True)


    **3. Add the extra root to the salt master config**

    You will need to add this new, managed root directory to the list of paths
    that the salt master searches for files under. We recommend adding it to
    the end so that any thing can be overridden by a matching file in
    ``salt/_libs`` if needed (but hopefully it shouldn't be).

    The bits of your `/etc/salt/master` config should look like this::

        file_roots:
          base:
            - /srv/salt
            - /srv/salt/_libs
            - /srv/salt-formulas

        fileserver_backend:
          - roots


    The formula-requirements.txt file
    ---------------------------------

    The format of the file is simply a list of git-cloneable urls with an
    optional revision specified on the end. At the moment the only form a
    version comparison accepted is `==`. The version can be a tag, a branch
    name or anything that ``git rev-parse`` understands (i.e. a plain sha or
    the output of ``git describe`` such as ``v0.2.2-1-g1b520c5``).

    Example::

        git@github.com:ministryofjustice/ntp-formula.git==v1.2.3
        git@github.com:ministryofjustice/repos-formula.git==my_branch
        git@github.com:ministryofjustice/php-fpm-formula.git
        git@github.com:ministryofjustice/utils-formula.git
        git@github.com:ministryofjustice/java-formula.git
        git@github.com:ministryofjustice/redis-formula.git==v0.2.2-1-g1b520c5
        git@github.com:ministryofjustice/logstash-formula.git
        git@github.com:ministryofjustice/sensu-formula.git
        git@github.com:ministryofjustice/rabbitmq-formula.git
        git@github.com:saltstack-formulas/users-formula.git


    """
    dynamic_modules_dirs = ['_modules', '_grains', '_renderers', '_returners', '_states']

    def __init__(self, root_dir, salt_root_path='vendor',
                 clone_path='formula-repos', salt_root='_root'):
        """
        There is a high chance you don't want to change the paths here.

        If you do, you'll need to change the paths in your salt config to ensure
        that there is an entry in `file_roots` that matches self.roots_dir
        (i.e., root_dir + salt_root_path + salt_root)
        """

        self.roots_dir = os.path.join(root_dir, salt_root_path, salt_root)
        self.repos_dir = os.path.join(root_dir, salt_root_path, clone_path)

        self._setup_logger()
        self.fetched_formulas = {}
        self.parsed_requirements_files = set()
        self.first_requirement_file = os.path.join(root_dir, 'formula-requirements.txt')
        self.requirements_files = [
            self.first_requirement_file
        ]

        # This makes any explicit version requirements in from the
        # first_requirement_file override anything from further down. This is a
        # hack to avoid dependency hell until we get SemVer in
        self.override_version_from_toplevel = True

    def _create_dirs(self):
        """
        Keep this out of init, so we don't remove files without re-adding them.
        """

        # Delete the salt roots dir on each run.
        # This is because the files in roots_dir are just symlinks
        if os.path.exists(self.roots_dir):
            shutil.rmtree(self.roots_dir)
        os.makedirs(self.roots_dir)

        # Ensure the repos_dir exists
        try:
            os.makedirs(self.repos_dir)
        except OSError:
            pass

    def _setup_logger(self):
        logging.basicConfig()
        self.logger = logging.getLogger(__name__)

    def _is_from_top_level_requirement(self, file):
        return file == self.first_requirement_file

    def parse_requirement(self, requirement_str):
        """
        Requirement parsing.  Returns a dict containg the full URL to clone
        (`url`), the name of the formula (`name`), a revision (if one is
        specified or 'master' otherwise) (`revision`), and a indication of if
        the revision was explicit or defaulted (`explicit_revision`).
        """
        requirement_str = requirement_str.strip()

        (url, name, rev,) = re.search(r'(.*?/([^/]*?)(?:-formula)?(?:\.git)?)(?:==(.*?))?$', requirement_str).groups()
        return {
            'url': url,
            'name': name,
            'revision': rev or 'master',
            'explicit_revision': bool(rev),
        }

    def parse_requirements_lines(self, lines, source_name):
        """
        Parse requirements from a list of lines, strips out comments and blank
        lines and yields the list of requirements contained, as returned by
        parse_requirement
        """
        for line in lines:
            line = re.sub('#.*$', '', line).strip()
            if not line or line.startswith('#'):
                continue

            req = self.parse_requirement(line)
            if req is None:
                continue

            req['source'] = source_name

            if self._is_from_top_level_requirement(source_name):
                req['top_level_requirement'] = True

            yield req

    def parse_requirements_file(self, filename):
        """
        Parses the formula requirements, and yields dict objects for each line.

        The parsing of each line is handled by parse_requirement
        """
        with open(filename, 'r') as fh:
            return self.parse_requirements_lines(fh.readlines(), filename)

    def install_requirements(self):
        self._create_dirs()

        while len(self.requirements_files):
            req_file = self.requirements_files.pop()
            if req_file in self.parsed_requirements_files:
                # Already parsed.
                continue

            self.parsed_requirements_files.add(req_file)

            self.logger.info("Checking %s" % req_file)
            for formula in self.parse_requirements_file(req_file):
                (repo_dir, _) = self.install_requirement(formula)

                self.fetched_formulas.setdefault(formula['name'], formula)

                # Check for recursive formula dep.
                new_req_file = os.path.join(repo_dir, 'formula-requirements.txt')
                if os.path.isfile(new_req_file):
                    self.logger.info(
                        "Adding {new} to check form {old} {revision}".format(
                            new=new_req_file,
                            old=req_file,
                            revision=formula['revision']))
                    self.requirements_files.append(new_req_file)

    def check_for_version_clash(self, formula):
        """
        Will check to see if `formula` has already been installed and the
        version we requested clashes with the version we've already
        vendored/installed
        """
        previously_fetched = self.fetched_formulas.get(formula['name'], None)
        if previously_fetched:
            if previously_fetched['url'] != formula['url']:
                raise RuntimeError(dedent("""
                    Formula URL clash for {name}:
                    - {old[url]} (defined in {old[source]})
                    + {new[url]} (defined in {new[source]})""".format(
                    name=formula['name'],
                    old=previously_fetched,
                    new=formula)
                ))
        return previously_fetched

    def install_requirement(self, formula):
        """
        Install the requirement as specified by the formula dictionary and
        return the directory symlinked into the roots_dir
        """
        self.check_for_version_clash(formula)

        repo_dir = os.path.join(self.repos_dir, formula['name'] + "-formula")

        with GitSshEnvWrapper():
            repo = self._open_repo(repo_dir, formula['url'])

            sha = self._fetch_and_resolve_sha(formula, repo)

            target = os.path.join(self.roots_dir, formula['name'])
            if sha is None:
                if not os.path.exists(target):
                    raise RuntimeError("%s: Formula marked as resolved but target '%s' didn't exist" % (formula['name'], target))
                return repo_dir, target

            # TODO: Check if the working tree is dirty, and (if request/flagged)
            # reset it to this sha
            if not repo.head.is_valid():
                logging.debug("Resetting invalid head on: {}\n".format(formula['name']))
                repo.head.reset(commit=sha, index=True, working_tree=True)

            if repo.head.commit.hexsha != sha:
                logging.debug("Resetting sha mismatch on: {}\n".format(formula['name']))
                repo.head.reset(commit=sha, index=True, working_tree=True)

            self.logger.debug("{formula[name]} is at {formula[revision]}".format(formula=formula))

        source = os.path.join(repo_dir, formula['name'])
        if os.path.exists(target):
            raise RuntimeError("%s: Target '%s' conflicts with something else" % (formula['name'], target))

        if os.path.exists(source):
            relative_source = os.path.relpath(source, os.path.dirname(target))
            os.symlink(relative_source, target)

        self._link_dynamic_modules(formula)

        return repo_dir, target

    def _link_dynamic_modules(self, formula):
        repo_dir = os.path.join(self.repos_dir, formula['name'] + "-formula")

        for libdir in self.dynamic_modules_dirs:
            targetdir = os.path.join(self.roots_dir, libdir)
            sourcedir = os.path.join(repo_dir, libdir)

            relative_source = os.path.relpath(sourcedir, targetdir)

            if os.path.isdir(sourcedir):
                for name in os.listdir(sourcedir):
                    if not os.path.isdir(targetdir):
                        os.mkdir(targetdir)
                    sourcefile = os.path.join(relative_source, name)
                    targetfile = os.path.join(targetdir, name)
                    try:
                        self.logger.info("linking {}".format(sourcefile))
                        os.symlink(sourcefile, targetfile)
                    except OSError as e:
                        if e.errno == errno.EEXIST:  # already exist
                            self.logger.info(
                                "skipping to linking {} as there is a file with higher priority already there".
                                format(sourcefile))
                        else:
                            raise

    def _fetch_and_resolve_sha(self, formula, repo):
        """
        Work out what the wanted sha is for this formula. If we have already
        satisfied this requirement then return None, else return the sha we
        want `repo` to be at
        """

        previously_fetched = self.fetched_formulas.get(formula['name'], None)

        if previously_fetched is not None and \
           previously_fetched.get('top_level_requirement', False) and \
           previously_fetched['explicit_revision'] and self.override_version_from_toplevel:
            self.logger.info("Overriding {name} version of {new_ver} to {old_ver} from project formula requirements".format(
                name=formula['name'],
                new_ver=formula['revision'],
                old_ver=previously_fetched['revision'],
            ))
            formula['sha'] = previously_fetched['sha']

            # Should already be up to date from when we installed
            # previously_fetched
            return None

        elif 'sha' not in formula:
            self.logger.debug("Resolving {formula[revision]} for {formula[name]}".format(
                formula=formula))

            target_sha = self._rev_to_sha(formula, repo)
            if target_sha is None:
                # This shouldn't happen as _rev_to_sha should throw. Safety net
                raise RuntimeError("No sha resolved!")
            formula['sha'] = target_sha

        if previously_fetched is not None:
            # The revisions might be specified as different strings but
            # resolve to the same. So resolve both and check
            if previously_fetched['sha'] != formula['sha']:

                raise RuntimeError(dedent("""
                    Formula revision clash for {new[name]}:
                    - {old[revision]} <{old_sha}> (defined in {old[source]})
                    + {new[revision]} <{new_sha}> (defined in {new[source]})""".format(
                    old=previously_fetched,
                    old_sha=previously_fetched['sha'][0:7],
                    new=formula,
                    new_sha=formula['sha'][0:7])
                ))

            # Nothing needed - we're already at a suitable sha from when we
            # fetched it previously this run
            return None

        return target_sha

    def _open_repo(self, repo_dir, upstream_url):
        # Split things out into multiple steps and checks to be Ctrl-c resilient
        if os.path.isdir(repo_dir):
            repo = Repo(repo_dir)
        else:
            repo = Repo.init(repo_dir)

        try:
            repo.remotes.origin
        except AttributeError:
            repo.create_remote('origin', upstream_url)
        return repo

    def _rev_to_sha(self, formula, repo):
        """
        Try to resovle the revision into a SHA. If rev is a tag or a SHA then
        try to avoid doing a fetch on the repo if we already know about it. If
        it is a branch then make sure it is the tip of that branch (i.e. this
        will do a git fetch on the repo)
        """

        have_updated = False
        is_branch = False
        sha = None
        origin = repo.remotes.origin

        for attempt in range(0, 2):
            try:
                # Try a tag first. Treat it as immutable so if we find it then
                # we don't have to fetch the remote repo
                tag = repo.tags[formula['revision']]
                return tag.commit.hexsha
            except IndexError:
                pass

            try:
                # Next check for a branch - if it is one then we want to udpate
                # as it might have changed since we last fetched
                (full_ref,) = filter(lambda r: r.remote_head == formula['revision'], origin.refs)
                is_branch = True

                # Don't treat the sha as resolved until we've updated the
                # remote
                if have_updated:
                    sha = full_ref.commit.hexsha
            except (ValueError, AssertionError):
                pass

            # Could just be a SHA
            try:
                if not is_branch:
                    # Don't try to pass it to `git rev-parse` if we know it's a
                    # branch - this would just return the *current* SHA but we
                    # want to force an update
                    #
                    # The $sha^{object} syntax says that this is a SHA *and
                    # that* it is known in this repo. Without this git will
                    # happily take a full sha and go 'yep, that looks like a
                    #  valid sha. Tick'
                    sha = repo.git.rev_parse('{formula[revision]}^{{object}}'.format(formula=formula))
            except GitCommandError:
                # Maybe we just need to fetch first.
                pass

            if sha is not None:
                return sha

            if have_updated:
                # If we've already updated once and get here then we can't find it :(
                raise RuntimeError("Could not find out what revision '{rev}' was for {url} (defined in {source}".format(
                    rev=formula['revision'],
                    url=formula['url'],
                    source=formula['source'],
                ))

            msg = "Fetching %s" % origin.url
            if is_branch:
                msg = msg + " to see if %s has changed" % formula['revision']
            sys.stdout.write(msg)
            origin.fetch(refspec="refs/tags/*:refs/tags/*")
            origin.fetch()
            print(" done")

            have_updated = True


def get_deps(root_dir):
    if os.path.exists(os.path.join(root_dir, 'formula-requirements.txt')):
        return
    deps = {}
    print 'No formula-requirements found. Will generate one.'
    if 'GITHUB_TOKEN' not in os.environ:
        print 'Env variable GITHUB_TOKEN has not been set.'
        sys.exit(1)
    md_file = os.path.join(root_dir, 'metadata.yml')
    if 'ROOT_FORMULA' in os.environ:
        org, formula = os.environ['ROOT_FORMULA'].split('/')
        deps = resolve_deps.get_reqs_recursive(org, formula)
    elif os.path.exists(md_file):
        with open(md_file, 'r') as md_fd:
            data = yaml.load(md_fd)
            for dep in data['dependencies']:
                org, formula = dep.split(':')[1].split('/')
                deps.update(resolve_deps.get_reqs_recursive(org, formula))
    else:
        print 'No ROOOT_FORMULA defined and no metadata file found.'
        sys.exit(1)

    req_file = os.path.join(root_dir, 'formula-requirements.txt')
    with open(req_file, 'w') as req_file:
        for dep in deps:
            org, formula = dep.split('/')
            tag = deps[dep]['tag']
            req_file.write(
                'git@github.com:{0}/{1}.git=={2}\n'.format(org, formula, tag))

@task
def shaker():
    """
    utility task to initiate Shaker in the most typical way
    """
    root_dir = os.path.dirname(env.real_fabfile)
    get_deps(root_dir)
    shaker_instance = Shaker(root_dir=root_dir)
    shaker_instance.install_requirements()


@task
def freeze():
    """
    utility task to check current versions
    """
    local('for d in vendor/formula-repos/*; do echo -n "$d "; git --git-dir=$d/.git describe --tags 2>/dev/null || git --git-dir=$d/.git rev-parse --short HEAD; done', shell='/bin/bash')


@task
def check():
    """
    utility task to check if there are no new versions available
    """
    local('for d in vendor/formula-repos/*; do (export GIT_DIR=$d/.git; git fetch --tags -q 2>/dev/null; echo -n "$d: "; latest_tag=$(git describe --tags $(git rev-list --tags --max-count=1 2>/dev/null) 2>/dev/null || echo "no tags"); current=$(git describe --tags 2>/dev/null || echo "no tags"); echo "\tlatest: $latest_tag  current: $current"); done', shell='/bin/bash')
