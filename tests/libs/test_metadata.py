from unittest import TestCase
from shaker.libs import metadata
from nose.tools import raises
from shaker.libs.errors import ConstraintResolutionException
from mock import patch


class TestMetadata(TestCase):

    # Sample metadata with duplicates
    _sample_metadata_duplicates = {
        "dependencies": [
            "git@github.com:test_organisation/test1-formula.git==v1.0.1",
            "git@github.com:test_organisation/test1-formula.git==v1.0.2",
            "git@github.com:test_organisation/test2-formula.git==v2.0.1",
            "git@github.com:test_organisation/test3-formula.git==v3.0.1",
            "git@github.com:test_organisation/test3-formula.git==v3.0.2"
        ],
        "entry": ["dummy"]
    }

    _sample_metadata_no_duplicates = {
        "dependencies": [
            "git@github.com:test_organisation/test1-formula.git==v1.0.1",
            "git@github.com:test_organisation/test2-formula.git==v2.0.1",
            "git@github.com:test_organisation/test3-formula.git==v3.0.1"
        ],
        "entry": ["dummy"]
    }

    def test_resolve_constraints_equality(self):
        """
        TestMetadata: Test == constraints are resolved correctly
        """

        # Under a simple resolve, the current constraint should win
        new_constraint = '==v0.1'
        current_constraint = '==v1.1'
        constraint = metadata.resolve_constraints(new_constraint,
                                                  current_constraint)
        self.assertEqual(constraint,
                         current_constraint,
                         "Under a simple resolve, the current constraint should win. "
                         "Actual '%s', Expected %s"
                         % (constraint,
                            current_constraint))

    def test_resolve_constraints_greater_than(self):
        """
        TestMetadata: Test >= constraints are resolved correctly
        """
        # With >=, the largest constraint should win
        new_constraint = '>=v1.2'
        current_constraint = '>=v1.1'
        constraint = metadata.resolve_constraints(new_constraint,
                                                  current_constraint)
        self.assertEqual(constraint,
                         new_constraint,
                         "With >=, the largest constraint should win "
                         "Actual '%s', Expected %s"
                         % (constraint,
                            new_constraint))

    def test_resolve_constraints_less_than(self):
        """
        TestMetadata: Test >= constraints are resolved correctly
        """
        # With >=, the largest constraint should win
        new_constraint = '<=v1.2'
        current_constraint = '<=v1.1'
        constraint = metadata.resolve_constraints(new_constraint,
                                                  current_constraint)
        self.assertEqual(constraint,
                         current_constraint,
                         "With <=, the least constraint should win "
                         "Actual '%s', Expected %s"
                         % (constraint,
                            current_constraint))

    @raises(ConstraintResolutionException)
    def test_resolve_constraints_unequal(self):
            """
            TestMetadata: Test unequal constraints are resolved correctly
            """
            # Expect an exception on unequal constraints
            new_constraint = '<=v1.2'
            current_constraint = '>=v1.1'
            constraint = metadata.resolve_constraints(new_constraint,
                                                      current_constraint)
            self.assertEqual(constraint,
                             current_constraint,
                             "Expect an exception on unequal constraints"
                             % (constraint,
                                current_constraint))

    def test_resolve_metadata_duplicates(self):
        """
        TestMetadata: Check if we successfully remove duplicates from a sample metadata
        """
        original_metadata = self._sample_metadata_duplicates
        expected_metadata = self._sample_metadata_no_duplicates
        resolved_metadata = metadata.resolve_metadata_duplicates(original_metadata)

        expected_metadata_dependencies = expected_metadata["dependencies"]
        resolved_metadata_dependencies = resolved_metadata["dependencies"]
        expected_metadata_entries = expected_metadata["entry"]
        resolved_metadata_entries = resolved_metadata["entry"]

        # Test dependencies found
        for expected_metadata_dependency in expected_metadata_dependencies:
            self.assertTrue(expected_metadata_dependency in resolved_metadata_dependencies,
                            "test_resolve_metadata_duplicates: dependency '%s' "
                            "not found in de-duplicated metadata"
                            % (expected_metadata_dependency))

        # Test entry found
        for expected_metadata_entry in expected_metadata_entries:
            self.assertTrue(expected_metadata_entry in resolved_metadata_entries,
                            "test_resolve_metadata_duplicates: Entry '%s' "
                            "not found in de-duplicated metadata"
                            % (expected_metadata_entry))

    @raises(TypeError)
    def test_resolve_metadata_duplicates_bad_metadata_object(self):
        """
        TestMetadata: Check if bad yaml metadata will throw up a TypeError.
        """
        # Callable with bad metadata
        metadata.resolve_metadata_duplicates("not-a-dictionary")

    @raises(IndexError)
    def test_resolve_metadata_duplicates_metadata_missing_index(self):
        """
        TestMetadata: Check if metadata with a missing index will throw an error
        """
        metadata.resolve_metadata_duplicates({})

    @patch('shaker.libs.github.parse_github_url')
    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    def test_parse_metadata_requirements_raw(self,
                                             mock_load_local_requirements,
                                             mock_load_local_metadata,
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
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'some-formula'
            },
            'test_organisation/another-formula':
            {
                'source': 'git@github.com:test_organisation/another-formula.git',
                'constraint': '>=v2.0',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'another-formula'
            }
        }
        mock_parse_github_url.side_effect = [
            {
                'source': 'git@github.com:test_organisation/some-formula.git',
                'constraint': '==v1.0',
                'sourced_constraints': ['==v1.0'],
                'organisation': 'test_organisation',
                'name': 'some-formula'
            },
            {
                'source': 'git@github.com:test_organisation/another-formula.git',
                'constraint': '>=v2.0',
                'sourced_constraints': ['==v2.0'],
                'organisation': 'test_organisation',
                'name': 'another-formula'
            },
            None
        ]
        # PEP8 requires unused mock being used
        mock_load_local_requirements.return_value = None
        mock_load_local_metadata.return_value = None
        mock_fetch_local_metadata.return_value = None

        actual_result = metadata.parse_metadata_requirements(requirements)

        self.assertEqual(actual_result,
                         expected_result,
                         "TestShakerMetadata::test__parse_metadata_requirements_raw: Mismatch\n"
                         "Actual: %s\nExpected: %s\n\n"
                         % (actual_result,
                            expected_result))

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    def test_parse_metadata_requirements_simple(self,
                                                mock_load_local_requirements,
                                                mock_load_local_metadata,
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
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'some-formula'
            },
            'test_organisation/another-formula':
            {
                'source': 'git@github.com:test_organisation/another-formula.git',
                'constraint': '>=v2.0',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'another-formula'
            }
        }

        # PEP8 requires unused mock being used
        mock_load_local_requirements.return_value = None
        mock_load_local_metadata.return_value = None
        mock_fetch_local_metadata.return_value = None

        actual_result = metadata.parse_metadata_requirements(requirements)

        self.assertEqual(actual_result,
                         expected_result,
                         "TestShakerMetadata::test__parse_metadata_requirements_simple: Mismatch\n"
                         "Actual: %s\nExpected: %s\n\n"
                         % (actual_result, expected_result))

    @patch('shaker.shaker_metadata.ShakerMetadata._fetch_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_metadata')
    @patch('shaker.shaker_metadata.ShakerMetadata.load_local_requirements')
    def test_parse_metadata_requirements_simple_with_blanks(self,
                                                mock_load_local_requirements,
                                                mock_load_local_metadata,
                                                mock_fetch_local_metadata):
        """
        TestMetadata: Test that blanks are accepted in the formula constraints
        """
        requirements = [
            'test_organisation/some-formula ==   v1.0',
            'test_organisation/another-formula >= v2.0'
        ]

        expected_result = {
            'test_organisation/some-formula':
            {
                'source': 'git@github.com:test_organisation/some-formula.git',
                'constraint': '==v1.0',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'some-formula'
            },
            'test_organisation/another-formula':
            {
                'source': 'git@github.com:test_organisation/another-formula.git',
                'constraint': '>=v2.0',
                'sourced_constraints': [],
                'organisation': 'test_organisation',
                'name': 'another-formula'
            }
        }

        # PEP8 requires unused mock being used
        mock_load_local_requirements.return_value = None
        mock_load_local_metadata.return_value = None
        mock_fetch_local_metadata.return_value = None

        actual_result = metadata.parse_metadata_requirements(requirements)

        self.assertEqual(actual_result,
                         expected_result,
                         "TestShakerMetadata::test_parse_metadata_requirements_simple_with_blanks: Mismatch\n"
                         "Actual: %s\nExpected: %s\n\n"
                         % (actual_result, expected_result))

    def test_compare_requirements_equal(self):
        """
        TestShakerMetadata: Test comparing different requirements equal
        """
        previous_requirements = [
                              "test_organisation/test1-formula==v1.0.1",
                              "test_organisation/test2-formula==v2.0.1",
                              "test_organisation/test3-formula==v3.0.1",
                              ]
        new_requirements = [
                                "test_organisation/test1-formula==v1.0.1",
                                "test_organisation/test2-formula==v2.0.1",
                                "test_organisation/test3-formula==v3.0.1",
                                ]
        actual_result = metadata.compare_requirements(previous_requirements,
                                                      new_requirements)
        self.assertEqual(0,
                         len(actual_result),
                         "Comparison should have no difference")

    def test_compare_requirements_new_entry(self):
        """
        TestShakerMetadata: Test comparing different requirements new entries
        """
        previous_requirements = [
                              "test_organisation/test1-formula==v1.0.1",
                              "test_organisation/test2-formula==v2.0.1",
                              ]
        new_requirements = [
                                "test_organisation/test1-formula==v1.0.1",
                                "test_organisation/test2-formula==v2.0.1",
                                "test_organisation/test3-formula==v3.0.1",
                                ]
        actual_result = metadata.compare_requirements(previous_requirements,
                                                      new_requirements)
        expected_result = [
                           ['', "test_organisation/test3-formula==v3.0.1"]
                        ]
        self.assertEqual(actual_result,
                         expected_result,
                         ("Comparison should have deprecated entry\n"
                          "Actual: '%s'\n"
                          "Expected: %s\n")
                         % (actual_result,
                            expected_result))

    def test_compare_requirements_deprecated_entry(self):
        """
        TestShakerMetadata: Test comparing different requirements deprecated entries
        """
        previous_requirements = [
                              "test_organisation/test1-formula==v1.0.1",
                              "test_organisation/test2-formula==v2.0.1",
                              "test_organisation/test3-formula==v3.0.1",
                              ]
        new_requirements = [
                                "test_organisation/test1-formula==v1.0.1",
                                "test_organisation/test2-formula==v2.0.1",
                                ]
        actual_result = metadata.compare_requirements(previous_requirements,
                                                      new_requirements)
        expected_result = [
                           ["test_organisation/test3-formula==v3.0.1", ""]
                        ]
        self.assertEqual(actual_result,
                         expected_result,
                         ("Comparison should have new entry\n"
                          "Actual: '%s'\n"
                          "Expected: %s\n")
                         % (actual_result,
                            expected_result))

    def test_compare_requirements_new_versions(self):
        """
        TestShakerMetadata: Test comparing different requirements versions
        """
        previous_requirements = [
                              "test_organisation/test1-formula==v1.0.10",
                              "test_organisation/test2-formula==v2.0.1",
                              "test_organisation/test3-formula==v3.0.1",
                              ]
        new_requirements = [
                                "test_organisation/test1-formula==v1.0.1",
                                "test_organisation/test2-formula==v2.0.10",
                                "test_organisation/test3-formula==v3.0.1",

                                ]
        actual_result = metadata.compare_requirements(previous_requirements,
                                                      new_requirements)
        expected_result = [
                            ["test_organisation/test1-formula==v1.0.10",
                                "test_organisation/test1-formula==v1.0.1"],
                            ["test_organisation/test2-formula==v2.0.1",
                                "test_organisation/test2-formula==v2.0.10"]
                        ]
        self.assertEqual(actual_result,
                         expected_result,
                         ("Comparison should have new version\n"
                          "Actual: '%s'\n"
                          "Expected: %s\n")
                         % (actual_result,
                            expected_result))
