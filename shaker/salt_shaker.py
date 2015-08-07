import logging
import os
import sys
import warnings

from shaker.libs import logger
from shaker.libs import metadata
from shaker.libs import pygit2_utils
from shaker_metadata import ShakerMetadata
from shaker_remote import ShakerRemote
from shaker.libs.errors import ShakerRequirementsUpdateException


class Shaker(object):
    """
    Shaker takes in a metadata yaml file and uses this to resolve a set
    of dependencies into a pinned and versioned set in a
    formula-requirements.txt file. This can then be used to synchronise
    a set of salt-formulas with remote versions pinned to the specified
    versions.

    Starting from a root formula and calculate all necessary dependencies,
    based on metadata stored in each formula.

       -

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
    def __init__(self, root_dir, salt_root_path='vendor',
                 clone_path='formula-repos', salt_root='_root'):
        """
        Initialise application paths and collect together the
        metadata

        Args:
            root_dir(string): The root directory to use
            salt_root_dir(string): The directory to use for the salt
                root
            clone_path(string): The directory to put formula into
            salt_root(string): The directory to link formula into
        """
        # Run sanity checks on pygit2
        pygit2_utils.pygit2_check()

        self.roots_dir = os.path.join(root_dir, salt_root_path, salt_root)
        self.repos_dir = os.path.join(root_dir, salt_root_path, clone_path)

        self._root_dir = root_dir
        self._shaker_metadata = ShakerMetadata(root_dir)

    def install_requirements(self,
                             simulate=False,
                             enable_remote_check=False):
        """
        simulate(bool): True to only simulate the run,
            false to carry it through for real
        enable_remote_check(bool): True to enable remote
            checks when installing pinned versions
        """
        logger.Logger().info("Shaker::install_requirements: "
                             "Installing pinned requirements..."
                             "dependencies will be installed "
                             "from the stored formula requirements")
        self._load_local_requirements()
        self._install_versioned_requirements(overwrite=False,
                                             simulate=simulate,
                                             enable_remote_check=enable_remote_check)

    def update_requirements(self,
                            simulate=False):
        """
        Update the formula-requirements from the metadata,
        then install them

        Args:
            simulate(bool): True to only simulate the run,
                false to carry it through for real
        """
        logger.Logger().info("Shaker::install_requirements: "
                             "Updating and Installing requirements..."
                             "all dependencies will be "
                             "re-calculated from the metadata")
        self._update_local_requirements()
        self._install_versioned_requirements(overwrite=True,
                                             simulate=simulate,
                                             enable_remote_check=True)

    def check_requirements(self):
        """
        Check the current formula-requirements against those that
        would be generated from the metadata,
        """
        logger.Logger().info("Shaker::check_requirements: "
                             "Checking the current requirements "
                             "against an update")
        self._load_local_requirements(enable_remote_check=True)
        current_requirements = self._shaker_remote.get_requirements()
        self._update_local_requirements()
        new_requirements = self._shaker_remote.get_requirements()

        requirements_diff = metadata.compare_requirements(current_requirements,
                                                          new_requirements)

        if len(requirements_diff) == 0:
            logger.Logger().info("Shaker::check_requirements: "
                                 "No formula requirements changes found")
        else:
            for requirement_pair in requirements_diff:
                first_entry = requirement_pair[0]
                second_entry = requirement_pair[1]
                if len(first_entry) == 0:
                    logger.Logger().info("Shaker::check_requirements: "
                                         "New entry %s"
                                         % (second_entry))
                elif len(second_entry) == 0:
                    logger.Logger().info("Shaker::check_requirements: "
                                         "Deprecated entry %s"
                                         % (first_entry))
                else:
                    logger.Logger().info("Shaker::check_requirements: "
                                         "Unequal entries %s != %s"
                                         % (first_entry,
                                            second_entry))
        return requirements_diff

    def _load_local_requirements(self,
                                 enable_remote_check=False):
        """
        Load the requirements file and update the remote dependencies

        Args:
            enable_remote_check(bool): False to use current formula without checking
                remotely for updates. True to use remote repository API to
                recalculate shas
        """
        logger.Logger().info("Shaker: Loading the current formula requirements...")
        self._shaker_remote = ShakerRemote(self._shaker_metadata.local_requirements)
        if enable_remote_check:
            logger.Logger().info("Shaker: Updating the current formula requirements "
                                 "dependencies...")
            self._shaker_remote.update_dependencies()

    def _update_local_requirements(self):
        """
        Update the requirements from metadata entries, overriding the
        current formula requirements
        """
        logger.Logger().info("Shaker: Updating the formula requirements...")

        self._shaker_metadata.update_dependencies(ignore_local_requirements=True)
        self._shaker_remote = ShakerRemote(self._shaker_metadata.dependencies)
        self._shaker_remote.update_dependencies()

    def _install_versioned_requirements(self,
                                        overwrite=False,
                                        simulate=False,
                                        enable_remote_check=False
                                        ):
        """
        Install all of the versioned requirements found

        Args:
            overwrite(bool): True to overwrite dependencies,
                false otherwise
            simulate(bool): True to only simulate the run,
                false to carry it through for real
            enable_remote_check(bool): False to use current formula without checking
                remotely for updates. True to use remote repository API to
                recalculate shas
        """
        if not simulate:
            if enable_remote_check:
                logger.Logger().info("Shaker::install_requirements: Updating requirements tag target shas")
                self._shaker_remote.update_dependencies()
            else:
                logger.Logger().info("Shaker::install_requirements: No remote check, not updating tag target shas")
            logger.Logger().info("Shaker::install_requirements: Installing requirements...")
            successful, unsuccessful = self._shaker_remote.install_dependencies(overwrite=overwrite,
                                                                                enable_remote_check=enable_remote_check)

            # If we have unsuccessful updates, then we should fail before writing the requirements file
            if unsuccessful > 0:
                msg = ("Shaker::install_requirements: %s successful, %s failed"
                       % (successful, unsuccessful))
                raise ShakerRequirementsUpdateException(msg)

            if enable_remote_check:
                logger.Logger().info("Shaker: Writing requirements file...")
                self._shaker_remote.write_requirements(overwrite=True, backup=False)
        else:
            requirements = '\n'.join(self._shaker_remote.get_requirements())
            logger.Logger().warning("Shaker: Simulation mode enabled, "
                                    "no changes will be made...\n%s\n\n"
                                    % (requirements))


def _setup_logging(level):
    """
    Initialise the default application logging

    Args:
        level(logging.LEVEL): The level to set
            logging at
    """
    logger.Logger('salt-shaker')
    logger.Logger().setLevel(level)


def shaker(root_dir='.',
           debug=False,
           verbose=False,
           pinned=False,
           simulate=False,
           check_requirements=False,
           enable_remote_check=False):
    """
    Utility task to initiate Shaker, setting up logging and
    running the neccessary commands to install requirements

    Args:
        root_dir(string): The root directory to use
        debug(bool): Enable/disable debugging output
        verbose(bool): Enable/disable verbose output
        pinned(bool): True to use pinned requirements,
            False to use metadata to recalculate
            requirements
        simulate(bool): True to only simulate the run,
            false to carry it through for real
        check_requirements(bool): True to compare
            a remote dependency check with the current
            formula requirements
        enable_remote_check(bool): True to enable remote
            checks when installing pinned versions
    """
    if (debug):
        _setup_logging(logging.DEBUG)
    elif (verbose):
        _setup_logging(logging.INFO)
    else:
        _setup_logging(logging.INFO)

    if not os.path.exists(root_dir):
        os.makedirs(root_dir, 0755)

    shaker_instance = Shaker(root_dir=root_dir)
    if check_requirements:
        shaker_instance.check_requirements()
    elif pinned:
        shaker_instance.install_requirements(simulate=simulate,
                                             enable_remote_check=enable_remote_check)
    else:
        shaker_instance.update_requirements(simulate=simulate)


def get_deps(root_dir, root_formula=None, constraint=None, force=False):
    """
    (DEPRECATED) Update the formula-requirements from the metadata.yaml,
    then install them

    Args:
        simulate(bool): True to only simulate the run,
            false to carry it through for real
    """
    # This filterwarning makes sure we always see *this* log message
    warnings.filterwarnings("once", "shaker\.salt_shaker\.get_deps.*", DeprecationWarning)
    # Then issue a warning form the caller's perspective
    warnings.warn("shaker.salt_shaker.get_deps has been deprecated. Use `shaker.salt_shaker.shaker(root_dir=...)` instead", DeprecationWarning, stacklevel=2)

    return shaker(root_dir, pinned=not force, enable_remote_check=True)
