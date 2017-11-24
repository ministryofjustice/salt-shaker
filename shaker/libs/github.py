import json
import requests
import os
import re
import sys
import pygit2
from parse import parse
import urlparse
from distutils.version import LooseVersion
import metadata
from errors import ConstraintResolutionException
from errors import GithubRepositoryConnectionException
import shaker.libs.logger
from shaker.libs.pygit2_utils import pygit2_parse_error


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


def parse_semver_tag(tag):
    """
    Convert a tag name into a dictionary of semver compliant
    data. Formats must be of the form,
        v{major}.{minor}.{patch}(-postfix)
    eg,
        v1.2.3
        v1.2.3-prerelease_tag1

    Args:
        tag(string): The tag to convert

    Returns:
        dictionary: Dictionary of semver compliant data of form,
            {   "major: major_version,
                "minor": minor_version,
                "patch": patch_version,
                "postfix": (posfix-tag)
            }
        If the tag could not be parsed, the values of all keys are set to None.
    """
    retval = {
        "major": None,
        "minor": None,
        "patch": None,
        "postfix": None,
    }

    # Use these regexs to determine the accetable tag type
    version_comparators = {
        'release': 'v(\d+).(\d+).(\d+)$',
        'prerelease': 'v(\d+).(\d+).(\d+)-(.+)',
        'prerelease-compat': 'v(\d+).(\d+).(\d+)(.+)',
    }

    # Check for a release v1.2.3
    if re.match(version_comparators["release"], tag):
        parsed_results = parse('v{major:d}.{minor:d}.{patch:d}', tag)
        retval = {
            "major": parsed_results["major"],
            "minor": parsed_results["minor"],
            "patch": parsed_results["patch"],
            "postfix": None,
        }
    # Check for a semver compliant prerelease v1.2.3-pre1
    elif re.match(version_comparators["prerelease"], tag):
        parsed_results = parse('v{major:d}.{minor:d}.{patch:d}-{postfix}', tag)
        retval = {
            "major": parsed_results["major"],
            "minor": parsed_results["minor"],
            "patch": parsed_results["patch"],
            "postfix": parsed_results["postfix"],
        }
    # Check for a non-semver compliant prerelease v1.2.3pre1
    elif re.match(version_comparators["prerelease-compat"], tag):
        parsed_results = re.match(version_comparators["prerelease-compat"], tag).groups()
        retval = {
            "major": int(parsed_results[0]),
            "minor": int(parsed_results[1]),
            "patch": int(parsed_results[2]),
            "postfix": parsed_results[3],
        }
    # Not an acceptable versioned tag
    else:
        shaker.libs.logger.Logger().debug("github::parse_semver_tag: "
                                          "Failed to parse tag %s'"
                                          % (tag))

    return retval


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
    parsed_results = parse_semver_tag(tag)
    rettag = [
        parsed_results["major"],
        parsed_results["minor"],
        parsed_results["patch"],
        parsed_results["postfix"],
    ]

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
        msg = "github::get_branch_data: No valid github token"
        raise GithubRepositoryConnectionException(msg)

    tags_url = ('https://api.github.com/repos/%s/%s/tags?per_page=%s'
                % (org_name, formula_name, max_tag_count))
    tag_versions = []
    tags_data = {}
    tags_json = requests.get(tags_url,
                             auth=(github_token, 'x-oauth-basic'))

    shaker.libs.logger.Logger().debug("github::get_valid_tags: "
                                      "Calling validate_github_access with %s "
                                      % str(tags_json))

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
            wanted_version = get_latest_tag(tag_versions,
                                            include_prereleases=False)
            if wanted_version:
                wanted_tag = 'v{0}'.format(wanted_version)
            else:
                wanted_tag = None

        except ValueError as e:
            msg = ("github::get_valid_tags: "
                   "Invalid json for url '%s': %s"
                   % (tags_url,
                      e.message))
            raise ValueError(msg)
    else:
        wanted_tag = None

    shaker.libs.logger.Logger().debug("github::get_valid_tags: "
                                      "wanted_tag=%s, tag_versions=%s"
                                      % (wanted_tag, tag_versions))
    return wanted_tag, tag_versions, tags_data


