import logging
import json
import requests
import os
import re

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
        msg = "No github token found. Please set your GITHUB_TOKEN environment variable"
        logging.error(msg)
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
    valid_credentials = False
    
    if (type(response) == requests.models.Response):
        
        # Check the status codes for success
        if response.status_code == 200:
            logging.info("Github access checked ok")
            valid_credentials = True
        else:
             # Set a default response message, use the real one if we
             # find it in the response 
            response_message = "No response found"
            try:
                # Access the responses body as json
                response_json = json.loads(response.text)
                if "message" in response_json: 
                    response_message = response_json["message"]
            except:
                # Just ignore if we can'l load json, its not essential here
                pass
                if (response.status_code == 401) and ("Bad credentials" in response_message):
                    logging.error("Github credentials incorrect: %s" % response_message)
                elif response.status_code == 403 and ("Maximum number of login attempts exceeded" in response_message):
                    logging.error("Github credentials failed due to lockout: %s" % response_message)
                else:
                    logging.error("Unknown problem checking credentials: %s" % response_message)
    
    return valid_credentials

def parse_metadata(metadata):
    """
    Entry function to handle the metadata parsing workflow and return a metadata 
    object which is cleaned up
    
    Args:
        metadata (dictionary): Keyed salt formula dependency information
    
    Returns:
        parsed_metadata (dictionary): The original metadata parsed and cleaned up
    """
    # Remove duplicates
    parsed_metadata = resolve_metadata_duplicates(metadata)
    return parsed_metadata
    
def resolve_metadata_duplicates(metadata):
    """
    Strip duplicates out of a metadata file. If we have no additional criteria, 
    simply take the first one. Or can resolve by latest version or preferred organisation
    if required
    
    Args:
        metadata (dictionary): Keyed salt formula dependency information
    
    Returns:
        resolved_dependencies (dictionary): The original metadata stripped of duplicates
            If the metadata could not be resolved then we return the original args version
    """ 
    # Only start to make alterations if we have a valid metadata format
    # Otherwise ignore and just return the one we were passed as an argument
    if metadata and (type(metadata) == type({})) and ("dependencies" in metadata):
        # Count the duplicates we find
        count_duplicates = 0
        
        resolved_dependency_collection = {}
        for dependency in metadata["dependencies"]:
            # Filter out formula name
            org, formula = dependency.split(':')[1].split('.git')[0].split('/')
            
            # Simply take the first formula found, ignore subsequent
            # formulas with the same name even from different organisations
            # Just warn, not erroring out
            if not formula in resolved_dependency_collection:
                resolved_dependency_collection[formula] = dependency 
            else:
                # Do some sort of tag resolution
                count_duplicates += 1
                logging.warning("resolve_metadata_duplicates: Skipping duplicate dependency %s" %(formula))
        
        # Only alter the metadata if we need to
        if count_duplicates > 0:   
            resolved_dependencies = resolved_dependency_collection.values()
            metadata["dependencies"] = resolved_dependencies
    return metadata
    
