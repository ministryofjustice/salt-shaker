import errno
import os
import shutil

import shaker.libs.github
import shaker.libs.logger
from shaker.libs.errors import ConstraintResolutionException
import re
import yaml


class ShakerRemote:
    """
    Class to handle communication with remote repositories,
    resolving dependencies into downloads into local
    directories

    Attributes:
        _dependencies(list): A list of git repository targets
    """
    _dependencies = {}
    _targets = []
    _working_directory = ''
    _install_directory = ''
    _salt_root = ''
    _dynamic_modules_dirs = ['_modules', '_grains', '_renderers',
                             '_returners', '_states']

    def __init__(self,
                 dependencies,
                 working_directory='vendor',
                 install_directory='formula-repos',
                 salt_root='_root'):
        self._dependencies = dependencies
        self._working_directory = working_directory
        self._install_directory = install_directory
        self._salt_root = salt_root

    def update_dependencies(self):
        """
        Update the list of targets with actual git sha
        targets from the dictionary of dependencies
        """
        shaker.libs.logger.Logger().debug("ShakerRemote::update_dependencies: "
                                          "Updating the dependencies \n%s\n\n"
                                          % (self._dependencies.keys()))
        for dependency in self._dependencies.values():
            target_sha = self._resolve_constraint_to_sha(dependency)
            shaker.libs.logger.Logger().debug("ShakerRemote::update_dependencies: "
                                              "Found sha '%s'"
                                              % (target_sha))
            if target_sha:
                dependency["sha"] = target_sha

    def install_dependencies(self,
                             overwrite=False,
                             remove_directories=True,
                             enable_remote_check=False):
        """
        Install the dependency as specified by the formula dictionary and
        return the directory symlinked into the roots_dir

        Args:
            overwrite(bool): True if we will delete and recreate existing
                directories, False to preserve them
            remove_directories(bool): True to delete unused directories,
                False to preserve them
            enable_remote_check(bool): False to update repositories directly,
                True to contact github to find shas
        Returns:
            tuple: Tuple of successful, skipped repository updates
        """
        self._create_directories(overwrite=overwrite)
        successful_updates = 0
        unsuccessful_updates = 0
        install_dir = os.path.join(self._working_directory,
                                   self._install_directory)
        for dependency in self._dependencies.values():
            dependency_name = dependency.get("name", None)

            use_tag = False
            if not enable_remote_check:
                dependency_constraint = dependency.get("constraint", None)
                parsed_dependency_constraint = shaker.libs.metadata.parse_constraint(dependency_constraint)
                dependency_tag = parsed_dependency_constraint.get("tag", None)
                shaker.libs.logger.Logger().debug("ShakerRemote::install_dependencies: "
                                                  "No remote checks, found tag '%s'"
                                                  % (dependency_tag))
                if dependency_tag is not None:
                    dependency["tag"] = dependency_tag
                    use_tag = True
                else:
                    msg = ("ShakerRemote::install_dependencies: "
                           "No tag found when remote checks disabled")
                    raise ConstraintResolutionException(msg)
            else:
                shaker.libs.logger.Logger().debug("ShakerRemote::install_dependencies: "
                                                  "Remote checks enabled on dependency %s"
                                                  % (dependency))

            success = shaker.libs.github.install_source(dependency,
                                                        install_dir,
                                                        use_tag)
            shaker.libs.logger.Logger().debug("ShakerRemote::install_dependencies: "
                                              "Installed '%s to directory '%s': %s"
                                              % (dependency_name,
                                                 install_dir,
                                                 success))
            if success:
                successful_updates += 1
            else:
                unsuccessful_updates += 1

            success_message = "FAIL"
            if success:
                success_message = "OK"

            if (use_tag):
                shaker.libs.logger.Logger().info("ShakerRemote::install_dependencies: "
                                                 "Updating '%s' from tag '%s'...%s"
                                                 % (dependency_name,
                                                    dependency_tag,
                                                    success_message))
            else:
                shaker.libs.logger.Logger().info("ShakerRemote::install_dependencies: "
                                                 "Updating '%s' from raw sha '%s'...%s"
                                                 % (dependency_name,
                                                    dependency.get("sha", None),
                                                    success_message))
        if remove_directories:
            for pathname in os.listdir(install_dir):
                    found = False
                    for value in self._dependencies.values():
                        name = value.get("name", None)
                        if pathname == name:
                            found = True
                            break
                    if not found:
                        shaker.libs.logger.Logger().debug("ShakerRemote::install_dependencies: "
                                                          "Deleting directory on non-existent "
                                                          "dependency '%s'"
                                                          % (pathname))
                        fullpath = os.path.join(self._working_directory,
                                                self._install_directory,
                                                pathname)
                        shutil.rmtree(fullpath)

        # Do linking of modules
        self._update_root_links()
        return (successful_updates, unsuccessful_updates)

    def write_requirements(self,
                           output_directory='.',
                           output_filename='formula-requirements.txt',
                           overwrite=False,
                           backup=False):
        """
        Write out the resolved dependency list, into the file
        in the working directory. Skip overwrite unless forced

        Args:
            output_filename(string): The filename of the output file
            overwrite(bool): False to not ovewrite a pre-existing
                file, false otherwise.

        Returns:
            bool: True if file written, false otherwise
        """
        path = "%s/%s" % (output_directory,
                          output_filename)

        if os.path.exists(path):
            if not overwrite:
                shaker.libs.logger.Logger().warning('ShakerMetadata::write_requirements: '
                                                    ' File exists, not writing...')
                return False
            elif backup:
                # postfix = time.time()
                postfix = "last"
                newpath = "%s.%s" % (path, postfix)
                try:
                    os.rename(path, newpath)
                    shaker.libs.logger.Logger().info('ShakerMetadata::write_requirements: '
                                                     ' File exists, renaming %s to %s.'
                                                     % (path,
                                                        newpath))
                except OSError as e:
                    shaker.libs.logger.Logger().error('ShakerMetadata::write_requirements: '
                                                      ' Problem renaming file %s to %s: %s'
                                                      % (path,
                                                         newpath,
                                                         e.message))
                    return False

        with open(path, 'w') as outfile:
            requirements = self.get_requirements()
            outfile.write('\n'.join(requirements))
            outfile.write('\n')
            shaker.libs.logger.Logger().debug("ShakerMetadata::write_requirements: "
                                              "Wrote file '%s'"
                                              % (path)
                                              )
            return True

        return False

    def _get_formula_exports(self, dependency_info):
        """
        based on metadata.yml generates a list of exports
        if file is unreadable or exports are not supplied defaults to `re.sub('-formula$', '', name)`

        example metadata.yaml for formula foobar-formula
        ```
        exports:
        - foo
        - bar
        ```

        Returns:
            a list of directories from formula to link (exports supplied by formula)
        """
        name = dependency_info.get('name', None)
        exports_default = [re.sub('-formula$', '', name)]
        metadata_path = os.path.join(self._working_directory,
                                     self._install_directory,
                                     name, 'metadata.yml')
        try:
            with open(metadata_path, 'r') as metadata_file:
                metadata = yaml.load(metadata_file)
                shaker.libs.logger.Logger().debug("ShakerRemote::_get_formula_exports: metadata {}".format(metadata))
                exports = metadata.get("exports", exports_default)
        except IOError:
            shaker.libs.logger.Logger().debug("ShakerRemote::_get_formula_exports: skipping unreadable {}".format(
                metadata_path
            ))
            exports = exports_default
        shaker.libs.logger.Logger().debug("ShakerRemote::_get_formula_exports: exports {}".format(exports))
        return exports

    def _update_root_links(self):
        for dependency_info in self._dependencies.values():
            shaker.libs.logger.Logger().debug("ShakerRemote::update_root_links: "
                                              "Updating '%s"
                                              % (dependency_info))
            name = dependency_info.get('name', None)
            exports = self._get_formula_exports(dependency_info)
            # Let's link each export from this formula
            for export in exports:
                # Collect together a list of source directory paths to use for
                # our formula discovery an linking strategy
                subdir_candidates = [
                    {
                        "source": os.path.join(self._working_directory,
                                               self._install_directory,
                                               name,
                                               export
                                               ),
                        "target": os.path.join(self._working_directory,
                                               self._salt_root,
                                               export
                                               )
                    },
                    {
                        "source": os.path.join(self._working_directory,
                                               self._install_directory,
                                               name),
                        "target": os.path.join(self._working_directory,
                                               self._salt_root,
                                               name)
                    },
                ]
                subdir_found = False
                for subdir_candidate in subdir_candidates:
                    source = subdir_candidate["source"]
                    target = subdir_candidate["target"]
                    if os.path.exists(source):
                        if not os.path.exists(target):
                            subdir_found = True
                            relative_source = os.path.relpath(source, os.path.dirname(target))
                            os.symlink(relative_source, target)
                            shaker.libs.logger.Logger().info("ShakerRemote::update_root_links: "
                                                              "Linking %s to %s"
                                                              % (source, target))
                        else:
                            msg = ("ShakerRemote::update_root_links: "
                                   "Target '%s' conflicts with something else"
                                   % (target))
                            raise IOError(msg)

                        break

                # If we haven't linked a root yet issue an exception
                if not subdir_found:
                    msg = ("ShakerRemote::update_root_links: "
                           "Could not find target link for formula '%s'"
                           % (name))
                    raise IOError(msg)
                else:
                    self._link_dynamic_modules(name)

    def _link_dynamic_modules(self, dependency_name):
        shaker.libs.logger.Logger().debug("ShakerRemote::_link_dynamic_modules(%s) "
                                          % (dependency_name))

        repo_dir = os.path.join(self._working_directory, self._install_directory, dependency_name)

        for libdir in self._dynamic_modules_dirs:
            targetdir = os.path.join(self._working_directory,
                                     self._salt_root,
                                     libdir)
            sourcedir = os.path.join(repo_dir, libdir)

            relative_source = os.path.relpath(sourcedir, targetdir)

            if os.path.isdir(sourcedir):
                for name in os.listdir(sourcedir):
                    if not os.path.isdir(targetdir):
                        os.mkdir(targetdir)
                    sourcefile = os.path.join(relative_source, name)
                    targetfile = os.path.join(targetdir, name)
                    try:
                        shaker.libs.logger.Logger().debug("ShakerRemote::_link_dynamic_modules"
                                                          "linking %s"
                                                          % (sourcefile))
                        os.symlink(sourcefile, targetfile)
                    except OSError as e:
                        if e.errno == errno.EEXIST:  # already exist
                            shaker.libs.logger.Logger().warning("ShakerRemote::_link_dynamic_modules: "
                                                                "Not linking %s as link already exists"
                                                                % (sourcefile))
                        else:
                            raise

    def _resolve_constraint_to_sha(self,
                                   dependency):
        """
        Convert the dependencies version into a downloadable
        sha target
        """
        # Find our tags
        org = dependency.get('organisation', None)
        name = dependency.get('name', None)
        constraint = dependency.get('constraint', None)

        # Resolve the constraint to an actual tag
        target_obj = shaker.libs.github.resolve_constraint_to_object(org, name, constraint)
        if target_obj:
            dependency["version"] = target_obj['name']
            dependency["sha"] = target_obj["commit"]['sha']
            shaker.libs.logger.Logger().debug("_resolve_constraint_to_sha(%s) Found version '%s' and sha '%s'"
                                              % (dependency.get('name', ''),
                                                 dependency["version"],
                                                 dependency["sha"]))
            return dependency["sha"]

        return None

    def _create_directories(self, overwrite=False):
        """
        Make sure all our required directories are set up correctly
        """
        if not os.path.exists(self._working_directory):
            os.makedirs(self._working_directory, 0755)

        # Delete the salt roots dir on each run.
        # This is because the files in roots_dir are just symlinks
        salt_root_path = os.path.join(self._working_directory,
                                      self._salt_root)
        if os.path.exists(salt_root_path):
            shutil.rmtree(salt_root_path)
            shaker.libs.logger.Logger().debug("_create_directories: Deleting salt root directory '%s'"
                                              % (salt_root_path))
        os.makedirs(salt_root_path)

        # Ensure the repos_dir exists
        install_path = os.path.join(self._working_directory,
                                    self._install_directory)

        if not os.path.exists(install_path):
            try:
                shaker.libs.logger.Logger().debug("_create_directories: Creating repository directory '%s'"
                                                  % (install_path))
                os.makedirs(install_path)
            except OSError as e:
                    raise IOError("There was a problem creating the directory '%s', '%s'"
                                  % (install_path, e))
        elif overwrite and os.path.exists(install_path):
            shutil.rmtree(install_path)
            shaker.libs.logger.Logger().debug("_create_directories: Deleting repository directory '%s'"
                                              % (install_path))
            os.makedirs(install_path)

    def get_requirements(self):
        """
            Get a list of the requirements from the current
            dependency metadata

        Returns:
            (list): List of requirements or None type. Format is
                <organisation-name>/<formula-name>(comparator)
        """
        requirements = []
        if self._dependencies and len(self._dependencies) > 0:

            for key, info in self._dependencies.items():
                entry = ("%s==%s"
                         % (key,
                            info.get("version", "")
                            ))
                requirements.append(entry)

        return requirements
