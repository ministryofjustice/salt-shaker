import json
import requests
import os
import re
import sys
import pygit2
from parse import parse
import urlparse
from datetime import datetime
import base64

import metadata
from errors import ConstraintResolutionException
import shaker.libs.logger

const_re = re.compile('([=><]+)\s*(.*)')
tag_re = re.compile('v[0-9]+\.[0-9]+\.[0-9]+')


def parse_github_url(url):
    """
    Parse a github url og the form
    git@github.com:test_organisation/test3-formula.git==v3.0.2
    with or witgout constraint and return a
    dictionary of information about it

    Args:
        url(string): The github url to parse

    Returns:
        debug(dictionary): A dictionary of information
            about the url of the form
            {
                'source': <source>,
                'name': <name>,
                'organisation': <organisation>,
                'constraint': <constraint>
            }
    """
    github_root = "git@github.com:"
    shaker.libs.logger.Logger().debug("github::parse_github_url: "
                                      " Parsing '%s'"
                                      % (url))
    constraint = ''
    result = None
    have_constraint = False
    try:
        have_constraint = url.split('.git')[1] != ''
    except IndexError as e:
        msg = ("github::parse_github_url: Could not split url '%s', '%s'"
               % (url, e))
        raise IndexError(msg)

    if have_constraint:
        result = parse("%s{organisation}/{name}.git{constraint}"
                       % (github_root),
                       url)
        constraint = result['constraint']
    else:
        result = parse("%s{organisation}/{name}.git"
                       % (github_root),
                       url)
        shaker.libs.logger.Logger().debug("github::parse_github_url:"
                                          "No constraint found for %s"
                                          % (url))

    organisation = result['organisation']
    name = result['name']
    source = "%s%s/%s.git" % (github_root, organisation, name)

    info = {
        'source': source,
        'name': name,
        'organisation': organisation,
        'constraint': constraint,
    }
    return info


def convert_tag_to_semver(tag):
    """
    Convert a tag name into a list of semver compliant data
    Formats must be of the form,
        v{major}.{minor}.{patch}(-postfix)
    eg,
        v1.2.3
        v1.2.3-prerelease_tag1

    Args:
        tag(string): The tag to convert

    Returns:
        list: List of semver compliant data of form,
            [major_version, minor_version, patch_version, (posfix-tag)]
            Or return an empty list if the tag could not be parsed.
    """
    # Strip any leading 'v' from release/pre-release tags
    if '-' in tag:
        parsed_results = parse('v{maj}.{min}.{patch}-{postfix}', tag)
        if not parsed_results:
            shaker.libs.logger.Logger().debug("github::convert_tag_to_semver: "
                                            "Failed to parse pre-release %s'"
                                            % (tag))
            return []

        rettag = [parsed_results["maj"],
                  parsed_results["min"],
                  parsed_results["patch"],
                  parsed_results["postfix"]
                  ]
        shaker.libs.logger.Logger().debug("github::convert_tag_to_semver: "
                                            "Found %s'"
                                            % (rettag))
        return rettag
    else:
        parsed_results = parse('v{maj}.{min}.{patch}', tag)
        if not parsed_results:
            shaker.libs.logger.Logger().debug("github::convert_tag_to_semver: "
                                            "Failed to parse release %s'"
                                            % (tag))
            return []

        rettag = [parsed_results["maj"], parsed_results["min"], parsed_results["patch"]]
        shaker.libs.logger.Logger().debug("github::convert_tag_to_semver: "
                                            "Found %s'"
                                            % (rettag))
        return rettag


