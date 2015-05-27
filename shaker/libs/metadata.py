import shaker.libs.logger
import re
from shaker.libs.errors import (ConstraintFormatException,
                                ConstraintResolutionException,
                                ShakerRequirementsParsingException)
from parse import parse

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
        _, formula = dependency.split(':')[1].split('.git')[0].split('/')

        # Simply take the first formula found, ignore subsequent
        # formulas with the same name even from different organisations
        # Just warn, not erroring out
        if formula not in resolved_dependency_collection:
            resolved_dependency_collection[formula] = dependency
        else:
            # Do some sort of tag resolution
            count_duplicates += 1
            shaker.libs.logger.Logger().warning("resolve_metadata_duplicates: "
                                                "Skipping duplicate dependency %s"
                                                % (formula))

    # Only alter the metadata if we need to
    if count_duplicates > 0:
        resolved_dependencies = resolved_dependency_collection.values()
        metadata["dependencies"] = resolved_dependencies

    return metadata


def parse_constraint(constraint):
    """
    Parse a constraint of form
    into an info dictionary of form
    {'comparator': comparator, 'tag': tag, 'version': version, 'postfix': postfix}

    Args:
        constraint(string): The string representing the constratint

    Returns:
        dictionary: The information dictionary
    """
    match = comparator_re.search(constraint)
    comparator = match.group(1)
    tag = match.group(2)

    version = None
    postfix = None
    parsed_results = parse('v{version}-{postfix}', tag)
    if parsed_results:
        version = parsed_results["version"]
        postfix = parsed_results["postfix"]
    else:
        parsed_results = parse('v{version}', tag)
        if parsed_results:
            version = parsed_results["version"]
            postfix = None

    return {'comparator': comparator,
            'tag': tag,
            'version': version,
            'postfix': postfix}


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
        shaker.libs.logger.Logger().debug("metadata.resolve_constraints(%s, %s)"
                                          % (new_constraint,
                                             current_constraint))
        # Deal with simple cases first, if we have an empty
        # constraint and a non-empty one, use the non-empty
        # one, if both are empty then just no versioning
        # is required
        have_new_constraint = (new_constraint and (len(new_constraint) > 0))
        have_current_constraint = (current_constraint and (len(current_constraint) > 0))
        if not have_new_constraint and not have_current_constraint:
            return ''
        elif not have_new_constraint and have_current_constraint:
            return current_constraint
        elif have_new_constraint and not have_current_constraint:
            return new_constraint

        new_constraint_result = parse_constraint(new_constraint)
        current_constraint_result = parse_constraint(current_constraint)
        shaker.libs.logger.Logger().debug("metadata.resolve_constraints: %s\n%s\n"
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
                raise ConstraintResolutionException
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
                raise ConstraintFormatException(msg)
        else:
            msg = ("metadata.resolve_constraints: %s\n%s\n"
                   % (new_constraint_result,
                      current_constraint_result))
            raise ConstraintFormatException(msg)

        return None


def parse_metadata_requirements(metadata_dependencies):
    """
    Parse the supplied metadata requirements of the format,
    [
        'git@github.com:test_organisation/some-formula.git==v1.0',
        'git@github.com:test_organisation/another-formula.git==v2.0'
    ]
    or
    [
        'test_organisation/some-formula==v1.0',
        'test_organisation/another-formula==v2.0'
    ]
    and return them in the format,

    'test_organisation/some-formula':
        {
            'source': 'git@github.com:test_organisation/some-formula.git',
            'constraint': '==1.0',
            'sourced_constraints': ['==1.0'],
            'organisation': 'test_organisation',
            'name': 'some-formula'
        }

    Args:
        metadata_requirements(string): String of metadata requirements

    Return:
        dependencies(dictionary): A collection of details on the
        dependencies in the specified format

    """
    dependencies = {}
    for metadata_dependency in metadata_dependencies:
        # If we have a github url, then parse it, otherwise generate one
        # From the simplified format. Pass this to th github url parser
        # to ensure we are generating the same strucutres for both cases
        metadata_info = {}
        if (".git" in metadata_dependency or "git@" in metadata_dependency):
            shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                              "Parsing '%s' as raw github format\n"
                                              % (metadata_dependency))
            metadata_info = shaker.libs.github.parse_github_url(metadata_dependency)
        else:
            parsed_entry = re.search('(.*)([=><]{2})\s*(.*)', metadata_dependency)
            if parsed_entry and len(parsed_entry.groups()) >= 3:
                parsed_formula = parsed_entry.group(1).strip()
                parsed_comparator = parsed_entry.group(2).strip()
                parsed_version = parsed_entry.group(3).strip()
                shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                                  "parsed values for formula >%s< comparator >%s< version >%s<"
                                                  % (parsed_formula, parsed_formula, parsed_version))
                github_url = "git@github.com:{0}.git{1}{2}".format(parsed_formula,
                                                                   parsed_comparator,
                                                                   parsed_version)
                metadata_info = shaker.libs.github.parse_github_url(github_url)
                shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                                  "Parsing '%s' as simple format with constraint"
                                                  % (metadata_dependency))

            else:
                github_url = "git@github.com:%s.git" % (metadata_dependency)
                metadata_info = shaker.libs.github.parse_github_url(github_url)
                shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                                  "Parsing '%s' as simple format without constraint\n"
                                                  % (metadata_dependency))

        if metadata_info:
            dependency_entry = {
                'source': metadata_info.get('source', None),
                'constraint': metadata_info.get('constraint', None),
                'sourced_constraints': [],
                'organisation': metadata_info.get('organisation', None),
                'name': metadata_info.get('name', None)
            }
            # Look for problems
            format_check = (dependency_entry['source'] and
                            dependency_entry['organisation'] and
                            dependency_entry['name']
                            )
            if not format_check:
                msg = ("metadata::parse_metadata_requirements: "
                       "Parsing '%s' as simple format without constraint\n"
                       % (metadata_dependency))
                raise ShakerRequirementsParsingException(msg)

            dependency_key = "%s/%s" % (dependency_entry.get('organisation'),
                                        dependency_entry.get('name'))
            dependencies[dependency_key] = dependency_entry

            shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                              "Parsed entry %s %s\n from metadata: %s"
                                              % (metadata_dependency,
                                                 dependency_entry,
                                                 metadata_info))
        else:
            shaker.libs.logger.Logger().debug("metadata::parse_metadata_requirements: "
                                              "No data found for entry %s"
                                              % (metadata_info.get('source', None)))
    return dependencies


