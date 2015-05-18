import logging
import os

from shaker.libs import logger
from shaker_metadata import ShakerMetadata
from shaker_remote import ShakerRemote


class Shaker(object):
    """
    Start from a root formula and calculate all necessary dependencies,
    based on metadata stored in each formula.

    How it works
    ------------

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
        There is a high chance you don't want to change the paths here.

        If you do, you'll need to change the paths in your salt config to ensure
        that there is an entry in `file_roots` that matches self.roots_dir
        (i.e., root_dir + salt_root_path + salt_root)
        """

        self.roots_dir = os.path.join(root_dir, salt_root_path, salt_root)
        self.repos_dir = os.path.join(root_dir, salt_root_path, clone_path)

        self._root_dir = root_dir
        self._shaker_metadata = ShakerMetadata(root_dir)

    def load_requirements(self):
        """
        Load the requirements file and update the remote dependencies
        """
        logger.Logger().info("Shaker: Loading the current formula requirements...")
        self._shaker_remote = ShakerRemote(self._shaker_metadata.local_requirements)
        self._shaker_remote.update_dependencies()

    def update_requirements(self):
        """
        Update the requirements from metadata entries, overriding the
        current formula requirements
        """
        logger.Logger().info("Shaker: Updating the formula requirements...")

        self._shaker_metadata.update_dependencies(ignore_local_requirements=True)
        self._shaker_remote = ShakerRemote(self._shaker_metadata.dependencies)
        self._shaker_remote.update_dependencies()

    def install_requirements(self,
                             overwrite=False,
                             simulate=False):
        """
        Install all of the versioned requirements found
        """
        if not simulate:
            logger.Logger().info("Shaker: Installing dependencies...")
            self._shaker_remote.install_dependencies(overwrite=overwrite)
            logger.Logger().info("Shaker: Writing requirements file...")
            self._shaker_remote.write_requirements(overwrite=True, backup=True)
        else:
            requirements = '\n'.join(self._shaker_remote.get_requirements())
            logger.Logger().warning("Shaker: Simulation mode enabled, "
                                 "no changes will be made...\n%s\n\n"
                                 % (requirements))


def setup_logging(level):
    # Initialise the default app logging
    logger.Logger('salt-shaker')
    logger.Logger().setLevel(level)


def shaker(root_dir='.',
           debug=False,
           verbose=False,
           overwrite=False,
           simulate=False):
    """
    utility task to initiate Shaker in the most typical way
    """
    if (debug):
        setup_logging(logging.DEBUG)
    elif (verbose):
        setup_logging(logging.INFO)
    else:
        setup_logging(logging.WARNING)

    if not os.path.exists(root_dir):
        os.makedirs(root_dir, 0755)
    shaker_instance = Shaker(root_dir=root_dir)

    if overwrite:
        logger.Logger().info("Shaker: Updating..."
                             "All dependencies will be "
                             "re-calculated from the metadata")
        shaker_instance.update_requirements()
        shaker_instance.install_requirements(overwrite=True,
                                             simulate=simulate)
    else:
        logger.Logger().info("Shaker: Refreshing..."
                             "Dependencies will be refreshed "
                             "from the stored formula requirements")
        shaker_instance.load_requirements()
        shaker_instance.install_requirements(overwrite=False,
                                             simulate=simulate)