def get_valid_tags(org_name,
             formula_name,
             max_tag_count=1000):
    """
    Get all semver compliant tags from a repository using the
    formula organisation and name

    Args:
        org_name(string): The organisation name of the repository
        formula_name(string): The formula name of the repository
        max_tag_count(int): Limit on amount of tags to fetch

    Returns:
        string: The tag that is calculated to be the 'preferred' one
        list: All the tag versions found that were semver compliant
        dictionary: Data for all tags, semver compliant or not
    """

    github_token = get_valid_github_token()
    if not github_token:
        shaker.libs.logger.Logger().error("github::get_valid_tags: "
                                          "No valid github token")
        sys.exit(1)

    tags_url = ('https://api.github.com/repos/%s/%s/tags?per_page=%s'
                % (org_name, formula_name, max_tag_count))
    tag_versions = []
    tags_data = {}
    tags_json = requests.get(tags_url,
                             auth=(github_token, 'x-oauth-basic'))
    # Check for successful access and any credential problems
    if validate_github_access(tags_json):
        try:
            tags_data = json.loads(tags_json.text)
            for tag in tags_data:
                raw_name = tag['name']
            
                semver_info = convert_tag_to_semver(raw_name)
                # If we have a semver valid tag, then add,
                # otherwise ignore
                if len(semver_info) > 0:
                    
                    parsed_tag_version_results = parse('v{tag}', raw_name)
                    if parsed_tag_version_results:
                        shaker.libs.logger.Logger().debug("github::get_valid_tags: "
                                      "Appending valid tag %s'"
                                      % (raw_name))
                        parsed_tag_version = parsed_tag_version_results["tag"]
                        tag_versions.append(parsed_tag_version)
                else:
                    shaker.libs.logger.Logger().warning("github::get_valid_tags: "
                                      "Ignoring semver invalid tag %s'"
                                      % (raw_name))

            tag_versions.sort()
            wanted_tag = 'v{0}'.format(tag_versions[-1])
        except ValueError as e:
            msg = ("github::get_valid_tags: "
                   "Invalid json for url '%s': %s"
                   % (tags_url,
                      e.message))
            raise ValueError(msg)
    else:
        wanted_tag = 'master'

    shaker.libs.logger.Logger().debug("github::get_valid_tags: "
                                     "wanted_tag=%s, tag_versions=%s"
                                    % (wanted_tag, tag_versions))
    return wanted_tag, tag_versions, tags_data


def is_tag_prerelease(tag):
    """
    Simple check for a pre-release

    Args:
        tag(string): The tag in format v1.2.3-postfix

    Returns:
        bool: True if format is that of a pre-release,
            false otherwise
    """
    parsed_results = parse('v{version}-{postfix}', tag)
    if parsed_results:
        return True

    return False


def resolve_constraint_to_object(org_name, formula_name, constraint):
    """
    For a given formula, take the constraint and compare it to
    the repositories available tags. Then try to find a tag that
    best resolves within the constraint.

    If we can get resolutions, return the json data object associated
    with the tag. If not, then raise a ConstraintResolutionException

    Args:
        org_name(string): The organisation name of the formula
        formula_name(string): The formula name
        constraint(string): The constraint to be applied, in the form
            <comparator><tag>. eg, '==v1.0.1', '>=2.0.1'

    Returns:
        dictionary: Json data from github associated with the resolved tag
        ConstraintResolutionException: If no resolutions was possible
    """
    shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                      "resolve_constraint_to_object(%s, %s, %s)"
                                      % (org_name, formula_name, constraint))
    wanted_tag, tag_versions, tags_data = get_valid_tags(org_name, formula_name)

    if not constraint or (constraint == ''):
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                          "No constraint specified, returning '%s'"
                                          % (wanted_tag))
        obj = None
        for tag_data in tags_data:
            if tag_data["name"] == wanted_tag:
                obj = tag_data
                break
        return obj

    parsed_constraint = metadata.parse_constraint(constraint)
    parsed_comparator = parsed_constraint['comparator']
    parsed_tag = parsed_constraint['tag']
    parsed_version = parsed_constraint['version']

    # See if we can pick up a version
    if tag_versions and parsed_version:
        if parsed_comparator == '==':
            if parsed_version in tag_versions:
                shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                                  "Found exact version '%s'"
                                                  % (parsed_version))
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == parsed_tag:
                        obj = tag_data
                        break
                return obj
            else:
                raise ConstraintResolutionException("github::resolve_constraint_to_object: "
                                                    "Could not satisfy constraint '%s', "
                                                    " version %s not in tag list %s"
                                                    % (constraint,
                                                       parsed_constraint,
                                                       tag_versions))
        else:
            # Get a versioned tag (eg, v1.1.0) that is most greater than,
            # or least less than
            # but also not another type of tag (eg 'fdfsdfdsfsd')
            valid_version = None
            if parsed_comparator == '>=':
                # Get latest non pre-release version
                for tag_version in reversed(tag_versions):
                    if (tag_version >= parsed_version):
                        if not is_tag_prerelease(tag_version):
                            valid_version = tag_version
                            break
                        else:
                            shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                                  "Skipping pre-release version '%s'"
                                                  % (tag_version))
                    else:
                        raise ConstraintResolutionException("github::resolve_constraint_to_object: "
                                                    " No non-prerelease version found %s"
                                                    % (constraint))

            elif parsed_comparator == '<=':
                valid_version=None
                for tag_version in reversed(tag_versions):
                    if (tag_version <= parsed_version):
                        if not is_tag_prerelease(tag_version):
                            valid_version = tag_version
                            break
                        else:
                            shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                                  "Skipping pre-release version '%s'"
                                                  % (tag_version))

                if not valid_version:
                    raise ConstraintResolutionException("github::resolve_constraint_to_object: "
                                                " No non-prerelease version found %s"
                                                % (constraint))
            else:
                msg = ("github::resolve_constraint_to_object: "
                       "Unknown comparator '%s'" % (parsed_comparator))
                raise ConstraintResolutionException(msg)

            if valid_version:
                shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: "
                                                  "resolve_constraint_to_object:Found valid version '%s'"
                                                  % (valid_version))
                valid_tag = 'v%s' % valid_version
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == valid_tag:
                        obj = tag_data
                        break

                return obj
            else:
                raise ConstraintResolutionException("github::resolve_constraint_to_object: "
                                                    'Constraint %s cannot be satisfied for %s/%s'
                                                    % (constraint, org_name, formula_name))
    else:
        msg = ("github::resolve_constraint_to_object: "
               "Unknown parsed constraint '%s' from '%s'" % (parsed_constraint, constraint))
        raise ConstraintResolutionException(msg)
    raise ConstraintResolutionException("github::resolve_constraint_to_object: "
                                        'Constraint {} cannot be satisfied for {}/{}'.format(constraint,
                                                                                             org_name,
                                                                                             formula_name))

    return None