def get_branch_data(org_name,
                    formula_name,
                    branch_name):
    """
    Get the raw data from github for a specific branch of the repo

    Args:
        org_name(string): The organisation name of the repository
        formula_name(string): The formula name of the repository
        branch_name(string): Name of the branch

    Returns:
        dictionary: Data for the specific branch or a empty in case of
        problems
    """

    shaker.libs.logger.Logger().debug("github::get_branch_data: "
                                      "starts here: org_name %s "
                                      "formula_name %s branch_name %s"
                                      % (org_name, formula_name, branch_name))
    github_token = get_valid_github_token()
    if not github_token:
        msg = "github::get_branch_data: No valid github token"
        raise GithubRepositoryConnectionException(msg)

    branch_url = ('https://api.github.com/repos/%s/%s/branches/%s'
                  % (org_name, formula_name, branch_name))
    shaker.libs.logger.Logger().debug("github::get_branch_data: "
                                      "branch_url %s "
                                      % (branch_url))
    branch_json = requests.get(branch_url,
                               auth=(github_token, 'x-oauth-basic'))

    shaker.libs.logger.Logger().debug("github::get_branch_data: "
                                      "Calling validate_github_access with %s "
                                      % str(branch_json))
    # Check for successful access and any credential problems
    if validate_github_access(branch_json):
        try:
            branch_data = json.loads(branch_json.text)
        except ValueError as e:
            msg = ("github::get_branch_data: "
                   "Invalid json for url '%s': %s"
                   % (branch_url,
                      e.message))
            raise ValueError(msg)
    else:
        branch_data = None

    return branch_data


def get_latest_tag(tag_versions,
                   include_prereleases=False):
    """
    Get the latest valid semver tag from a list of tag versions.
    Trivially we can return the very latest if we like, but this
    will skip non-release versions by default

    Args:
        tag_versions(list): List of tag versions, in format
            [
                "1.2.3-prerelease1",
                "1.1.1",
                "0.8.7"
            ]
        include_prereleases(bool): True to include prereleases
            in looking for latest semver compliant release tags,
            false to only use releases (eg, 1.2.3)

    Returns:
        string: tag version of the latest tag, in form "1.2.3"
    """
    shaker.libs.logger.Logger().debug("github::get_latest_tag: "
                                      "Latest from %s"
                                      % (tag_versions))
    tag_versions.sort(key=LooseVersion)
    for tag_version in reversed(tag_versions):
        is_release = is_tag_release("v%s" % tag_version)
        is_prerelease = is_tag_prerelease("v%s" % tag_version)

        if not include_prereleases:
            if is_release and not is_prerelease:
                shaker.libs.logger.Logger().debug("github::get_latest_tag: "
                                                  "Found '%s' (excluding pre-releases)"
                                                  % (tag_version))
                return tag_version
        else:
            if is_release or is_prerelease:
                shaker.libs.logger.Logger().debug("github::get_latest_tag: "
                                                  "Found '%s' (including pre-releases)"
                                                  % (tag_version))
                return tag_version

    return None


def is_tag_release(tag):
    """
    Simple check for a release

    Args:
        tag(string): The tag in format v1.2.3

    Returns:
        bool: True if format is that of a release,
            false otherwise
    """
    parsed_tag = parse_semver_tag(tag)
    valid_version_checks = (
        (parsed_tag["major"] is not None) and
        (parsed_tag["minor"] is not None) and
        (parsed_tag["patch"] is not None)
    )
    if not valid_version_checks:
        shaker.libs.logger.Logger().debug("github::is_tag_release: "
                                          "%s is not release, bad version checks" % (tag))
        return False
    if parsed_tag["postfix"]:
        shaker.libs.logger.Logger().debug("github::is_tag_release: "
                                          "%s is not release, contains postfix" % (tag))
        return False

    shaker.libs.logger.Logger().debug("github::is_tag_release: "
                                      "%s is release" % (tag))
    return True


