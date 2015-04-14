import logging
import os
import sys
import re
import time
import shutil
import urlparse
import errno
import glob
from textwrap import dedent

import pygit2
import yaml

import resolve_deps
import helpers
import logging


class Shaker(object):
    """
    Start from a root formula and calculate all necessary dependencies,
    based on metadata stored in each formula.

    How it works
    ------------

    Salt Shaker works by creating an extra file root that must be copied up to
    your salt server and added to the master config.


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
    dynamic_modules_dirs = ['_modules', '_grains', '_renderers',
                            '_returners', '_states']

    # The root directory
    root_dir = None
    # The local metadata
    local_metadata = None

    def __init__(self, root_dir, salt_root_path='vendor',
                 clone_path='formula-repos', 
                 salt_root='_root',
                 metadata_filename='metadata.yml'):
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
        self.first_requirement_file = os.path.join(root_dir,
                                                   'formula-requirements.txt')
        self.requirements_files = [
            self.first_requirement_file
        ]

        # This makes any explicit version requirements in from the
        # first_requirement_file override anything from further down. This is a
        # hack to avoid dependency hell until we get SemVer in
        self.override_version_from_toplevel = True

        # Set the local root directory
        self.root_dir = root_dir
        # Load in the local metadata
        self.local_metadata = helpers.load_metadata_from_file(root_dir,
                                                              metadata_filename)

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

        #Change git cli style URLs to libgit format
        # (username@host:repo to git://username@host/repo)
        # TODO: Use urlparse to parse the url.
        if url[0:4] == 'git@':
            url = 'ssh://{0}'.format(url.replace(':', '/', 1))

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
        if not os.path.exists(filename):
            print '%s not found. skipping' % filename
            return []

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

    def install_requirement(self, formula):
        """
        Install the requirement as specified by the formula dictionary and
        return the directory symlinked into the roots_dir
        """
        # self.check_for_version_clash(formula)

        repo_dir = os.path.join(self.repos_dir, formula['name'] + "-formula")
        repo = self._open_repo(repo_dir, formula['url'])


        sha = self._fetch_and_resolve_sha(formula, repo)

        target = os.path.join(self.roots_dir, formula['name'])
        if sha is None:
            if not os.path.exists(target):
                raise RuntimeError("%s: Formula marked as resolved but target '%s' didn't exist" % (formula['name'], target))
            return repo_dir, target

        oid = pygit2.Oid(hex=sha)
        repo.checkout_tree(repo[oid].tree)
        # The line below is *NOT* just setting a value.
        # Pygit2 internally resets the head of the filesystem to the OID we set.
        #
        #
        # In other words .... *** WARNING: MAGIC IN PROGRESS ***
        repo.set_head(oid)

        if repo.head.get_object().hex != sha:
            logging.debug("Resetting sha mismatch on: {}\n".format(formula['name']))
            repo.reset(sha, pygit2.GIT_RESET_HARD)
            # repo.head.reset(commit=sha, index=True, working_tree=True)

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
        target_sha = None

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
        git_url = urlparse.urlparse(upstream_url)
        username = git_url.netloc.split('@')[0]\
            if '@' in git_url.netloc else 'git'
        credentials = pygit2.credentials.KeypairFromAgent(username)
        if os.path.isdir(repo_dir):
            repo = pygit2.Repository(repo_dir)
        else:
            try:
                repo = pygit2.clone_repository(upstream_url, repo_dir,
                                           credentials=credentials)
            except pygit2.errors.GitError as e:
                logging.error("Shaker::_open_repo: Problem cloning "
                              " repository '%s', %s"
                              % (upstream_url, e)
                              )
                sys.exit(1)

        origin = filter(lambda x: x.name == 'origin', repo.remotes)
        if not origin:
            repo.create_remote('origin', upstream_url)
            origin = filter(lambda x: x.name == 'origin', repo.remotes)
        origin[0].credentials = credentials

        self.logger.info('Cloned {}'.format(upstream_url))
        return repo

    def _block_while_fetching(self, transfer_progress):
        t_o = transfer_progress.total_objects
        t_d = transfer_progress.total_deltas
        while True:
            i_o = transfer_progress.indexed_objects
            i_d = transfer_progress.indexed_deltas
            if i_d == t_d and i_o == t_o:
                break
            time.sleep(0.5)

    def _rev_to_sha(self, formula, repo):
        """
        Try to resolve the revision into a SHA. If rev is a tag or a SHA then
        try to avoid doing a fetch on the repo if we already know about it. If
        it is a branch then make sure it is the tip of that branch (i.e. this
        will do a git fetch on the repo)
        """

        have_updated = False
        is_branch = False
        sha = None
        rev = formula['revision']
        origin = None
        for remote in repo.remotes:
            if remote.name == 'origin':
                url_bits = urlparse.urlparse(remote.url)
                if url_bits.scheme == 'git':
                    remote.url = 'ssh://{0}{1}'.format(url_bits.netloc,
                                                       url_bits.path)
                    remote.save()
                origin = remote
                break
        if not origin:
            raise RuntimeError("Unable to find origin for repo.")
        url = urlparse.urlparse(origin.url)
        username = url.netloc.split('@')[0] if '@' in url.netloc else 'git'
        origin.credentials = pygit2.credentials.KeypairFromAgent(username)

        for attempt in range(0, 2):
            # Try a tag first. Treat it as immutable so if we find it then
            # we don't have to fetch the remote repo
            refs = repo.listall_references()
            tag_ref = 'refs/tags/{}'.format(rev)
            if tag_ref in refs:
                return repo.lookup_reference(tag_ref).get_object().hex

            # Next check for a branch - if it is one then we want to update
            # as it might have changed since we last fetched
            branch_ref = 'refs/remotes/origin/{}'.format(rev)
            if branch_ref in refs:
                full_ref = repo.lookup_reference(branch_ref)
                is_branch = True
                # Don't treat the sha as resolved until we've updated the
                # remote
                if full_ref and have_updated:
                    sha = full_ref.get_object().hex
                    return sha

            # Could just be a SHA
            try:
                sha = repo.revparse_single(formula['revision']).hex \
                    if not is_branch else None
            except KeyError:
                # Maybe we just need to fetch first.
                pass

            if sha:
                return sha

            if have_updated:
                # If we've already updated once and get here
                # then we can't find it :(
                raise RuntimeError(
                    "Could not find out what revision '{rev}' was for {url}"
                    "(defined in {source}".format(
                        rev=formula['revision'],
                        url=formula['url'],
                        source=formula['source']
                    )
                )

            msg = "Fetching %s" % origin.url
            if is_branch:
                msg = msg + " to see if %s has changed" % formula['revision']
            sys.stdout.write(msg)
            origin.add_fetch("refs/tags/*:refs/tags/*")
            self._block_while_fetching(origin.fetch())
            print(" done")
            have_updated = True


    def get_formulas(self):
        """
        Read in metadata from the supplied directory, then use
        this data to generate a list of required formulas

        Returns:
            formulas(list): A list of formulas of the form
                [<organisation>, <name>, <constraint>
        """
        formulas = []

        if self.local_metadata:
            for dep in self.local_metadata.get('dependencies', []):
                parts = dep.split(' ')
                toks = parts[0].split(':')[1].split('/')
                if '.git' == toks[1][-4:]:
                    toks[1] = toks[1].split('.git')[0]
                if len(parts) > 1:
                    toks.append(' '.join(parts[1:]))
                else:
                    toks.append('')
                logging.info("salt_shaker::get_formulas: Appending formula '%s'"
                             % (toks))
                formulas.append(toks)
        else:
            logging.error('salt-shaker:get_formulas: No metadata file found.')
            sys.exit(1)

        return formulas

    def get_deps(self, force=False):
        if not force and os.path.exists(os.path.join(
                self.root_dir, 'formula-requirements.txt')):
            return

        deps = {}

        logging.info('No formula-requirements found. Will generate one.')
        github_token = helpers.get_valid_github_token()
        if not github_token:
            sys.exit(1)

        formulas = self.get_formulas()

        # See if we've got a root_formula
        # Look for a root formula name in metadata
        root_formula_entry = self.local_metadata.get("name", None)
        root_formulas = []
        if root_formula_entry:
            org, formula = root_formula_entry.split('/')
            root_formulas.append([org, formula, ''])
            logging.info("salt_shaker::get_deps: Found root formula '%s'"
                         % ([org, formula, '']))
        else:
            logging.info("salt-shaker:get_deps: "
                         "No root formula name found, "
                         "assuming this is a non-root formula")

        deps.update(resolve_deps.get_reqs_recursive(formulas,
                                                    root_formulas=root_formulas)
                    )

        req_file = os.path.join(self.root_dir, 'formula-requirements.txt')
        with open(req_file, 'w') as req_file:
            for dep in deps:
                org, formula = dep.split('/')
                tag = deps[dep]['tag']
                req_file.write(
                    'git@github.com:{0}/{1}.git=={2}\n'.format(org, formula, tag))


def shaker(root_dir='.', force=False, verbose=False):
    """
    utility task to initiate Shaker in the most typical way
    """
    if (verbose):
        logging.basicConfig(log_level=logging.INFO)

    if not os.path.exists(root_dir):
        os.makedirs(root_dir, 0755)
    shaker_instance = Shaker(root_dir=root_dir)
    shaker_instance.get_deps(force=force)
    shaker_instance.install_requirements()


def freeze(root_dir='.'):
    formula_dir = '{}/vendor/formula_repos/'.format(root_dir)
    formula_repos = glob.glob('{}/*-formula'.format(formula_dir))
    for formula in formula_repos:
        repo = pygit2.Repository(formula)

#find all repos in directory
#get current tag or sha of HEAD if no tags available from each repo



# @task
# def freeze():
#     """
#     utility task to check current versions
#     """
#     local('for d in vendor/formula-repos/*; do echo -n "$d "; git --git-dir=$d/.git describe --tags 2>/dev/null || git --git-dir=$d/.git rev-parse --short HEAD; done', shell='/bin/bash')
#
#
# @task
# def check():
#     """
#     utility task to check if there are no new versions available
#     """
#     local('for d in vendor/formula-repos/*; do (export GIT_DIR=$d/.git; git fetch --tags -q 2>/dev/null; echo -n "$d: "; latest_tag=$(git describe --tags $(git rev-list --tags --max-count=1 2>/dev/null) 2>/dev/null || echo "no tags"); current=$(git describe --tags 2>/dev/null || echo "no tags"); echo "\tlatest: $latest_tag  current: $current"); done', shell='/bin/bash')


#TODO
# generate formula skeleton
# unit tests
# change tasks above not to depend on fabric if possible
# document metadata.yml
# Think about formatting, multiple protocols, vers, criteria (<>=.....)


# move shaker task in cotton or separate tasks file