def get_valid_github_token(online_validation_enabled=False):
    """
    Check for a github token environment variable. If its not there,
    or is invalid, log a message and return None. Otherwise, return the token string

    Parameters:
        online_validation_enabled (bool): If True, then try out the credentials against
        the github api for success. No online validation if false
    Returns:
        github_token (string): The valid github token, None if invalid
    """
    github_token = None

    # A simple check for the right environment variable
    if "GITHUB_TOKEN" not in os.environ:
        shaker.libs.logger.Logger().error("No github token found. "
                                          "Please set your GITHUB_TOKEN environment variable")
    else:
        # Test an oauth call to the api, make sure the credentials are
        # valid and we're not locked out
        if online_validation_enabled:
            url = "https://api.github.com"
            response = requests.get(url,
                                    auth=(os.environ["GITHUB_TOKEN"],
                                          'x-oauth-basic'))

            # Validate the response against expected status codes
            # Set the return value to the token if we have success
            valid_response = validate_github_access(response)
            if valid_response:
                github_token = os.environ["GITHUB_TOKEN"]
                shaker.libs.logger.Logger().error("No valid repsonse from github token '%s'"
                                                  % (github_token))
        else:
            # If we're not validating online, just accept that we have a token
            github_token = os.environ["GITHUB_TOKEN"]

    return github_token


def validate_github_access(response):
    """
    Validate the github api's response for known credential problems

    Checked responses are

        * Authenticating with invalid credentials will return 401 Unauthorized:

        HTTP/1.1 401 Unauthorized
        {
            "message": "Bad credentials",
            "documentation_url": "https://developer.github.com/v3"
        }

        * Forbidden
        HTTP/1.1 403 Forbidden
        {
          "message": "Maximum number of login attempts exceeded. Please try again later.",
          "documentation_url": "https://developer.github.com/v3"
        }

    Args:
        response (requests.models.Response): The Response from the github server

    Returns:
        valid_credentials (bool): True if access was successful, false otherwise

    """

    # Assume invalid credentials unless proved otherwise

    if (type(response) == requests.models.Response):

        # Check the status codes for success
        if response.status_code == 200:
            shaker.libs.logger.Logger().debug("Github access checked ok")
            return True
        else:
            # Set a default response message, use the real one if we
            # find it in the response
            response_message = "No response found"
            try:
                # Access the responses body as json
                response_json = json.loads(response.text)
                if "message" in response_json:
                    response_message = response_json["message"]
                shaker.libs.logger.Logger().debug("Github credentials test got response: %s"
                                                  % response_json)
            except:
                # Just ignore if we can'l load json, its not essential here
                if (response.status_code == 401) and ("Bad credentials" in response_message):
                    shaker.libs.logger.Logger().error("validate_github_access: "
                                                      "Github credentials incorrect: %s" % response_message)
                elif response.status_code == 403 and ("Maximum number of login attempts exceeded" in response_message):
                    shaker.libs.logger.Logger().error("validate_github_access: "
                                                      "Github credentials failed due to lockout: %s" % response_message)
                elif response.status_code == 404:
                    shaker.libs.logger.Logger().error("validate_github_access: "
                                                      "URL not found")
                else:
                    shaker.libs.logger.Logger().error("validate_github_access: "
                                                      "Unknown problem checking credentials: %s" % response)
    else:
        shaker.libs.logger.Logger().error("Invalid response: %s" % response)

    return False


