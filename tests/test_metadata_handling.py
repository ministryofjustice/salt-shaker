import unittest
import yaml
from shaker import helpers
from nose.tools import raises

class TestMetadataHandling(unittest.TestCase):

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

    def test_resolve_metadata_duplicates(self):
        """
        Check if we successfully remove duplicates from a sample metadata
        """
        original_metadata = self._sample_metadata_duplicates
        expected_metadata = self._sample_metadata_no_duplicates
        resolved_metadata = helpers.resolve_metadata_duplicates(original_metadata)

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
        Check if bad yaml metadata will throw up a TypeError.
        """
        # Callable with bad metadata
        helpers.resolve_metadata_duplicates("not-a-dictionary")

    @raises(IndexError)
    def test_resolve_metadata_duplicates_metadata_missing_index(self):
        """
        Check if metadata with a missing index will throw an error
        """
        helpers.resolve_metadata_duplicates({})
