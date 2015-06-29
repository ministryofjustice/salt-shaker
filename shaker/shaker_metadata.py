import os
import re
import requests
import yaml

from shaker.libs.errors import ShakerConfigException
from shaker.libs.errors import GithubRepositoryConnectionException
import shaker.libs.github
import shaker.libs.metadata
import shaker.libs.logger


class ShakerMetadata:
    """
    Class to hold and resolve all the information about
    a formula using it's metadata. It can parse a local
    metadata file, use this to generate a dependency list,
    and call remotely to parse sub-dependencies.

    Attributes:
        working_directory(string): The working directory
             to look for metadata files and to write output
        metadata_filename(string): The filename that stores
            our root metadata
        root_metadata(dictionary): Dictionary of information
            on the root formula, eg
            {
                formula: 'test_organisation/my-formula':
                'organisation': 'test_organisation',
                'name': 'my-formula',
                'dependencies': {
                    'test_organisation/some-formula':
                    {
                        'source': 'git@github.com:test_organisation/some-formula.git',
                        'constraint': '==1.0',
                        'organisation': 'test_organisation',
                        'name': 'some-formula'
                    }
                }
            }
            dependencies(dictionary): Dictionary of organisation/name
                keys to a dictionary of properties for the dependency,
                'source', the url source for the dependency
                'versions', the versions of the dependency available
                'constraint', the version constraint on the dependency
                     added in the order found, ie root first.
                'organisation', the organisation name
                'name', the formula name

                An example

                    {
                        'test_organisation/some-formula':
                        {
                            'source': 'git@github.com:test_organisation/some-formula.git',
                            'constraint': '==1.0',
                            'organisation': 'test_organisation',
                            'name': 'some-formula'
                        }
                    }
    """
    working_directory = None
    metadata_filename = None
    root_metadata = {}
    local_requirements = {}
    dependencies = {}

    def __init__(self,
                 working_directory='.',
                 metadata_filename='metadata.yml',
                 autoload=True):
        """
        Initialise the instance from a metadata config file

        Args:
            working_directory(string): The directory of the metadata file
            metadata_filename(string): The filename of the metadata file
            autoload(bool): If True, then try to load local data, do nothing
                on False
        """
        self.working_directory = working_directory
        self.metadata_filename = metadata_filename
        self.requirements_filename = metadata_filename
        if autoload:
            self.load_local_metadata()
            self.load_local_requirements()

    def load_local_metadata(self):
        """
        Load in the metadata from a file into our data
        structures
        """
        # Load in the raw metadata
        raw_data = self._fetch_local_metadata(self.working_directory,
                                              self.metadata_filename)
        # Process the raw data into our data structure
        if raw_data:
            root_name_key = raw_data.get('formula', None)
            if (root_name_key):
                self.root_metadata['formula'] = root_name_key
                self.root_metadata.update(self._parse_metadata_name(root_name_key))
            else:
                shaker.libs.logger.Logger().debug('ShakerMetadata::update_metadata: '
                                                  'No root key name found, '
                                                  'assuming a deploy formula')

            root_dependencies = raw_data.get('dependencies', None)
            if (root_dependencies):
                # Root dependencies need to be differentiated so they can be used a the basis
                # for a dependency refresh
                self.root_metadata['dependencies'] = shaker.libs.metadata.parse_metadata_requirements(root_dependencies)
            else:
                shaker.libs.logger.Logger().warning('ShakerMetadata::update_metadata: '
                                                    'No root dependencies found')
        else:
            msg = 'ShakerMetadata::update_metadata: Error loading metadata.'
            raise ShakerConfigException(msg)

    def update_dependencies(self,
                            ignore_local_requirements=False,
                            ignore_dependency_requirements=False):
        """
        Update the dependencies from the root formula down
        through the dependency chain

        Args:
            ignore_local_requirements(bool): True if we skip parsing the requirements file
                for the root and use metadata directly, false otherwise
            ignore_dependency_requirements(bool): True if we skip parsing the requirements file
                for the dependencies and use their metadata directly, false otherwise
        """
        # Try to read root requirements, unless we're ignoring them
        # If we are, or fail to read, open up metadata
        have_local_requirements = len(self.local_requirements) > 0
        if not ignore_local_requirements and have_local_requirements:
            shaker.libs.logger.Logger().debug('ShakerMetadata::update_dependencies: '
                                              'Updating from requirements')
            self.dependencies = self.local_requirements
            self._fetch_dependencies(self.dependencies,
                                     ignore_dependency_requirements)
        else:
            shaker.libs.logger.Logger().debug('ShakerMetadata::update_dependencies: '
                                              'Updating from metadata')
            # Add in root dependencies, always overwrite
            root_dependencies = self.root_metadata.get('dependencies', {})
            if len(root_dependencies) <= 0:
                shaker.libs.logger.Logger().debug("ShakerMetadata::update_dependencies: "
                                                  "No dependencies found in metadata")
            else:
                self.dependencies = root_dependencies
                self._fetch_dependencies(self.dependencies,
                                         ignore_dependency_requirements)

    def load_local_requirements(self,
                                input_directory='.',
                                input_filename='formula-requirements.txt'):
        """
        Load a dependency list from a file path, parsing it into our
        data structures. Expects a list inside
        the file of the form

        git@github.com:test_organisation/some-formula.git==v1.0
        git@github.com:test_organisation/another-formula.git==v2.0

        Args:
            input_directory(string): The directory of the input file
            input_filename(string): The filename of the input file
        """
        path = "%s/%s" % (input_directory,
                          input_filename)
        shaker.libs.logger.Logger().debug('ShakerMetadata::load_local_requirements: '
                                          'Loading %s...'
                                          % (path))
        if not os.path.exists(path):
            shaker.libs.logger.Logger().debug('ShakerMetadata::load_local_requirements: '
                                              'File not found %s'
                                              % (path))
            return False
        else:
            with open(path, 'r') as infile:
                loaded_dependencies = []
                for line in infile:
                    stripped_line = line.strip()
                    if len(stripped_line) > 0 and stripped_line[0] != '#':
                        loaded_dependencies.append(line)

            if len(loaded_dependencies) > 0:
                self.local_requirements = shaker.libs.metadata.parse_metadata_requirements(loaded_dependencies)
                return True
            else:
                shaker.libs.logger.Logger().warning("ShakerMetadata::load_local_requirements: "
                                                    "File '%s' empty %s"
                                                    % (path,
                                                       loaded_dependencies))
                return False

        return True

    def _fetch_local_metadata(self,
                              directory,
                              filename):
        """
        Fetch data from a local file

        Args:
            directory(string): The directory of the file
            filename(string): The filename of the file

        Returns:
            dictionary: The data found, None if could not be parsed
        """
        md_file = os.path.join(directory,
                               filename)
        if os.path.exists(md_file):
            with open(md_file, 'r') as md_fd:
                try:
                    data = yaml.load(md_fd)
                    return data
                except yaml.YAMLError as e:
                    msg = ('ShakerMetadata::_fetch_local_metadata: '
                           'Error in yaml format for file '
                           '%s: %s'
                           % (md_file,
                              e.message))
                    raise yaml.YAMLError(msg)
        else:
            msg = ('ShakerMetadata::_fetch_local_metadata: '
                   'Error loading file, '
                   'file does not exist. '
                   '%s'
                   % (md_file))
            raise IOError(msg)

        return None

    def _parse_metadata_name(self,
                             metadata_name):
        """
        Parse the supplied metadata name and return the root name entry
        in format,
        {
            'organisation': 'test_organisation',
            'name': 'my-formula'
        }

        Args:
            metadata_name(string): String of metadata name

        Returns:
            root_name_entry(dictionary): The root name entry found
                in the specified format
        """
        # Check that the metadata name string is in an expected
        # format
        if '/' not in metadata_name:
            raise ShakerConfigException("ShakerMetadata::_parse_metadata_name: "
                                        "No '/' separator found in string '%s'"
                                        % (metadata_name)
                                        )
        else:
            metadata_info = metadata_name.split('/')
            if len(metadata_info) != 2:
                raise ShakerConfigException("ShakerMetadata::_parse_metadata_name: "
                                            "Bad name format found in string '%s', "
                                            "expected '<organisation>/<formula-name>"
                                            % (metadata_name))
            else:
                root_org = metadata_info[0]
                root_name = metadata_info[1]
                root_name_entry = {
                    'organisation': root_org,
                    'name': root_name
                }
                return root_name_entry

        return None

    def _fetch_dependencies(self,
                            base_dependencies,
                            ignore_dependency_requirements=False):
        """
        Fetch all of the base formulas dependencies and sub-dependencies
        and process them into our data structures

        Args:
            base_dependencies(dictionary):
                A metadata dictionary to use as the base of our
                dependency loading of form
                'test_organisation/some-formula':
                {
                    'source': 'git@github.com:test_organisation/some-formula.git',
                    'constraint': '==1.0',
                    'sourced_constraints': ['==1.0'],
                    'organisation': 'test_organisation',
                    'name': 'some-formula'
                },
                'test_organisation/another-formula':
                {
                    'source': 'git@github.com:test_organisation/another-formula.git',
                    'constraint': '==1.0',
                    'sourced_constraints': ['==1.0'],
                    'organisation': 'test_organisation',
                    'name': 'another-formula'
                }
            ignore_dependency_requirements(bool):
                True if we want to skip parsing a remote requirements file
                and go straight to metadata, False otherwise
        """
        shaker.libs.logger.Logger().debug('ShakerMetadata::fetch_dependencies: '
                                          'Fetching for base dependencies\n %s'
                                          % base_dependencies)
        root_metadata = self.root_metadata.get('formula', None)
        for dependency_key, dependency_info in base_dependencies.items():
                shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                  "Processing '%s': "
                                                  % (dependency_key))
                constraint = dependency_info.get('constraint', '')

                if dependency_key in self.dependencies:
                    # If we've already sourced this constrained version then we're done
                    sourced_constraints = self.dependencies.get(dependency_key).get('sourced_constraints', [])
                    if constraint in sourced_constraints:
                        shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                          "Already have requirements constraint, '%s' in "
                                                          "sourced constraints '%s'"
                                                          % (constraint,
                                                             sourced_constraints))
                        continue

                    elif dependency_key == root_metadata:
                        shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                          "Root key dependency found %s = %s, skipping"
                                                          % (dependency_key, root_metadata))
                        continue

                # We've checked whether we have this dependency, and whether we
                # need to skip it. So now get it
                org_name = dependency_info.get('organisation', None)
                formula_name = dependency_info.get('name', None)

                shaker.libs.logger.Logger().debug('ShakerMetadata::fetch_dependencies: '
                                                  'Processing %s' % dependency_key)

                # Try to fetch the formula requirements file, if its not found,
                # fallback to fetching the metadata directly
                remote_metadata = None
                if not ignore_dependency_requirements:
                    shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                      "Looking for requirements for %s:%s"
                                                      % (dependency_key, constraint))
                    remote_requirements = self._fetch_remote_requirements(org_name,
                                                                          formula_name,
                                                                          constraint=constraint)

                    if remote_requirements:
                        shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                          "Found requirements %s"
                                                          % (remote_requirements))
                        remote_metadata = {"dependencies": remote_requirements}

                if not remote_metadata:
                    shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                      "Looking for metadata for %s"
                                                      % (dependency_key))
                    remote_metadata = self._fetch_remote_metadata(org_name,
                                                                  formula_name,
                                                                  constraint=constraint)

                # Need to ensure we don't try to re-get this one
                constraint = dependency_info.get('constraint', '')
                # we've tried all our methods of sourcing this requirement, so update the
                # sourced requirements
                self._add_dependency_sourced(dependency_key, constraint)

                if remote_metadata:
                    remote_dependencies = self._add_dependencies_from_metadata(remote_metadata)
                    self._fetch_dependencies(remote_dependencies)

                else:
                    shaker.libs.logger.Logger().debug("ShakerMetadata::fetch_dependencies: "
                                                      "No requirements or metadata found for %s, skipping"
                                                      % (dependency_key))

    def _fetch_remote_metadata(self,
                               org_name,
                               formula_name,
                               constraint=None):
        """
        Use a organisation, formula name and optional
        constraint to fetch the metadata for a formula

        Args:
            org_name(string): The name of the organisation
            formula_name(string): The name of the formula
            constraint(string): (optional) Constraint of the
                formula. In '==v1.0.0' type format

        Returns:
            (dictionary): The loaded metadata of the required
                formula, None type if there was a problem
        """
        github_token = shaker.libs.github.get_valid_github_token()
        if not github_token:
            msg = "github::get_branch_data: No valid github token"
            raise GithubRepositoryConnectionException(msg)

        shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_metadata: "
                                          "Fetching remote repository "
                                          "%s/%s:%s"
                                          % (org_name,
                                             formula_name,
                                             constraint))
        # Check for successful access and any credential problems
        metadata = self._fetch_remote_file(org_name,
                                           formula_name,
                                           "metadata.yml",
                                           constraint)

        data = None
        if metadata:
            data = yaml.load(metadata)
            parsed_data = self._parse_metadata_name(data)
            parsed_data["dependencies"] = shaker.libs.metadata.parse_metadata_requirements(data)
            for dependency_info in parsed_data["dependences"].values():
                dependency_info['sourced_constraints'] = dependency_info.get('constraint', '')
                shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_metadata: "
                                                  "Added sourced constraint '%s'"
                                                  % (dependency_info))
            return data
        else:
            shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_metadata: "
                                              "No metadata found for "
                                              "%s/%s:%s"
                                              % (org_name,
                                                 formula_name,
                                                 constraint))

    def _fetch_remote_requirements(self,
                                   org_name,
                                   formula_name,
                                   constraint=None):
        """
        Use a organisation, formula name and optional
        constraint to fetch the requiremtns for a formula

        Args:
            org_name(string): The name of the organisation
            formula_name(string): The name of the formula
            constraint(string): (optional) Constraint of the
                formula. In '==v1.0.0' type format

        Returns:
            (dictionary): The loaded dependencies of the required
                formula, eg,
                    'test_organisation/some-formula':
                    {
                        'source': 'git@github.com:test_organisation/some-formula.git',
                        'constraint': '==1.0',
                        'sourced_constraints': ['==1.0', '<=2.0.0'],
                        'organisation': 'test_organisation',
                        'name': 'some-formula'
                    }
                None type if the repo has no requirements file or if there was a problem.
        """
        # Check for successful access and any credential problems
        raw_requirements = self._fetch_remote_file(org_name,
                                                   formula_name,
                                                   "formula-requirements.txt",
                                                   constraint)
        parsed_data = None
        if raw_requirements:
            data = raw_requirements.split()
            if data:
                parsed_data = shaker.libs.metadata.parse_metadata_requirements(data)
                shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_requirements: "
                                                  "Found parsed_data %s"
                                                  % (parsed_data))
                for entry_info in parsed_data.values():
                    entry_info['sourced_constraints'] = [entry_info.get('constraint', '')]
                    shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_requirements: "
                                                      "Added sourced constraint '%s'"
                                                      % (entry_info))
                return parsed_data
            else:
                msg = ("ShakerMetadata::_fetch_remote_requirements: "
                       "Could not parse requirements found for %s/%s\n%s\n\n"
                       % (org_name, formula_name, raw_requirements))
                raise ShakerConfigException(msg)
        else:
            msg = ("ShakerMetadata::_fetch_remote_requirements: "
                   "No requirements found for %s/%s"
                   % (org_name, formula_name))
            shaker.libs.logger.Logger().debug(msg)

    def _fetch_remote_file(self,
                           org_name,
                           formula_name,
                           remote_file,
                           constraint=None):
        """
        Use a organisation, formula name and optional
        constraint to fetch the requirements for a formula

        Args:
            org_name(string): The name of the organisation
            formula_name(string): The name of the formula
            remote_file(string): The requirements file
                of the formula
            constraint(string): (optional) Constraint of the
                formula. In '==v1.0.0' type format

        Returns:
            (dictionary): The loaded metadata of the required
                formula, None type if there was a problem
        """
        github_token = shaker.libs.github.get_valid_github_token()
        if not github_token:
            msg = "github::get_branch_data: No valid github token"
            raise GithubRepositoryConnectionException(msg)

        target_obj = shaker.libs.github.resolve_constraint_to_object(org_name, formula_name, constraint)
        if not target_obj:
            msg = ("ShakerMetadata::_fetch_remote_file: "
                   "%s/%s:%s: No target object found, check it exists "
                   "and you have the environment variable GITHUB_TOKEN set "
                   "for authenticated access to private repositories"
                   % (org_name, formula_name, constraint))
            raise GithubRepositoryConnectionException(msg)

        target_tag = target_obj.get("name", None)

        remote_file_url = ("https://raw.githubusercontent.com/%s/%s/%s/%s"
                           % (org_name,
                              formula_name,
                              target_tag,
                              remote_file))

        # Check for successful access and any credential problems
        raw_data = requests.get(remote_file_url,
                                auth=(github_token, 'x-oauth-basic')
                                )
        shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_file: "
                                          "Calling github.validate_github_access with raw_data: " + str(raw_data)) 
        if shaker.libs.github.validate_github_access(raw_data,remote_file_url):
            remote_dict = yaml.load(raw_data.content)
            return remote_dict
        else:
            shaker.libs.logger.Logger().debug("ShakerMetadata::_fetch_remote_file: "
                                              "Could not validate github access to '%s'"
                                              % (remote_file_url))
        return None

    def _add_dependencies_from_metadata(self, metadata):
        """
        Load in dependencies from a dictionary of form
        'dependencies': {
                    'test_organisation/some-formula':
                    {
                        'source': 'git@github.com:test_organisation/some-formula.git',
                        'constraint': '==1.0',
                        'sourced_constraints: [],
                        'organisation': 'test_organisation',
                        'name': 'some-formula'
                    }
                }
        """
        shaker.libs.logger.Logger().debug("ShakerMetadata::_add_dependencies_from_metadata: "
                                          "Adding  metadata: %s"
                                          % (metadata))
        parsed_metadata_dependencies = {}
        if metadata:
            metadata_dependencies = metadata.get('dependencies',
                                                 None)
            if metadata_dependencies:
                parsed_metadata_dependencies = shaker.libs.metadata.parse_metadata_requirements(metadata_dependencies)
                for dep_key, dep_info in parsed_metadata_dependencies.items():
                    if dep_key != self.root_metadata.get('formula', None):
                        if dep_key not in self.dependencies:
                            shaker.libs.logger.Logger().debug("ShakerMetadata::_add_dependencies_from_metadata: "
                                                              "New Metadata added '%s"
                                                              % (dep_key))
                            self.dependencies[dep_key] = dep_info
                        else:
                            # Resolve constraints
                            current_constraint = self.dependencies[dep_key].get('constraint', {})
                            new_constraint = dep_info.get('constraint', None)
                            self.dependencies[dep_key]['constraint'] = shaker.libs.metadata.resolve_constraints(new_constraint,
                                                                                                                current_constraint)
                            shaker.libs.logger.Logger().debug("ShakerMetadata::_add_dependencies_from_metadata: "
                                                              "Updating constraint for '%s"
                                                              % (dep_key))
                            # Merge source constraints
                            current_sourced_constraints = self.dependencies[dep_key].get('sourced_constraints', [])
                            new_sourced_constraints = dep_info.get('sourced_constraints', [])
                            self.dependencies[dep_key]['sourced_constraints'] = current_sourced_constraints + new_sourced_constraints
                            shaker.libs.logger.Logger().debug("ShakerMetadata::_add_dependencies_from_metadata: "
                                                              "Merged sourced constraints\n"
                                                              "'%s' + '%s' = '%s'"
                                                              % (current_sourced_constraints,
                                                                 new_sourced_constraints,
                                                                 self.dependencies[dep_key]['sourced_constraints']))
                    else:
                        shaker.libs.logger.Logger().debug("ShakerMetadata::_add_dependencies_from_metadata: "
                                                          "Root key found (%s==%s), ignoring"
                                                          % (dep_key,
                                                             self.root_metadata.get('formula', None)))

            else:
                shaker.libs.logger.Logger().warning("ShakerMetadata::_add_dependencies_from_metadata: "
                                                    "Metadata contained no dependencies")
        else:
            shaker.libs.logger.Logger().error("ShakerMetadata::_add_dependencies_from_metadata: "
                                              "Metadata null")

            raise ShakerConfigException

        return parsed_metadata_dependencies

    def _add_dependency_sourced(self,
                                dependency_key,
                                constraint):
        """
        Mark a dependency constraint version as being sourced

        Args:
            dependency_key(string): The key name of the dependency
            constraint(string): The constraint that has been sourced
        """
        # Need to ensure we don't try to re-get this one
        # If we've already sourced this constrained version then we're done
        sourced_constraints = [constraint]
        if dependency_key in self.dependencies:
            current_sourced_constraints = self.dependencies.get(dependency_key).get('sourced_constraints', None)
            if current_sourced_constraints:
                sourced_constraints = sourced_constraints + current_sourced_constraints
        else:
            self.dependencies[dependency_key] = {}

        self.dependencies[dependency_key]["sourced_constraints"] = sourced_constraints
