import logging
import os
import sys
import re
import time
import shutil
import urlparse
import errno
import glob
from textwrap import dedent

import pygit2
import yaml

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
    dynamic_modules_dirs = ['_modules', '_grains', '_renderers',
                            '_returners', '_states']

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

    def update_requirements(self, overwrite=False):
        if overwrite:
            ignore_root_requirements=True,
            ignore_dependency_requirements=False
        else:
            ignore_root_requirements=False,
            ignore_dependency_requirements=False
        self._shaker_metadata.update_dependencies(ignore_root_requirements,
                                                  ignore_dependency_requirements)
        self._shaker_remote = ShakerRemote(self._shaker_metadata.dependencies)
        self._shaker_remote.update_dependencies()

    def install_requirements(self, overwrite=False):
        self._shaker_remote.install_dependencies()
        self._shaker_remote.write_requirements(overwrite=overwrite)


def setup_logging(level):
    # Initialise the default app logging
    logging.basicConfig()
    logger.Logger('salt-shaker')
    logger.Logger().setLevel(level)
    logging.getLogger('shaker.helpers.github').setLevel(level)
    logging.getLogger('shaker.helpers.metadata').setLevel(level)
    
def shaker(root_formula=None,
           root_dir='.',
           root_constraint=None,
           debug=False,
           verbose=False,
           overwrite=False):
    """
    utility task to initiate Shaker in the most typical way
    """
    if (debug):
        setup_logging(logging.DEBUG)
    elif (verbose):
        setup_logging(logging.INFO)
    if not os.path.exists(root_dir):
        os.makedirs(root_dir, 0755)
    shaker_instance = Shaker(root_dir=root_dir)
    shaker_instance.update_requirements(overwrite=overwrite)
    shaker_instance.install_requirements(overwrite=overwrite)