def open_repository(url,
                    target_directory):
    """
    Make a connection from a remote git repository into a local
    directory.

    Args:
        url(string): The remote github url of the repository
        target_directory(string): The local target directory

    Returns:
        pygit2.repo: The repository object created
    """
    git_url = urlparse.urlparse(url)
    username = git_url.netloc.split('@')[0]\
        if '@' in git_url.netloc else 'git'
    credentials = pygit2.credentials.KeypairFromAgent(username)

    # If local directory exists, then make a connection to it
    # Otherwise, clone the remote repo into the new directory
    if os.path.isdir(target_directory):
        shaker.libs.logger.Logger().debug("open_repository: "
                                          "Opening url '%s' "
                                          "with existing local repository '%s'"
                                          % (url, target_directory))
        repo = pygit2.Repository(target_directory)
    else:
        repo = pygit2.clone_repository(url,
                                       target_directory,
                                       credentials=credentials)
        shaker.libs.logger.Logger().debug(":open_repository: "
                                          "Cloning url '%s' into local repository '%s'"
                                          % (url, target_directory))
    origin = filter(lambda x: x.name == 'origin', repo.remotes)
    if not origin:
        repo.create_remote('origin', url)
        origin = filter(lambda x: x.name == 'origin', repo.remotes)
    origin[0].credentials = credentials

    return repo


def install_source(target_source,
                   target_directory):
    """
    Install the requirement as specified by the formula dictionary and
    return the directory symlinked into the roots_dir

    Args:
        target_source(dictionary): A keyed collection of information about the
            source of the format
            {
                'name': '<target_name>',
                'url': '<target_url>',
                sha: The sha revision to install
            }
        target_directory(string): THe directory to install into
    """
    target_name = target_source.get('name', None)
    target_url = target_source.get('source', None)
    target_sha = target_source.get('sha', None)
    target_path = os.path.join(target_directory,
                               target_name)
    shaker.libs.logger.Logger().debug("install_source: Opening %s in directory %s, "
                                      "with url %s, and sha %s"
                                      % (target_name,
                                         target_directory,
                                         target_url,
                                         target_sha))
    target_repository = open_repository(target_url, target_path)

    current_sha = get_repository_sha(target_path,
                                     revision='HEAD')

    # If the local and target shas are the same, skip
    # otherwise, update the repository
    if current_sha == target_sha:
        shaker.libs.logger.Logger().debug("github::install_source: %s: "
                                          "Target and current shas are equivalent..."
                                          "skipping update: %s"
                                          % (target_path,
                                             target_sha))
        return False

    oid = pygit2.Oid(hex=target_sha)
    target_repository.checkout_tree(target_repository[oid].tree)
    shaker.libs.logger.Logger().debug("github::install_source: Checking out sha '%s' into '%s"
                                      % (target_sha, target_path))
    # The line below is *NOT* just setting a value.
    # Pygit2 internally resets the head of the filesystem to the OID we set.
    #
    #
    # In other words .... *** WARNING: MAGIC IN PROGRESS ***
    target_repository.set_head(oid)

    if target_repository.head.get_object().hex != target_sha:
        shaker.libs.logger.Logger().debug("Resetting sha mismatch on source '%s'"
                                          % (target_name))
        target_repository.reset(target_sha, pygit2.GIT_RESET_HARD)
        # repo.head.reset(commit=sha, index=True, working_tree=True)

    shaker.libs.logger.Logger().debug("Source '%s' is at version '%s'"
                                      % (target_name, target_sha))

    return True