def compare_requirements(previous_requirements,
                         new_requirements):

    """
    Compare this objects requirements to another set
    of requirements

    Args:
        other_requirements(list): List of requirements of form,
            [
                some-organisation/some-formula==1.0.1,
                some-organisation/another-formula,
            ]

    Returns:
        list: List of differing formula requirements, in form for
        new, deprecated and unequal versions
            [
                ['', some-organisation/another-formula]
                [some-organisation/some-formula==1.0.1, '']
                [some-organisation/some-formula==1.0.1, some-organisation/another-formula]
            ]
    """
    diff = []
    parsed_first_requirements = shaker.libs.metadata.parse_metadata_requirements(new_requirements)
    parsed_other_requirements = shaker.libs.metadata.parse_metadata_requirements(previous_requirements)

    # Test for deprecated entries
    for other_requirement_name, other_requirement_info in parsed_other_requirements.items():
        other_requirement_constraint = other_requirement_info.get("constraint", None)
        other_requirement_line = ("%s%s" % (other_requirement_name, other_requirement_constraint))
        if other_requirement_name not in parsed_first_requirements.keys():
            entry = [other_requirement_line, '']
            diff.append(entry)
            shaker.libs.logger.Logger().debug("compare_requirements: Found deprecated entry '%s'"
                                              % (entry))
        else:
            first_requirement_info = parsed_first_requirements.get(other_requirement_name)
            first_requirement_constraint = first_requirement_info.get("constraint", None)
            first_requirement_line = ("%s%s" % (other_requirement_name, first_requirement_constraint))
            if first_requirement_constraint != other_requirement_constraint:
                entry = [other_requirement_line, first_requirement_line]
                diff.append(entry)
                shaker.libs.logger.Logger().debug("compare_requirements: Found version diff entry '%s'"
                                                  % (entry))
    # Test for new entries
    for first_requirement_name, first_requirement_info in parsed_first_requirements.items():
        if first_requirement_name not in parsed_other_requirements.keys():
            first_requirement_constraint = first_requirement_info.get("constraint", None)
            first_requirement_line = ("%s%s" % (first_requirement_name, first_requirement_constraint))
            entry = ['', first_requirement_line]
            diff.append(entry)
            shaker.libs.logger.Logger().debug("compare_requirements: Found new entry '%s'"
                                              % (first_requirement_info))

    return diff
