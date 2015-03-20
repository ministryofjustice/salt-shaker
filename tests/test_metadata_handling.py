import unittest
import yaml
from shaker import helpers

class TestMetadataHandling(unittest.TestCase):
    
    # Sample metadata with duplicates
    _sample_metadata_duplicates = \
"""
dependencies:
    - git@github.com:test_organisation/test1-formula.git
    - git@github.com:test_organisation/test1-formula.git
    - git@github.com:test_organisation/test2-formula.git
    - git@github.com:test_organisation/test3-formula.git
    - git@github.com:test_organisation/test3-formula.git
entry:
    - dummy
"""
    _sample_metadata_no_duplicates = \
"""
dependencies:
    - git@github.com:test_organisation/test1-formula.git
    - git@github.com:test_organisation/test2-formula.git
    - git@github.com:test_organisation/test3-formula.git
entry:
    - dummy
"""
    # Sample config that yaml load will fail to parse
    _sample_metadata_bad_yaml = \
    """
    dependencies--
        - git@github.com:test_organisation/test1-formula.git
        - git@github.com:test_organisation/test1-formula.git
        - git@github.com:test_organisation/test2-formula.git
        - git@github.com:test_organisation/test3-formula.git
        - git@github.com:test_organisation/test3-formula.git
    entry--
        - dummy
    """
    @classmethod
    def setup_class(cls):
        pass
    
    @classmethod
    def teardown_class(cls):
        pass
    
    def test_resolve_metadata_duplicates(self):
        """
        Check if we successfully remove duplicates from a sample metadata
        """
        original_metadata = yaml.load(self._sample_metadata_duplicates)
        expected_metadata = yaml.load(self._sample_metadata_no_duplicates)
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
            
    def test_resolve_metadata_duplicates_bad_metadata_object(self):
        """
        Check if resolve_metadata_duplicates can handle bad yaml
        data without breaking anything
        """
        expected = yaml.load(self._sample_metadata_bad_yaml)
        result = helpers.resolve_metadata_duplicates(yaml.load(self._sample_metadata_bad_yaml))
        self.assertEqual(result, expected, "")
