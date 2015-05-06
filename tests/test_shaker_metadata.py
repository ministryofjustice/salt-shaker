import os
import yaml
from unittest import TestCase
import mock
from mock import MagicMock
from mock import patch
from nose.tools import raises

import responses
import logging
from shaker.shaker_metadata import ShakerMetadata


class TestShakerMetadata(TestCase):

    _sample_metadata_root = {
        "formula": "test_organisation/root-formula",
        "dependencies": [
            "git@github.com:test_organisation/test1-formula.git==v1.0.1",
            "git@github.com:test_organisation/test2-formula.git==v2.0.1",
        ]
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
                 'organisation': 'test_organisation',
                 'name': 'test1-formula'
                 },
                'test_organisation/test2-formula':
                {
                 'source': 'git@github.com:test_organisation/test2-formula.git',
                 'constraint': '==v2.0.1',
                 'organisation': 'test_organisation',
                 'name': 'test2-formula'
                 }
            }
        }
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
    _sample_dependencies_root_only = {
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
    }
    _sample_requirements_file = ("git@github.com:test_organisation/test1-formula.git==v1.0.1\n"
                            "git@github.com:test_organisation/test2-formula.git==v2.0.1\n"
                            "git@github.com:test_organisation/test3-formula.git==v3.0.1\n")
    
    _sample_tags_test1 = [
        { "name": "v1.0.0"},
        { "name": "v1.0.1"},
        { "name": "v1.0.2"},
    ]

    _sample_tags_test2 = [
        { "name": "v2.0.0"},
        { "name": "v2.0.1"},
        { "name": "v2.0.2"},
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
        actual_return_value = testobj._fetch_local_metadata()

    @patch('shaker.shaker_metadata.ShakerMetadata._parse_metadata_requirements')
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

    @patch('shaker.libs.github.parse_github_url')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    def test__parse_metadata_requirements_raw(self,
                                              monk_load_local_requirements,
                                              monk_load_local_metadata,
                                              mock_fetch_local_metadata,
                                              mock_parse_github_url):
        requirements = [
                        'git@github.com:test_organisation/some-formula.git==v1.0',
                        'git@github.com:test_organisation/another-formula.git>=v2.0'
                        ]
        
        expected_result = {
                           'test_organisation/some-formula':
                           {
                                'source': 'git@github.com:test_organisation/some-formula.git',
                                'constraint': '==v1.0',
                                'organisation': 'test_organisation',
                                'name': 'some-formula'
                            },
                           'test_organisation/another-formula':
                           {
                                'source': 'git@github.com:test_organisation/another-formula.git',
                                'constraint': '>=v2.0',
                                'organisation': 'test_organisation',
                                'name': 'another-formula'
                            }
                           }
        mock_parse_github_url.side_effect = [
                         {
                          'source': 'git@github.com:test_organisation/some-formula.git',
                          'constraint': '==v1.0',
                          'organisation': 'test_organisation',
                          'name': 'some-formula'
                         },
                         {
                          'source': 'git@github.com:test_organisation/another-formula.git',
                          'constraint': '>=v2.0',
                          'organisation': 'test_organisation',
                          'name': 'another-formula'
                         },
                        None
                    ]
        testobj = ShakerMetadata()
        actual_result = testobj._parse_metadata_requirements(requirements)
        
        self.assertEqual(actual_result,
                        expected_result,
                        "TestShakerMetadata::test__parse_metadata_requirements_raw: Mismatch\n"
                        "Actual: %s\n"
                        "Expected: %s\n\n"
                        % (actual_result,
                           expected_result))
        
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    def test__parse_metadata_requirements_simple(self,
                                              monk_load_local_requirements,
                                              monk_load_local_metadata,
                                              mock_fetch_local_metadata):
        requirements = [
                        'test_organisation/some-formula==v1.0',
                        'test_organisation/another-formula>=v2.0'
                        ]
        
        expected_result = {
                           'test_organisation/some-formula':
                           {
                                'source': 'git@github.com:test_organisation/some-formula.git',
                                'constraint': '==v1.0',
                                'organisation': 'test_organisation',
                                'name': 'some-formula'
                            },
                           'test_organisation/another-formula':
                           {
                                'source': 'git@github.com:test_organisation/another-formula.git',
                                'constraint': '>=v2.0',
                                'organisation': 'test_organisation',
                                'name': 'another-formula'
                            }
                           }
        
        testobj = ShakerMetadata()
        actual_result = testobj._parse_metadata_requirements(requirements)
        
        self.assertEqual(actual_result,
                        expected_result,
                        "TestShakerMetadata::test__parse_metadata_requirements_simple: Mismatch\n"
                        "Actual: %s\n"
                        "Expected: %s\n\n"
                        % (actual_result,
                           expected_result))


    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_remote_file')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    def test__fetch_remote_requirements(self,
                                        mock_load_local_metadata,
                                        mock_fetch_remote_file):
        sample_raw_requirements = (
            "git@github.com:test_organisation/test1-formula.git==v1.0.1\n"
            "git@github.com:test_organisation/test2-formula.git==v2.0.1\n"
            )
        
        mock_fetch_remote_file.return_value = sample_raw_requirements
        org_name = "test-organisation"
        formula_name = "test1-formula"
        constraint = None
        
        testobj = ShakerMetadata()
        data = testobj._fetch_remote_requirements(org_name, formula_name, constraint)
        self.assertEqual(data,
                         self._sample_dependencies_root_only,
                         ("Dependency data mismatch:\nActual:%s\nExpected:%s\n\n"
                          % (data,
                             self._sample_dependencies_root_only)))
        

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
                'organisation': 'test_organisation',
                'name': 'test1-formula'
            }
        }
        sample_root_requirements = {
            'test_organisation/testa-formula': {
                'source': 'git@github.com:test_organisation/testa-formula.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'testa-formula'
            }
        }
        
        testobj = ShakerMetadata()
        testobj.root_requirements=sample_root_requirements
        testobj.root_metadata=sample_root_metadata

        ignore_root_requirements = False
        ignore_dependency_requirements=False
        testobj.update_dependencies(ignore_root_requirements,
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
        sample_root_requirements = {
            'test_organisation/testa-formula': {
                'source': 'git@github.com:test_organisation/testa-formula.git',
                'constraint': '==v1.0.1',
                'organisation': 'test_organisation',
                'name': 'testa-formula'
            }
        }
        
        testobj = ShakerMetadata()
        testobj.root_requirements={}
        testobj.root_metadata = self._sample_metadata_root

        ignore_root_requirements = False
        ignore_dependency_requirements=False
        testobj.update_dependencies(ignore_root_requirements,
                                    ignore_dependency_requirements)

        mock_fetch_dependencies.assert_called_once_with(self._sample_dependencies_root_only,
                                                        ignore_dependency_requirements)
        self.assertEqual(testobj.dependencies,
                         self._sample_dependencies_root_only,
                         'Dependencies mismatch\n'
                         'Actual:%s\n'
                         'Expected:%s\n\n'
                         % (testobj.dependencies,
                            self._sample_dependencies_root_only
                            )
                         )

    def test_fetch_dependencies(self):
        self.assertTrue(False, "TODO")

    @patch("shaker.shaker_metadata.ShakerMetadata.load_local_metadata")
    def test_load_local_requirements(self,
                                     mock_load_local_metadata):
        """
        TestShakerMetadata::test_load_local_requirements: Test loading from local dependency file
        """
        # Setup
        mock_load_local_metadata.return_value = self._sample_requirements_file
        testobj = ShakerMetadata()
        testobj.load_local_requirements('./tests/files', 'requirements.txt')
        self.assertEqual(testobj.root_requirements,
                         self._sample_dependencies,
                         "Loaded dependencies mismatch \n\n"
                         "%s\n\n"
                         "%s\n\n"
                         % (testobj.root_requirements,
                            self._sample_dependencies))