def is_tag_prerelease(tag):
    """
    Simple check for a pre-release

    Args:
        tag(string): The tag in format v1.2.3-postfix

    Returns:
        bool: True if format is that of a pre-release,
            false otherwise
    """
    parsed_tag = parse_semver_tag(tag)
    valid_version_checks = (
        (parsed_tag["major"] is not None) and
        (parsed_tag["minor"] is not None) and
        (parsed_tag["patch"] is not None)
    )
    if valid_version_checks and parsed_tag["postfix"]:
        shaker.libs.logger.Logger().debug("github::is_tag_prerelease: "
                                          "%s is pre-release" % (tag))
        return True

    shaker.libs.logger.Logger().debug("github::is_tag_prerelease: "
                                      "%s is not pre-release" % (tag))
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

    # do we have a constraint?
    if constraint:
        # is it a branch or a tag?
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                          "constraint is not empty '%s'"
                                          % (org_name, formula_name, constraint))
        parsed_constraint = metadata.parse_constraint(constraint)
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                          "parsed_constraint '%s'"
                                          % (org_name, formula_name, str(parsed_constraint)))
        # is it a branch (i.e. not a version)
        if not parsed_constraint['version']:
            branch_name = parsed_constraint['tag']
            shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                              "There is no version, assuming this is "
                                              "a branch, name: '%s'"
                                              % (org_name, formula_name, branch_name))
            branch_data = get_branch_data(org_name, formula_name, branch_name)
            if not branch_data:
                raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                                    "github did not return any value for "
                                                    "branch '%s'"
                                                    % (org_name, formula_name, branch_name))
            return branch_data

    # carry on with version analyses
    wanted_tag, tag_versions, tags_data = get_valid_tags(org_name, formula_name)
    if not constraint or (constraint == ''):
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                          "No constraint specified, returning '%s'"
                                          % (org_name,
                                             formula_name,
                                             wanted_tag))
        obj = None
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                          "type of tags_data: %s"
                                          % (org_name,
                                             formula_name,
                                             type(tags_data)))
        for tag_data in tags_data:
            if tag_data["name"] == wanted_tag:
                obj = tag_data
                shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                                  "type of (note no s!) tag_data: %s"
                                                  % (org_name,
                                                     formula_name,
                                                     type(tag_data)))
                break
        shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                          "returning obj: '%s' type: %s"
                                          % (org_name,
                                             formula_name,
                                             str(obj), type(obj)))
        return obj

    parsed_constraint = metadata.parse_constraint(constraint)
    parsed_comparator = parsed_constraint['comparator']
    parsed_tag = parsed_constraint['tag']
    parsed_version = parsed_constraint['version']

    # See if we can pick up a version
    if tag_versions and parsed_version:
        if parsed_comparator == '==':
            if parsed_version in tag_versions:
                shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                                  "Found exact version '%s'"
                                                  % (org_name,
                                                     formula_name,
                                                     parsed_version))
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == parsed_tag:
                        obj = tag_data
                        break
                return obj
            else:
                raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                                    "Could not satisfy constraint for '%s', "
                                                    " version %s not in tag list %s"
                                                    % (org_name,
                                                       formula_name,
                                                       constraint,
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
                            shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                                              "Skipping pre-release version '%s'"
                                                              % (org_name,
                                                                 formula_name,
                                                                 tag_version))
                    else:
                        raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                                            " No non-prerelease version found %s"
                                                            % (org_name,
                                                               formula_name,
                                                               constraint))

            elif parsed_comparator == '<=':
                valid_version = None
                for tag_version in reversed(tag_versions):
                    if (tag_version <= parsed_version):
                        if not is_tag_prerelease(tag_version):
                            valid_version = tag_version
                            break
                        else:
                            shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                                              "Skipping pre-release version '%s'"
                                                              % (org_name,
                                                                 formula_name,
                                                                 tag_version))

                if not valid_version:
                    raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                                        " No non-prerelease version found '%s'"
                                                        % (org_name,
                                                           formula_name,
                                                           constraint))
            else:
                msg = ("github::resolve_constraint_to_object: "
                       "Unknown comparator '%s/%s%s'" % (org_name,
                                                         formula_name,
                                                         parsed_comparator))
                raise ConstraintResolutionException(msg)

            if valid_version:
                shaker.libs.logger.Logger().debug("github::resolve_constraint_to_object: %s/%s: "
                                                  "resolve_constraint_to_object:Found valid version '%s'"
                                                  % (org_name,
                                                     formula_name,
                                                     valid_version))
                valid_tag = 'v%s' % valid_version
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == valid_tag:
                        obj = tag_data
                        break

                return obj
            else:
                raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                                    'Constraint %s cannot be satisfied'
                                                    % (org_name,
                                                       formula_name,
                                                       constraint))
    else:
        msg = ("github::resolve_constraint_to_object: "
               "Unknown parsed constraint '%s' from '%s'" % (parsed_constraint, constraint))
        raise ConstraintResolutionException(msg)
    raise ConstraintResolutionException("github::resolve_constraint_to_object: %s/%s: "
                                        'Constraint {} cannot be satisfied'.format(org_name,
                                                                                   formula_name,
                                                                                   constraint))
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

            shaker.libs.logger.Logger().debug("github::get_valid_github_token:"
                                              "Calling validate_github_access with %s" % (str(response)))
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


