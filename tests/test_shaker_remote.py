from unittest import TestCase
from mock import patch
from shaker.shaker_remote import ShakerRemote
from nose.tools import raises


class TestShakerRemote(TestCase):
    """
    A class to test the ShakerRemote class
    """

    _sample_dependencies = {
        'test_organisation/test1-formula': {
            'source': 'git@github.com:test_organisation/test1-formula.git',
            'constraint': '==v1.0.1',
            'organisation': 'test_organisation',
            'name': 'test1-formula'
        },
        'test_organisation/test2-formula': {
            'source': 'git@github.com:test_organisation/test2-formula.git',
            'constraint': '==v2.0.1',
            'organisation': 'test_organisation',
            'name': 'test2-formula'
        },
        'test_organisation/test3-formula': {
            'source': 'git@github.com:test_organisation/test3-formula.git',
            'constraint': '==v3.0.1',
            'organisation': 'test_organisation',
            'name': 'test3-formula'
        }
    }

    _sample_requirements = ("git@github.com:test_organisation/test1-formula.git==v1.0.1\n"
                            "git@github.com:test_organisation/test2-formula.git==v2.0.1\n"
                            "git@github.com:test_organisation/test3-formula.git==v3.0.1\n")

    def setUp(self):
        TestCase.setUp(self)

    def tearDown(self):
        TestCase.tearDown(self)

    @patch('os.write')
    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test_write_requirements__overwrite(self,
                                           mock_path_exists,
                                           mock_open,
                                           mock_write):
        """
        TestShakerMetadata: Test resolved dependency overwrites an existing file when forced
        """

        # Setup
        testobj = ShakerRemote(self._sample_dependencies)
        output_directory = "tests/files"
        output_filename = "test_dependencies.txt"
        output_path = '%s/%s' % (output_directory,
                                 output_filename)

        # Overwrite an existing file
        mock_path_exists.return_value = True
        testobj.write_requirements(output_directory,
                                   output_filename,
                                   overwrite=True,
                                   backup=False)
        mock_open.assert_called_once_with(output_path, 'w')
        mock_write.assert_called_once(self._sample_requirements)

    @patch('os.write')
    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test_write_requirements__simple(self,
                                        mock_path_exists,
                                        mock_open,
                                        mock_write):
        """
        TestShakerMetadata: Test resolved dependency are correctly written out to file
        """

        # Setup
        testobj = ShakerRemote(self._sample_dependencies)
        output_directory = "tests/files"
        output_filename = "test_dependencies.txt"
        output_path = '%s/%s' % (output_directory,
                                 output_filename)

        # Simple write
        mock_path_exists.return_value = False
        testobj.write_requirements(output_directory,
                                   output_filename,
                                   overwrite=False,
                                   backup=False)
        mock_open.assert_called_once_with(output_path, 'w')
        mock_write.assert_called_once(self._sample_requirements)

    @patch('os.write')
    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test_write_requirements__no_overwrite(self,
                                              mock_path_exists,
                                              mock_open,
                                              mock_write):
        """
        TestShakerMetadata: Test resolved dependency do not overwrite an existing file
        """

        # Setup
        testobj = ShakerRemote(self._sample_dependencies)
        output_filename = "test_dependencies.txt"

        # Don't overwrite an existing file
        mock_path_exists.return_value = True
        testobj.write_requirements(output_filename,
                                   overwrite=False,
                                   backup=False)
        self.assertFalse(mock_open.called, ("With overwrite disabled, "
                                            "we shouldn't have called to open"))
        self.assertFalse(mock_write.called, ("With overwrite disabled, "
                                             "we shouldn't have called to write"))

    @patch('shaker.libs.github.install_source')
    @patch('shaker.libs.github.get_repository_sha')
    @patch('shaker.shaker_remote.ShakerRemote._create_directories')
    def test_install_dependencies_non_existing_sha(self,
                                                   mock_create_directories,
                                                   mock_get_repository_sha,
                                                   mock_install_source):
        """
        TestShakerMetadata: Test installing dependencies with non-existent sha
        """
        mock_create_directories.return_value = None
        mock_get_repository_sha.side_effect = ["fake_sha",
                                               None]
        mock_install_source.return_value = True

    @patch('shaker.shaker_remote.ShakerRemote._link_dynamic_modules')
    @patch('os.symlink')
    @patch('os.path.exists')
    def test__update_root_links__formula_subdir_exists(self,
                                                       mock_path_exists,
                                                       mock_symlink,
                                                       mock_link_dynamic_modules):
        """
        Test root links are made when our formula has docker-formula/docker structure
        """
        # Setup
        sample_dependencies = {
            'test_organisation/test1-formula': {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            },
        }
        testobj = ShakerRemote(sample_dependencies)
        # Set path exists check values
        # True: formula-repos/docker-formula/docker exists
        # False: _root/docker exists
        mock_path_exists.side_effect = [
            True,
            False
        ]
        testobj._update_root_links()
        source = "vendor/formula-repos/test1-formula/test1"
        target = "vendor/_root/test1"
        mock_symlink.assert_called_once_with(source, target)
        mock_link_dynamic_modules.assert_called_once_with("test1-formula")

    @patch('shaker.shaker_remote.ShakerRemote._link_dynamic_modules')
    @patch('os.symlink')
    @patch('os.path.exists')
    def test__update_root_links__formula_subdir_not_exist(self,
                                                          mock_path_exists,
                                                          mock_symlink,
                                                          mock_link_dynamic_modules):
        """
        Test root links are made when our formula has no subdir docker/ structure
        """
        # Setup
        sample_dependencies = {
            'test_organisation/test1': {
                'source': 'git@github.com:test_organisation/test1.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'test1'
            },
        }
        testobj = ShakerRemote(sample_dependencies)
        # Set path exists check values
        # False: formula-repos/docker-formula/docker exists
        # True: formula-repos/docker/ exists
        # False: _root/docker exists
        mock_path_exists.side_effect = [
            False,
            True,
            False
        ]
        testobj._update_root_links()
        source = "vendor/formula-repos/test1"
        target = "vendor/_root/test1"
        mock_symlink.assert_called_once_with(source, target)
        mock_link_dynamic_modules.assert_called_once_with("test1")

    @raises(IOError)
    @patch('shaker.shaker_remote.ShakerRemote._link_dynamic_modules')
    @patch('os.symlink')
    @patch('os.path.exists')
    def test__update_root_links__formula_link_exists(self,
                                                     mock_path_exists,
                                                     mock_symlink,
                                                     mock_link_dynamic_modules):
        """
        Test root links are made when our formula has no subdir docker-formula/ structure
        """
        # Setup
        sample_dependencies = {
            'test_organisation/test1-formula': {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            },
        }
        testobj = ShakerRemote(sample_dependencies)
        # Set path exists check values
        # True: formula-repos/docker-formula/docker exists
        # True: _root/docker exists
        mock_path_exists.side_effect = [
            True,
            True
        ]
        testobj._update_root_links()

    @raises(IOError)
    @patch('os.path.exists')
    def test__update_root_links__formula_dirs_not_exist(self,
                                                        mock_path_exists):
        """
        Test we have an exception when we can't find a any directory
        """
        # Setup
        sample_dependencies = {
            'test_organisation/test1-formula': {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            },
        }
        testobj = ShakerRemote(sample_dependencies)
        # Set path exists check values
        # True: formula-repos/docker-formula/docker exists
        # False: _root/docker exists
        mock_path_exists.side_effect = [
            False,
            False
        ]
        testobj._update_root_links()
        source = "vendor/formula-repos/test1-formula/test1"
        target = "vendor/_root/test1"
        mock_symlink.assert_called_with(source, target)
        mock_link_dynamic_modules.assert_called_with()
