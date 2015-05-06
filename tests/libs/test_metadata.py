from unittest import TestCase
from shaker.libs import metadata
from nose.tools import raises
from shaker.libs.errors import ConstraintResolutionException

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
        criteria = 'simple'
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
                            "test_resolve_metadata_duplicates: dependency '%s' not found in de-duplicated metadata"
                            % (expected_metadata_dependency))

        # Test entry found
        for expected_metadata_entry in expected_metadata_entries:
            self.assertTrue(expected_metadata_entry in resolved_metadata_entries, 
                            "test_resolve_metadata_duplicates: Entry '%s' not found in de-duplicated metadata"
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

