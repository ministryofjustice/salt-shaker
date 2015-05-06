import logging
import json
import requests
import os
import re
import sys
from parse import parse
import urlparse
import pygit2
import time
from datetime import datetime
import base64

import metadata
from errors import ConstraintResolutionException

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
        info(dictionary): A dictionary of information
            about the url of the form
            {
                'source': <source>,
                'name': <name>,
                'organisation': <organisation>,
                'constraint': <constraint>
            }
    """
    github_root = "git@github.com:"
    logging.getLogger('salt-shaker').debug("github::parse_github_url: "
                                           " Parsing '%s'"
                                           % (url))
    constraint = ''
    result = None
    have_constraint = False
    try:
        have_constraint = url.split('.git')[1] != ''
    except IndexError as e:
        msg = ("github::parse_github_url: Could not split url '%s'"
               % (url))
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


def get_tags(org_name, formula_name):
    def convert_tagname(tag):
        try:
            retag = None
            if '-' in tag:
                parsed_tag = tag.split('-')
                semver_tag = parsed_tag[0]
                postfix_tag = parsed_tag[1]
                rettag = map(int, semver_tag.split('.'))
                rettag.append(postfix_tag)
            else:
                rettag = map(int, tag.split('.'))


            logging.getLogger(__name__).debug("helpers.github::get_tags: "
                                             "Converted tag %s to %s"
                                             % (tag, rettag))
            return rettag
        except ValueError:
            logging.getLogger(__name__).warn("helpers.github::get_tags: "
                                             "Invalid tag %s'"
                                             % (tag))
            return []


    github_token = get_valid_github_token()
    if not github_token:
        logging.error("helpers.github::get_tags: No valid github token")
        sys.exit(1)

    tags_url = ('https://api.github.com/repos/%s/%s/tags'
                % (org_name, formula_name))
    tag_versions = []
    tags_json = requests.get(tags_url,
                             auth=(github_token, 'x-oauth-basic'))
    # Check for successful access and any credential problems
    
    if validate_github_access(tags_json):
        try:
            tags_data = json.loads(tags_json.text)
            tag_versions = [x['name'][1:] for x in tags_data]
            tag_versions.sort(key=convert_tagname)
            wanted_tag = 'v{0}'.format(tag_versions[-1])
        except ValueError as e:
            msg = ("helpers.github::get_tags: Invalid json for url '%s'"
                   % (tags_url))
            raise ValueError(msg)
    else:
        wanted_tag = 'master'
    
    logging.getLogger(__name__).debug("get_tags(%s, %s) => %s, %s"
                                      % (org_name, formula_name, wanted_tag, tag_versions))
    return wanted_tag, tag_versions, tags_data


def resolve_constraint_to_object(org_name, formula_name, constraint):
    """ 
    For a given formula, take the constraint and compare it to 
    the repositories available tags. Then try to find a tag that
    best resolves within the constraint
    """
    logging.getLogger('helpers.github').debug("resolve_constraint_to_tag(%s, %s, %s)"
                                              % (org_name, formula_name, constraint))
    wanted_tag, tag_versions, tags_data = get_tags(org_name, formula_name)
    
    if not constraint or (constraint == ''):
        logging.getLogger('helpers.github').debug("No constraint specified, returning '%s'"
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
                logging.getLogger('helpers.github').debug("Found exact version '%s'"
                                                          % (parsed_version))
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == parsed_tag:
                        obj = tag_data
                        break
                return obj
            else:
                raise ConstraintResolutionException("Could not satisfy constraint '%s', "
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
                for tag_version in tag_versions:
                    if (tag_version >= parsed_version):
                        valid_version = tag_version
                        break
        
            elif parsed_comparator == '<=':
                for tag_version in reversed(tag_versions):
                    if (tag_version <= parsed_version):
                        valid_version = tag_version
                        break
            else:
                msg = ("Unknown comparator '%s'" % (parsed_comparator))
                raise ConstraintResolutionException(msg)
                
            if valid_version:
                logging.getLogger('helpers.github').debug("resolve_constraint_to_object:Found valid version '%s'"
                                                          % (valid_version))
                valid_tag = 'v%s' % valid_version
                obj = None
                for tag_data in tags_data:
                    if tag_data["name"] == valid_tag:
                        obj = tag_data
                        break

                return obj
            else:
                raise ConstraintResolutionException('Constraint %s cannot be satisfied for %s/%s'
                                                    % (constraint, org_name, formula_name))
    else:
        msg = ("Unknown parsed constraint '%s' from '%s'" % (parsed_constraint, constraint))
        raise ConstraintResolutionException(msg)
    raise ConstraintResolutionException('Constraint {} cannot be satisfied for {}/{}'.format(
                                                                                             constraint, org_name, formula_name))
    
    return None

def get_valid_github_token(online_validation_enabled = False):
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
    if not "GITHUB_TOKEN" in os.environ:
        logging.error("No github token found. Please set your GITHUB_TOKEN environment variable")
    else:
        # Test an oauth call to the api, make sure the credentials are
        # valid and we're not locked out
        if online_validation_enabled:
            url = "https://api.github.com"
            response = requests.get(url,
                             auth=(os.environ["GITHUB_TOKEN"], 'x-oauth-basic'))

            # Validate the response against expected status codes
            # Set the return value to the token if we have success
            valid_response = validate_github_access(response)
            if valid_response:
                github_token = os.environ["GITHUB_TOKEN"]
                logging.error("No valid repsonse from github token '%s'"
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
            logging.info("Github access checked ok")
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
                logging.debug("Github credentials test got response: %s" % response_json)
            except:
                # Just ignore if we can'l load json, its not essential here
                if (response.status_code == 401) and ("Bad credentials" in response_message):
                    logging.error("validate_github_access: "
                                  "Github credentials incorrect: %s" % response_message)
                elif response.status_code == 403 and ("Maximum number of login attempts exceeded" in response_message):
                    logging.error("validate_github_access: "
                                  "Github credentials failed due to lockout: %s" % response_message)
                elif response.status_code == 404:
                    logging.error("validate_github_access: "
                                  "URL not found")
                else:
                    logging.error("validate_github_access: "
                                  "Unknown problem checking credentials: %s" % response)
    else:
        logging.error("Invalid response: %s" % response)

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
        logging.getLogger(__name__).info("open_repository: "
                     "Opening url '%s' with existing local repository '%s'"
                     % (url, target_directory))
        repo = pygit2.Repository(target_directory)
    else:
        repo = pygit2.clone_repository(url,
                                       target_directory,
                                       credentials=credentials)
        logging.getLogger(__name__).info(":open_repository: "
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
    logging.getLogger(__name__).debug("install_source: Opening %s in directory %s, "
                                     "with url %s, and sha %s"
                                     % (target_name,
                                        target_directory,
                                        target_url,
                                        target_sha))
    target_repository = open_repository(target_url, target_path)

    oid = pygit2.Oid(hex=target_sha)
    target_repository.checkout_tree(target_repository[oid].tree)
    logging.getLogger(__name__).info("install_source: Checking out sha '%s' into '%s"
                  % (target_sha, target_path))
    # The line below is *NOT* just setting a value.
    # Pygit2 internally resets the head of the filesystem to the OID we set.
    #
    #
    # In other words .... *** WARNING: MAGIC IN PROGRESS ***
    target_repository.set_head(oid)

    if target_repository.head.get_object().hex != target_sha:
        logging.info("Resetting sha mismatch on source '%s'"
                                                        % (target_name))
        target_repository.reset(target_sha, pygit2.GIT_RESET_HARD)
        # repo.head.reset(commit=sha, index=True, working_tree=True)

    logging.getLogger('helpers.github').info("Source '%s' is at version '%s'"
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
    target_sha = target_source.get('sha', None)
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
            logging.getLogger(__name__).debug("resolve_tag_to_sha: "
                                                      "Found sha '%s' for tag '%s'"
                                                      % (sha, tag_ref))
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
                logging.getLogger(__name__).debug("resolve_tag_to_sha: "
                                                      "Found sha '%s' for branch '%s'"
                                                      % (sha, tag_ref))
                return sha

        # Could just be a SHA
        try:
            sha = repository.revparse_single(target_version).hex
            logging.getLogger(__name__).debug("resolve_tag_to_sha: "
                                              "Found direct reference to sha '%s'"
                                              % (sha))
            return sha
        except KeyError:
            # Maybe we just need to fetch first.
            pass
        
        logging.getLogger(__name__).debug("resolve_tag_to_sha: "
                                                      "Cannot find version '%s' in refs '%s'"
                                                      % (target_version, refs))
    return None

def get_repository_info(repository):
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
                objects['tree'].append({
                'hex': obj.hex,
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
