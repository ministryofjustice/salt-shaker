import logging
import json
import requests
import os
import re
from shaker.libs import errors

logging.getLogger(__name__).setLevel(logging.DEBUG)
comparator_re = re.compile('([=><]+)\s*(.*)')
tag_re = re.compile('v[0-9]+\.[0-9]+\.[0-9]+')

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
    # Otherwise throw an exception

    # If metadata is not a dictionary or does not contain
    # a dependencies field then throw an exception
    if not (isinstance(metadata, type({}))):
        raise TypeError("resolve_metadata_duplicates: Metadata is not a "
                        "dictionary but type '%s'" % (type(metadata)))
    elif not ("dependencies" in metadata):
        raise IndexError("resolve_metadata_duplicates: Metadata has "
                         "no key called 'dependencies'"
                         )
    # Count the duplicates we find
    count_duplicates = 0

    resolved_dependency_collection = {}
    for dependency in metadata["dependencies"]:
        # Filter out formula name
        org, formula = dependency.split(':')[1].split('.git')[0].split('/')

        # Simply take the first formula found, ignore subsequent
        # formulas with the same name even from different organisations
        # Just warn, not erroring out
        if formula not in resolved_dependency_collection:
            resolved_dependency_collection[formula] = dependency 
        else:
            # Do some sort of tag resolution
            count_duplicates += 1
            logging.getLogger('helpers').warning("resolve_metadata_duplicates: Skipping duplicate dependency %s" %(formula))

    # Only alter the metadata if we need to
    if count_duplicates > 0:
        resolved_dependencies = resolved_dependency_collection.values()
        metadata["dependencies"] = resolved_dependencies

    return metadata


def parse_constraint(constraint):
    """
    Parse a constraint of form
    into an info dictionary of form
    {'comparator': comparator, 'tag': tag, 'version': version}
    
    Args:
        constraint(string): The string representing the constratint
    
    Returns:
        dictionary: The information dictionary
    """
    match = comparator_re.search(constraint)
    comparator = match.group(1)
    tag = match.group(2)
    version_match = re.search('^v(.*)', tag)
    version = None
    if version_match:
        version = version_match.group(1)
    return {'comparator': comparator, 'tag': tag, 'version': version}


def resolve_constraints(new_constraint,
                        current_constraint):
        """
        Resolve the dependencies uniquely using the precedence ==, >=, <=
        i.e,
        * '==' Equality takes priority over all other constraints, current
            equalities override any new
        * '>=' The highest greater than bound takes precedence over the lower
        * '<=' least less-than bound takes precedence over the higher
        * '>=, <=' Opposite contraints will throw an exception, although these
            may be resolvable in practice

        Args:
            new_constraint(string): New comparator and version 
            current_constraint(string): Current comparator and version
        
        Returns:
            string: The constraint that took precedence
            
        Raises:
            ConstraintFormatException
            ConstraintResolutionException
        """
        
        # Deal with simple cases first, if we have an empty
        # constraint and a non-empty one, use the non-empty 
        # one, if both are empty then just no versioning
        # is required
        if not new_constraint and not current_constraint:
            return ''
        elif not new_constraint and current_constraint:
            return current_constraint
        elif new_constraint and not current_constraint:
            return new_constraint
        
        new_constraint_result = parse_constraint(new_constraint)
        current_constraint_result = parse_constraint(current_constraint)
        logging.getLogger('helpers').debug("metadata.resolve_constraints: %s\n%s\n" 
                                           % (new_constraint_result,
                                           current_constraint_result))
        if new_constraint_result and current_constraint_result:
            new_comparator = new_constraint_result["comparator"]
            current_comparator = current_constraint_result["comparator"]
            # Deal with equality case
            if current_comparator == '==':
                return current_constraint
            elif new_comparator == '==':
                return new_constraint
            elif new_comparator != current_comparator:
                raise errors.ConstraintResolutionException
            elif new_comparator == '>=':
                # Get highest version
                version = max(new_constraint_result["tag"],
                              current_constraint_result["tag"])
                return '>=%s' % (version)
            elif new_comparator == '<=':
                # Get highest version
                version = min(new_constraint_result["tag"],
                              current_constraint_result["tag"])
                return '<=%s' % (version)
            else:
                msg = ("metadata.resolve_constraints: %s\n%s\n" 
                       % (new_constraint_result,
                          current_constraint_result))
                raise errors.ConstraintFormatException(msg)
        else:
            msg = ("metadata.resolve_constraints: %s\n%s\n" 
                       % (new_constraint_result,
                       current_constraint_result))
            raise errors.ConstraintFormatException(msg)

        return None