import os
import unittest
from shaker import salt_shaker
from shaker import helpers
from mock import patch


class TestSaltShaker(unittest.TestCase):

    # Sample metadata with duplicates
    _sample_metadata_root = {
        "name": "ministryofjustice/root-formula",
        "dependencies": [
            "git@github.com:test_organisation/test1-formula.git==v1.0.1",
            "git@github.com:test_organisation/test2-formula.git==v2.0.1",
            "git@github.com:test_organisation/test3-formula.git==v3.0.1"
        ]
    }

    def setUp(self):
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    @patch('shaker.helpers.load_metadata_from_file')
    def test_get_formulas_root_formula(self,
                                       mock_load_metadata_from_file):
        """
        Test that get_formulas can handle a root-formula name
        from metadata when it exists
        """
        # Simple get formulas with a root formula name
        expected_formulas = \
        [
            ["test_organisation", "test1-formula.git==v1.0.1", ''],
            ["test_organisation", "test2-formula.git==v2.0.1", ''],
            ["test_organisation", "test3-formula.git==v3.0.1", ''],
        ]
        mock_load_metadata_from_file.return_value = self._sample_metadata_root
        actual_formulas = salt_shaker.get_formulas()

        self.assertEqual(actual_formulas,
                         expected_formulas,
                         "Root formulas \n'%s' "
                         "\nshould be \n'%s'\n"
                         % (actual_formulas, expected_formulas))