def validate_github_access(response, url=None):
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
    shaker.libs.logger.Logger().debug("github::validate_github_access:starts here:response: %s"
                                      % str(response))

    if (type(response) == requests.models.Response):

        # Check the status codes for success
        if response.status_code == 200:
            shaker.libs.logger.Logger().debug("github::validate_github_access:Github access checked ok")
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
                    shaker.libs.logger.Logger().debug("github::validate_github_access: "
                                                      "URL %s not found" % url)
                else:
                    shaker.libs.logger.Logger().warning("validate_github_access: "
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
    try:
        credentials = pygit2.credentials.KeypairFromAgent(username)
    except AttributeError as e:
        pygit2_parse_error(e)

    # If local directory exists, then make a connection to it
    # Otherwise, clone the remote repo into the new directory
    if os.path.isdir(target_directory):
        shaker.libs.logger.Logger().debug("open_repository: "
                                          "Opening url '%s' "
                                          "with existing local repository '%s'"
                                          % (url, target_directory))
        repo = pygit2.Repository(target_directory)
    else:
        # Try to use pygit2 0.22 cloning
        try:
            shaker.libs.logger.Logger().debug("open_repository: "
                                              "Trying to open repository "
                                              "using pygit2 0.22 format")
            repo = pygit2.clone_repository(url,
                                           target_directory,
                                           credentials=credentials)
        except TypeError as e:
            shaker.libs.logger.Logger().debug("open_repository: "
                                              "Failed to detect pygit2 0.22")
            shaker.libs.logger.Logger().debug("open_repository: "
                                              "Trying to open repository "
                                              "using pygit2 0.23 format")
            # Try to use pygit2 0.23 cloning
            callbacks = pygit2.RemoteCallbacks(credentials)
            repo = pygit2.clone_repository(url,
                                           target_directory,
                                           callbacks=callbacks)

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
                   target_directory,
                   use_tag=False):
    """
    Install the requirement as specified by the formula dictionary and
    return the directory symlinked into the roots_dir. The sha revision
    will be checked out if specified, and if not, then the tag will be
    checked out if present

    Args:
        target_source(dictionary): A keyed collection of information about the
            source of the format
            {
                'name': '<target_name>',
                'url': '<target_url>',
                'sha': <sha revision to checkout>,
                'tag': <tag version to checkout>,
            }
        target_directory(string): THe directory to install into
        use_tag(bool): True to use the tag value for versioning,
            False otherwise
    """
    shaker.libs.logger.Logger().debug("install_source(%s, %s, %s)"
                                      % (target_source,
                                         target_directory,
                                         use_tag))
    target_name = target_source.get('name', None)
    target_url = target_source.get('source', None)
    target_sha = target_source.get('sha', None)
    target_tag = target_source.get('tag', None)

    target_path = os.path.join(target_directory,
                               target_name)
    shaker.libs.logger.Logger().debug("install_source: Opening %s in directory %s, "
                                      "with url %s, sha %s, tag %s"
                                      % (target_name,
                                         target_directory,
                                         target_url,
                                         target_sha,
                                         target_tag))
    target_repository = open_repository(target_url, target_path)

    if use_tag:
        if target_tag is None:
            shaker.libs.logger.Logger().error("github::install_source: Tag usage specified but is empty")
            return False
        # Look for tag, if not then look for branch
        try:
            parsed_tag = target_repository.revparse_single(target_tag)

            # If parsed tag refs a tag object, look for the actual commit object
            if parsed_tag.type == pygit2.GIT_OBJ_TAG:
                target_sha = parsed_tag.peel(pygit2.GIT_OBJ_COMMIT).hex
            else:
                target_sha = parsed_tag.hex

            shaker.libs.logger.Logger().debug("github::install_source: Found tag sha '%s' for tag '%s'"
                                              % (target_sha, target_tag))
        except KeyError:
            # Try to find the branch
            branch = target_repository.lookup_branch(("origin/%s" % target_tag),
                                                     pygit2.GIT_BRANCH_REMOTE)

            if branch is not None:
                target_repository.checkout(branch)
                parsed_tag = target_repository.revparse_single('HEAD')
                target_sha = parsed_tag.hex
            else:
                shaker.libs.logger.Logger().debug("github::install_source: "
                                                  "Could not find branch '%s', '%s'"
                                                  % (target_tag, branch))
                # We couldnt resolve this tag
                shaker.libs.logger.Logger().error("github::install_source: Could not find tag or branch %s"
                                                  % (target_tag))
                return False
    # Use the sha target if it exists, otherwise try the tag value
    else:
        if target_sha is None:
            shaker.libs.logger.Logger().error("github::install_source: Raw sha usage specified but is empty")
            return False

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
            return True
        else:
            shaker.libs.logger.Logger().debug("github::install_source: Found raw sha '%s'"
                                              % (target_sha))

    # We should have a sha now, use it to setup the repos
    target_oid = pygit2.Oid(hex=target_sha)

    target_repository.checkout_tree(target_repository[target_oid].tree)
    shaker.libs.logger.Logger().debug("github::install_source: Checking out oid '%s' in '%s"
                                      % (target_oid, target_path))
    # The line below is *NOT* just setting a value.
    # Pygit2 internally resets the head of the filesystem to the OID we set.
    target_repository.set_head(target_oid)

    if target_repository.head.get_object().hex != target_sha:
        shaker.libs.logger.Logger().debug("Resetting sha mismatch on source '%s'"
                                          % (target_name))
        target_repository.reset(target_sha, pygit2.GIT_RESET_HARD)

    shaker.libs.logger.Logger().debug("Source '%s' is at version '%s'"
                                      % (target_name, target_sha))
    return True


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
