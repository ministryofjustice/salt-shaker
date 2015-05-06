import shaker.libs.logger
import shaker.libs.github
import os
import shutil


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
    _logger = None
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
        self._logger = shaker.libs.logger.Logger()

    def update_dependencies(self):
        """
        Update the list of targets with actual git sha
        targets from the dictionary of dependencies
        """
        self._logger.info("ShakerRemote::update_dependencies: "
                          "Updating the dependencies \n%s\n\n"
                          % (self._dependencies))
        for dependency in self._dependencies.values():
            target_sha = self._resolve_constraint_to_sha(dependency)
            self._logger.info("ShakerRemote::update_dependencies: "
                             "Found sha '%s'"
                             % (target_sha))
            if target_sha:
                dependency["sha"] = target_sha

    def install_dependencies(self, overwrite=False):
        """
        Install the dependency as specified by the formula dictionary and
        return the directory symlinked into the roots_dir
        """
        self._create_directories(overwrite=overwrite)
        for dependency in self._dependencies.values():
            dependency_name = dependency.get("name", None)
            install_dir = os.path.join(self._working_directory,
                                       self._install_directory)
            shaker.libs.github.install_source(dependency,
                                                 install_dir)
            self._logger.info("ShakerRemote::install_dependencies: "
                              "Installed '%s to directory '%s'"
                              % (dependency_name,
                                 install_dir))
            
    def write_requirements(self,
                           output_directory='.',
                           output_filename='formula-requirements.txt',
                           overwrite=False):
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

        if os.path.exists(path) and not overwrite:
            shaker.libs.logger.Logger().warning('ShakerMetadata::write_requirements: '
                                                   ' File exists, not writing...')
            return False
        else:
            with open(path, 'w') as outfile:
                requirements = self._get_requirements()
                outfile.write('\n'.join(requirements))
                outfile.write('\n')
                shaker.libs.logger.Logger().info("ShakerMetadata::write_requirements: "
                                                      "Wrote file '%s'"
                                                      % (path)
                                                      )
                return True

        return False

    def _link_dynamic_modules(self, dependency):
        dependency_name = dependency.get("name")

        repo_dir = os.path.join(self._working_directory,
                                self._install_directory,
                                dependency_name)

        for libdir in self._dynamic_modules_dirs:
            
            targetdir = os.path.join(self._working_directory,
                                     self._salt_root,
                                     libdir)
            sourcedir = os.path.join(repo_dir, libdir)

            relative_source = os.path.relpath(sourcedir, targetdir)
            if os.path.isdir(sourcedir):
                self._logger.debug("ShakerRemote::_link_dynamic_modules: "
                                   "Found source directory '%s"
                                   % (sourcedir))
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
            else:
                raise IOError("ShakerRemote::_link_dynamic_modules: "
                              "Source directory '%s' not found"
                              % (sourcedir))

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
            self._logger.debug("_resolve_constraint_to_sha(%s) Found version '%s' and sha '%s'"
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
            self._logger.debug("_create_directories: Deleting salt root directory '%s'"
                           % (salt_root_path))
        os.makedirs(salt_root_path)
        
        # Ensure the repos_dir exists
        install_path = os.path.join(self._working_directory,
                                    self._install_directory)
        
        if not os.path.exists(install_path):
            try:
                self._logger.debug("_create_directories: Creating repository directory '%s'"
                               % (install_path))
                os.makedirs(install_path)
            except OSError as e:
                    raise IOError("There was a problem creating the directory '%s', '%s'"
                               % (install_path, e))
        elif overwrite and os.path.exists(install_path):
            shutil.rmtree(install_path)
            self._logger.debug("_create_directories: Deleting repository directory '%s'"
                           % (install_path))
            os.makedirs(install_path)
        

    def _get_requirements(self):
        """
            Get a list of the requirements from the current
            dependency metadata

        Returns:
            (list): List of requirements or None type
        """
        requirements = []
        if self._dependencies and len(self._dependencies) > 0:

            for key, info in self._dependencies.items():
                entry = ("%s==%s"
                         % (info.get("source", ""),
                            info.get("version", "")
                            ))
                requirements.append(entry)

        return requirements