def resolve_tag_to_sha(target_source,
                       target_version,
                       target_directory):
    """
    Try to resolve the revision into a SHA. If rev is a tag or a SHA then
    try to avoid doing a fetch on the repo if we already know about it. If
    it is a branch then make sure it is the tip of that branch (i.e. this
    will do a git fetch on the repo)
    """

    # Check for a a tag with the targets version
    # If we don't have a v1.0 style tag then try as a branch head
    # If none of the above, try it as a straight sha
    target_name = target_source.get('name', None)
    target_url = target_source.get('source', None)
    target_path = os.path.join(target_directory,
                               target_name)

    repository = open_repository(target_url, target_path)

    origin = get_origin_for_remote(repository)
    if not origin:
        raise RuntimeError("Unable to find origin for repo.")

    url = urlparse.urlparse(origin.url)
    username = url.netloc.split('@')[0] if '@' in url.netloc else 'git'
    origin.credentials = pygit2.credentials.KeypairFromAgent(username)

    for attempt in range(0, 2):
        # Try a tag first. Treat it as immutable so if we find it then
        # we don't have to fetch the remote repo
        refs = repository.listall_references()
        tag_ref = 'refs/tags/{}'.format(target_version)
        if tag_ref in refs:
            sha = repository.lookup_reference(tag_ref).get_object().hex
            shaker.libs.logger.Logger().debug("resolve_tag_to_sha: "
                                              "Found sha '%s' for tag '%s' on attempt"
                                              % (sha,
                                                 tag_ref,
                                                 attempt))
            return sha

        # Next check for a branch - if it is one then we want to update
        # as it might have changed since we last fetched
        branch_ref = 'refs/remotes/origin/{}'.format(target_version)
        if branch_ref in refs:
            full_ref = repository.lookup_reference(branch_ref)
            # Don't treat the sha as resolved until we've updated the
            # remote
            if full_ref:
                sha = full_ref.get_object().hex
                shaker.libs.logger.Logger().debug("resolve_tag_to_sha: "
                                                  "Found sha '%s' for branch '%s'"
                                                  % (sha, tag_ref))
                return sha

        # Could just be a SHA
        try:
            sha = repository.revparse_single(target_version).hex
            shaker.libs.logger.Logger().debug("resolve_tag_to_sha: "
                                              "Found direct reference to sha '%s'"
                                              % (sha))
            return sha
        except KeyError:
            # Maybe we just need to fetch first.
            pass

        shaker.libs.logger.Logger().debug("resolve_tag_to_sha: "
                                          "Cannot find version '%s' in refs '%s'"
                                          % (target_version, refs))
    return None


def get_repository_debug(repository):
    repo = pygit2.Repository(repository)
    objects = {
        'tags': [],
        'commits': [],
    }

    for objhex in repo:
        obj = repo[objhex]
        if obj.type == pygit2.GIT_OBJ_COMMIT:
            objects['commits'].append({
                'hash': obj.hex,
                'message': obj.message,
                'commit_date': datetime.utcfromtimestamp(
                    obj.commit_time).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'author_name': obj.author.name,
                'author_email': obj.author.email,
                'parents': [c.hex for c in obj.parents],
            })
        elif obj.type == pygit2.GIT_OBJ_TAG:
            objects['tags'].append({
                'hex': obj.hex,
                'name': obj.name,
                'message': obj.message,
                'target': base64.b16encode(obj.target).lower(),
                'tagger_name': obj.tagger.name,
                'tagger_email': obj.tagger.email,
            })
        elif obj.type == pygit2.GIT_OBJ_TAG:
            objects['tags'].append({
                'hex': obj.hex,
                'name': obj.name,
                'message': obj.message,
                'target': base64.b16encode(obj.target).lower(),
                'tagger_name': obj.tagger.name,
                'tagger_email': obj.tagger.email,
            })
        elif obj.type == pygit2.GIT_OBJ_TREE:
                objects['tree'].append({'hex': obj.hex,
                                        'name': obj.name,
                                        'message': obj.message,
                                        'target': base64.b16encode(obj.target).lower(),
                                        'tagger_name': obj.tagger.name,
                                        'tagger_email': obj.tagger.email,
                                        })
        else:
            # ignore blobs and trees
            pass

    return(json.dumps(objects, indent=2))


def get_origin_for_remote(repository):
    """
    Find the origin of a remote repository

    Args:
        repository(pygit2.repository):
            The remote repository to search

    Returns:
        pygit2.remote: The remote origin, None type
            if it couldn't be found
    """
    for remote in repository.remotes:
        if remote.name == 'origin':
            url_bits = urlparse.urlparse(remote.url)
            if url_bits.scheme == 'git':
                remote.url = 'ssh://{0}{1}'.format(url_bits.netloc,
                                                   url_bits.path)
                remote.save()
            return remote

    return None


def get_repository_sha(path,
                       revision='HEAD'):
    """
    Get the sha from a repository path and revision

    Args:
        path(string): The path to the repository to open
        revision(string): the revision to get the sha of

    Returns:
        string: The sha of the revision, None type if
            not found
    """
    try:
        repository = pygit2.Repository(path)
        sha = repository.revparse_single(revision).oid
        return sha.__str__()
    except KeyError as e:
        shaker.libs.logger.Logger().debug("github::get_repository_sha: "
                                          "Error opening repository: %s"
                                          % (e))
        return None
