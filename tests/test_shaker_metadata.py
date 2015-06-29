from unittest import TestCase
from mock import patch
from mock import mock_open
from nose.tools import raises
import testfixtures
import responses
import json

import logging
import shaker.libs.logger
from shaker.shaker_metadata import ShakerMetadata
from shaker.libs.errors import GithubRepositoryConnectionException


class TestShakerMetadata(TestCase):

    _sample_metadata_root = {
        "formula": "test_organisation/root-formula",
        'dependencies':
        {
            'test_organisation/test1-formula':
            {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            },
                'test_organisation/test2-formula':
                {
                    'source': 'git@github.com:test_organisation/test2-formula.git',
                    'constraint': '==v2.0.1',
                    'sourced_constraints': [],
                    'organisation': 'test_organisation',
                    'name': 'test2-formula'
            }
        }
    }

    _sample_metadata_test1 = {
        "name": "test_organisation/test1-formula",
        "dependencies": [
            "git@github.com:test_organisation/test3-formula.git==v3.0.1",
        ]
    }

    _sample_metadata_test2 = {
        "name": "test_organisation/test2-formula",
        "dependencies": [
            "git@github.com:test_organisation/test3-formula.git==v3.0.2",
        ]
    }
    _sample_metadata_test3 = {
        "name": "test_organisation/test3-formula",
        "dependencies": [
            "git@github.com:test_organisation/root-formula.git==v1.0.2",
        ]
    }
    _sample_requirements_root = {
        "git@github.com:test_organisation/testa-formula.git==v1.0.1",
        "git@github.com:test_organisation/testb-formula.git==v2.0.1",
    }

    _sample_requirements_testa = {
        "git@github.com:test_organisation/testc-formula.git==v3.0.1",
    }

    _sample_requirements_testb = {
        "dependencies": [
            "git@github.com:test_organisation/testc-formula.git==v3.0.2",
        ]
    }
    _sample_requirements_testc = {}

    _sample_root_formula = {
        'formula': 'test_organisation/root-formula',
        'organisation': 'test_organisation',
        'name': 'root-formula',
        'dependencies': {
            'test_organisation/test1-formula':
            {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            },
            'test_organisation/test2-formula':
            {
                'source': 'git@github.com:test_organisation/test2-formula.git',
                'constraint': '==v2.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test2-formula'
            }
        }
    }

    _sample_dependencies = {
        'test_organisation/test1-formula': {
            'source': 'git@github.com:test_organisation/test1-formula.git',
            'constraint': '==v1.0.1',
            'sourced_constraints': [],
            'organisation': 'test_organisation',
            'name': 'test1-formula'
        },
        'test_organisation/test2-formula': {
            'source': 'git@github.com:test_organisation/test2-formula.git',
            'constraint': '==v2.0.1',
            'sourced_constraints': [],
            'organisation': 'test_organisation',
            'name': 'test2-formula'
        },
        'test_organisation/test3-formula': {
            'source': 'git@github.com:test_organisation/test3-formula.git',
            'constraint': '==v3.0.1',
            'sourced_constraints': [],
            'organisation': 'test_organisation',
            'name': 'test3-formula'
        }
    }
    _sample_dependencies_root_only = {
        'test_organisation/test1-formula': {
            'source': 'git@github.com:test_organisation/test1-formula.git',
            'constraint': '==v1.0.1',
            'sourced_constraints': [],
            'organisation': 'test_organisation',
            'name': 'test1-formula'
        },
        'test_organisation/test2-formula': {
            'source': 'git@github.com:test_organisation/test2-formula.git',
            'constraint': '==v2.0.1',
            'sourced_constraints': [],
            'organisation': 'test_organisation',
            'name': 'test2-formula'
        },
    }
    _sample_sourced_dependencies_root_only = {
        'test_organisation/test1-formula': {
            'source': 'git@github.com:test_organisation/test1-formula.git',
            'constraint': '==v1.0.1',
            'sourced_constraints': ['==v1.0.1'],
            'organisation': 'test_organisation',
            'name': 'test1-formula'
        },
        'test_organisation/test2-formula': {
            'source': 'git@github.com:test_organisation/test2-formula.git',
            'constraint': '==v2.0.1',
            'sourced_constraints': ['==v2.0.1'],
            'organisation': 'test_organisation',
            'name': 'test2-formula'
        },
    }
    _sample_requirements_file = ("git@github.com:test_organisation/test1-formula.git==v1.0.1\n"
                                 "git@github.com:test_organisation/test2-formula.git==v2.0.1\n"
                                 "git@github.com:test_organisation/test3-formula.git==v3.0.1\n")

    _sample_tags_test1 = [
        {"name": "v1.0.0"},
        {"name": "v1.0.1"},
        {"name": "v1.0.2"},
    ]

    _sample_tags_test2 = [
        {"name": "v2.0.0"},
        {"name": "v2.0.1"},
        {"name": "v2.0.2"},
    ]

    def setUp(self):
        """
        TestShakerMetadata: Pre-method setup of the test object
        """
        logging.getLogger("salt-shaker-unittest").setLevel(logging.INFO)
        TestCase.setUp(self)

    def tearDown(self):
        """
        TestShakerMetadata: Post-method teardown of the test object
        """
        TestCase.tearDown(self)

    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    def test__init__(self,
                     mock_load_local_metadata,
                     mock_load_local_requirements,
                     ):
        """
        TestShakerMetadata: Test object initialises correctly
        """
        mock_load_local_metadata.return_value = None
        mock_load_local_requirements.return_value = None
        expected_working_directory = '.'
        expected_metadata_filename = 'metadata.yml'
        testobj_default = ShakerMetadata()
        self.assertEqual(testobj_default.working_directory,
                         expected_working_directory,
                         "Default initialised working directory mismatch"
                         "'%s' != '%s'"
                         % (testobj_default.working_directory,
                            expected_working_directory)
                         )
        self.assertEqual(testobj_default.metadata_filename,
                         expected_metadata_filename,
                         "Default initialised metadata filename mismatch. "
                         "'%s' != '%s'"
                         % (testobj_default.metadata_filename,
                            expected_metadata_filename)
                         )

        expected_working_directory = '/some/dir/'
        expected_metadata_filename = 'some_metadata.yml'
        testobj_custom = ShakerMetadata(expected_working_directory,
                                        expected_metadata_filename)
        self.assertEqual(testobj_custom.working_directory,
                         expected_working_directory,
                         "Custom initialised working directory mismatch"
                         "'%s' != '%s'"
                         % (testobj_custom.working_directory,
                            expected_working_directory)
                         )

        self.assertEqual(testobj_custom.metadata_filename,
                         expected_metadata_filename,
                         "Custom initialised metadata filename mismatch"
                         "'%s' != '%s'"
                         % (testobj_custom.metadata_filename,
                            expected_metadata_filename)
                         )

    @patch('yaml.load')
    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test__fetch_local_metadata__fileexists(self,
                                               mock_path_exists,
                                               mock_open,
                                               mock_yaml_load):
        """
        Test we get data when we load a metadata file
        """
        mock_path_exists.return_value = True
        with patch('__builtin__.open',
                   mock_open(read_data=()),
                   create=True):
            mock_yaml_load.return_value = self._sample_metadata_root
            testobj = ShakerMetadata()
            actual_return_value = testobj._fetch_local_metadata('fakedir',
                                                                'fakefile')
            self.assertEqual(actual_return_value,
                             self._sample_metadata_root,
                             "Metadata equalitymismatch: "
                             "\nActual:%s\nExpected:%s\n\n"
                             % (actual_return_value,
                                self._sample_metadata_root))

    @raises(IOError)
    @patch('os.path.exists')
    def test__fetch_local_metadata__filenotexist(self,
                                                 mock_path_exists):
        """
        Test we raise an error when we try to load a non-existent file
        """
        mock_path_exists.return_value = False
        testobj = ShakerMetadata()
        testobj._fetch_local_metadata()
        # No assert needed, we're testing for an exception

    @patch('shaker.libs.metadata.parse_metadata_requirements')
    @patch('shaker.shaker_metadata.ShakerMetadata._parse_metadata_name')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    def test_load_local_metadata(self,
                                 mock_fetch_local_metadata,
                                 mock_parse_metadata_name,
                                 mock_parse_metadata_requirements,
                                 ):
        """
        TestShakerMetadata: Test the metadata loads correctly into the object
        """
        testobj = ShakerMetadata()
        mock_fetch_local_metadata.return_value = self._sample_metadata_root
        mock_parse_metadata_name.return_value = {
            'organisation': 'test_organisation',
            'name': 'root-formula'
        }
        mock_parse_metadata_requirements.return_value = self._sample_root_formula["dependencies"]
        testobj.load_local_metadata()

        self.assertEqual(testobj.root_metadata,
                         self._sample_root_formula,
                         'Metadata root formula mismatch\n\n'
                         '%s\n\n'
                         '%s\n'
                         % (testobj.root_metadata,
                            self._sample_root_formula
                            )
                         )

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_file')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    def test__fetch_remote_requirements(self,
                                        mock_load_local_metadata,
                                        mock_fetch_remote_file):
        sample_raw_requirements = (
            "git@github.com:test_organisation/test1-formula.git==v1.0.1\n"
            "git@github.com:test_organisation/test2-formula.git==v2.0.1\n"
        )

        # PEP8 requires unused mock being used
        mock_load_local_metadata.return_value = None

        expected_result = self._sample_sourced_dependencies_root_only.copy()

        mock_fetch_remote_file.return_value = sample_raw_requirements
        org_name = "test-organisation"
        formula_name = "test1-formula"
        constraint = None

        testobj = ShakerMetadata()
        data = testobj._fetch_remote_requirements(org_name, formula_name, constraint)
        self.assertEqual(data,
                         expected_result,
                         ("Dependency data mismatch:\nActual:%s\nExpected:%s\n\n"
                          % (data, expected_result)))

    @patch("shaker.shaker_metadata.ShakerMetadata._fetch_dependencies")
    @patch("shaker.shaker_metadata.ShakerMetadata.load_local_metadata")
    def test_update_dependencies__use_requirements(self,
                                                   mock_load_local_metadata,
                                                   mock_fetch_dependencies):

        """
        TestShakerMetadata: Test we update dependencies using root requirements path
        """
        sample_root_metadata = {
            'test_organisation/test1-formula': {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': ['==v1.0.1'],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            }
        }
        sample_root_requirements = {
            'test_organisation/testa-formula': {
                'source': 'git@github.com:test_organisation/testa-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': ['==v1.0.1'],
                'organisation': 'test_organisation',
                'name': 'testa-formula'
            }
        }

        # PEP8 requires unused mock being used
        mock_load_local_metadata.return_value = None

        testobj = ShakerMetadata()
        testobj.local_requirements = sample_root_requirements
        testobj.root_metadata = sample_root_metadata

        ignore_local_requirements = False
        ignore_dependency_requirements = False
        testobj.update_dependencies(ignore_local_requirements,
                                    ignore_dependency_requirements)

        mock_fetch_dependencies.assert_called_once_with(sample_root_requirements,
                                                        ignore_dependency_requirements)
        self.assertEqual(testobj.dependencies,
                         sample_root_requirements,
                         'Dependencies mismatch\n'
                         'Actual:%s\n'
                         'Expected:%s\n\n'
                         % (testobj.dependencies,
                            sample_root_requirements
                            )
                         )

    @patch("shaker.shaker_metadata.ShakerMetadata._fetch_dependencies")
    @patch("shaker.shaker_metadata.ShakerMetadata.load_local_metadata")
    def test_update_dependencies__use_metadata(self,
                                               mock_load_local_metadata,
                                               mock_fetch_dependencies):

        """
        TestShakerMetadata: Test we update dependencies using root metadata path
        """
        # PEP8 requires unused mock being used
        mock_load_local_metadata.return_value = None

        testobj = ShakerMetadata()
        testobj.local_requirements = {}
        testobj.root_metadata = self._sample_metadata_root

        ignore_local_requirements = False
        ignore_dependency_requirements = False
        testobj.update_dependencies(ignore_local_requirements,
                                    ignore_dependency_requirements)

        mock_fetch_dependencies.assert_called_once_with(self._sample_dependencies_root_only,
                                                        ignore_dependency_requirements)
        self.assertEqual(testobj.dependencies,
                         self._sample_dependencies_root_only,
                         'Dependencies mismatch\n'
                         'Actual:%s\nExpected:%s\n\n'
                         % (testobj.dependencies,
                            self._sample_dependencies_root_only
                            )
                         )

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_requirements')
    def test_fetch_dependencies__requirements_exist(self,
                                                    mock_fetch_remote_requirements,
                                                    mock_fetch_remote_metadata):
        """
        TestShakerMetadata:test_fetch_dependencies__requirements_exist: Get dependencies when requirements file exists
        """
        test_base_dependencies = {
            'test_organisation/test1-formula':
            {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            }
        }
        mock_fetch_remote_requirements.side_effect = [
            ['test_organisation/test2-formula==v2.0.1'],
            None
        ]

        expected_dependencies = {
            'test_organisation/test1-formula':
            {
                'sourced_constraints': ['==v1.0.1'],
            },
            'test_organisation/test2-formula':
            {
                'source': 'git@github.com:test_organisation/test2-formula.git',
                'constraint': '==v2.0.1',
                'sourced_constraints': ['==v2.0.1'],
                'organisation': 'test_organisation',
                'name': 'test2-formula'
            }
        }
        mock_fetch_remote_metadata.return_value = None
        tempobj = ShakerMetadata(autoload=False)
        tempobj.dependencies = {}
        tempobj._fetch_dependencies(test_base_dependencies,
                                    ignore_dependency_requirements=False)

        testfixtures.compare(tempobj.dependencies, expected_dependencies)

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_requirements')
    def test_fetch_dependencies__only_metadata_exists(self,
                                                      mock_fetch_remote_requirements,
                                                      mock_fetch_remote_metadata):
        test_base_dependencies = {
            'test_organisation/test1-formula':
            {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            }
        }
        mock_fetch_remote_metadata.side_effect = [
            {
                "formula": "test_fetch_dependencies__only_metadata_exists",
                'dependencies':
                [
                    "test_organisation/test2-formula==v2.0.1"
                ]
            },
            None
        ]

        expected_dependencies = {
            'test_organisation/test1-formula':
            {
                'sourced_constraints': ['==v1.0.1'],
            },
            'test_organisation/test2-formula':
            {
                'source': 'git@github.com:test_organisation/test2-formula.git',
                'constraint': '==v2.0.1',
                'sourced_constraints': ['==v2.0.1'],
                'organisation': 'test_organisation',
                'name': 'test2-formula'
            }
        }
        mock_fetch_remote_requirements.return_value = None
        tempobj = ShakerMetadata(autoload=False)
        tempobj.dependencies = {}
        tempobj._fetch_dependencies(test_base_dependencies,
                                    ignore_dependency_requirements=False)

        testfixtures.compare(tempobj.dependencies, expected_dependencies)

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_requirements')
    def test_fetch_dependencies__already_sourced(self,
                                                 mock_fetch_remote_requirements,
                                                 mock_fetch_remote_metadata):
        """
        TestShakerMetadata::test_fetch_dependencies_exists: Don't fetch dependencies if we've already sourced them
        """
        test_base_dependencies = {
            'test_organisation/test1-formula':
            {
                'source': 'git@github.com:test_organisation/test1-formula.git',
                'constraint': '==v1.0.1',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            }
        }
        mock_fetch_remote_metadata.side_effect = [
            {
                'formula': 'test_organisation/test2-formula',
                'dependencies':
                [
                    "test_organisation/test2-formula==v2.0.1"
                ]
            },
            None
        ]

        expected_dependencies = {
            'test_organisation/test1-formula':
            {
                'sourced_constraints': ['==v1.0.1'],
            },
        }
        mock_fetch_remote_requirements.return_value = None
        tempobj = ShakerMetadata(autoload=False)
        tempobj.dependencies = {'test_organisation/test1-formula': {'sourced_constraints': ['==v1.0.1']}}
        tempobj._fetch_dependencies(test_base_dependencies,
                                    ignore_dependency_requirements=False)

        testfixtures.compare(tempobj.dependencies, expected_dependencies)

    @raises(GithubRepositoryConnectionException)
    @patch('shaker.libs.github.validate_github_access')
    @patch('shaker.libs.github.resolve_constraint_to_object')
    @patch('shaker.libs.github.get_valid_github_token')
    def test_fetch_remote_file__no_valid_object(self,
                                                mock_get_valid_github_token,
                                                mock_resolve_constraint_to_object,
                                                mock_validate_github_access):
        """
        TestShakerMetadata::test_fetch_remote_file__no_valid_object: Check for exception when no valid object
        """
        mock_get_valid_github_token.return_value = True
        mock_resolve_constraint_to_object.return_value = None
        mock_validate_github_access.return_value = True
        tempobj = ShakerMetadata(autoload=False)
        tempobj._fetch_remote_file("fake", "fake", "fake", "fake")
        # Looking for exception, assert not needed
        self.assertTrue(False, "N/A")

    @patch('shaker.libs.github.validate_github_access')
    @patch('shaker.libs.github.resolve_constraint_to_object')
    @patch('shaker.libs.github.get_valid_github_token')
    def test_fetch_remote_file__bad_access(self,
                                           mock_get_valid_github_token,
                                           mock_resolve_constraint_to_object,
                                           mock_validate_github_access):
        """
        TestShakerMetadata::test_fetch_remote_file__bad_access: Check for None on problem accessing github
        """
        mock_get_valid_github_token.return_value = True
        mock_resolve_constraint_to_object.return_value = {
            "name": "v5.2.0",
            "commit": {
                "sha": "FAKE",
                "url": "https://api.github.com/repos/fake"
            }
        }

        mock_validate_github_access.return_value = False
        tempobj = ShakerMetadata(autoload=False)
        return_val = tempobj._fetch_remote_file("FAKE", "FAKE", "FAKE", "FAKE")
        self.assertEqual(return_val, None, "Should get None type on bad github access")

    @responses.activate
    @patch('shaker.libs.github.validate_github_access')
    @patch('shaker.libs.github.resolve_constraint_to_object')
    @patch('shaker.libs.github.get_valid_github_token')
    def test_fetch_remote_file__good_access(self,
                                            mock_get_valid_github_token,
                                            mock_resolve_constraint_to_object,
                                            mock_validate_github_access):
        """
        TestShakerMetadata::test_fetch_remote_file__bad_access: Check for good access
        """
        mock_get_valid_github_token.return_value = True
        mock_resolve_constraint_to_object.return_value = {
            "name": "v1.0.0",
            "commit": {
                "sha": "FAKE",
                "url": "https://api.github.com/repos/fake"
            }
        }
        mock_response = {
            "name": "v1.0.0",
            "commit": {
                "sha": "fakesha",
                "url": "https://fakeurl"
            },
        }
        responses.add(
            responses.GET,
            "https://raw.githubusercontent.com/FAKE/FAKE/v1.0.0/FAKE",
            content_type="application/json",
            body=json.dumps(mock_response)
        )
        mock_validate_github_access.return_value = True
        tempobj = ShakerMetadata(autoload=False)
        expected_return = mock_response
        return_val = tempobj._fetch_remote_file("FAKE", "FAKE", "FAKE", "FAKE")
        self.assertEqual(return_val,
                         expected_return,
                         "Metadata mismatch\nActual:'%s'\nExpected:'%s'"
                         % (return_val, expected_return))

    @patch('os.path.exists')
    def test_load_local_requirements(self,
                                     mock_path_exists
                                     ):
        """
        TestShakerMetadata::test_load_local_requirements: Test loading from local dependency file
        """
        # Setup
        mock_path_exists.return_value = True
        text_file_data = '\n'.join(["git@github.com:test_organisation/test1-formula.git==v1.0.1",
                                    "git@github.com:test_organisation/test2-formula.git==v2.0.1",
                                    "git@github.com:test_organisation/test3-formula.git==v3.0.1"])
        with patch('__builtin__.open',
                   mock_open(read_data=()),
                   create=True) as mopen:
            mopen.return_value.__iter__.return_value = text_file_data.splitlines()

            shaker.libs.logger.Logger().setLevel(logging.DEBUG)
            tempobj = ShakerMetadata(autoload=False)
            input_directory = '.'
            input_filename = 'test'
            tempobj.load_local_requirements(input_directory, input_filename)
            mock_path_exists.assert_called_once_with('./test')
            mopen.assert_called_once_with('./test', 'r')
            testfixtures.compare(tempobj.local_requirements, self._sample_dependencies)

    @patch('os.path.exists')
    def test_load_local_requirements__with_blanks(self,
                                                  mock_path_exists
                                                  ):
        """
        TestShakerMetadata::test_load_local_requirements: Test loading from local dependency file with blanks and comments
        """
        # Setup
        mock_path_exists.return_value = True
        text_file_data = '\n'.join(["git@github.com:test_organisation/test1-formula.git==v1.0.1",
                                    "",
                                    "git@github.com:test_organisation/test2-formula.git==v2.0.1",
                                    "             ",
                                    "#DONT_READ_ME",
                                    "git@github.com:test_organisation/test3-formula.git==v3.0.1"])
        with patch('__builtin__.open',
                   mock_open(read_data=()),
                   create=True) as mopen:
            mopen.return_value.__iter__.return_value = text_file_data.splitlines()

            shaker.libs.logger.Logger().setLevel(logging.DEBUG)
            tempobj = ShakerMetadata(autoload=False)
            input_directory = '.'
            input_filename = 'test'
            tempobj.load_local_requirements(input_directory, input_filename)
            mock_path_exists.assert_called_once_with('./test')
            mopen.assert_called_once_with('./test', 'r')
            testfixtures.compare(tempobj.local_requirements, self._sample_dependencies)
