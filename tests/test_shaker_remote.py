from unittest import TestCase
from mock import patch
from shaker.shaker_remote import ShakerRemote


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
                                   overwrite=True)
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
                                   overwrite=False)
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
        testobj.write_requirements(output_filename, overwrite=False)
        self.assertFalse(mock_open.called, ("With overwrite disabled, "
                                            "we shouldn't have called to open"))
        self.assertFalse(mock_write.called, ("With overwrite disabled, "
                                             "we shouldn't have called to write"))