import unittest
import os
import requests
import responses
import json
import pygit2
from nose.tools import raises

import shaker.libs.github
from shaker.libs.errors import ConstraintResolutionException


class TestGithub(unittest.TestCase):

    _sample_response_tags = [
        {
            "name": "v1.0.1",
            "zipball_url": "https://api.github.com/repos/ministryofjustice/test-formula/zipball/v1.0.1",
            "tarball_url": "https://api.github.com/repos/ministryofjustice/test-formula/tarball/v1.0.1",
            "commit": {
                "sha": "6826533980361f54b9de17d181830fa4ec94138c",
                "url": "https://api.github.com/repos/ministryofjustice/test-formula/commits/6826533980361f54b9de17d181830fa4ec94138c"
            }
        },
        {
            "name": "v2.0.1",
            "zipball_url": "https://api.github.com/repos/ministryofjustice/test-formula/zipball/v2.0.1",
            "tarball_url": "https://api.github.com/repos/ministryofjustice/test-formula/tarball/v2.0.1",
            "commit": {
                "sha": "1d7d509b534b08b08b1f85253990b6c3f0dec007",
                "url": "https://api.github.com/repos/ministryofjustice/test-formula/commits/1d7d509b534b08b08b1f85253990b6c3f0dec007"
            }
        },
    ]

    def setUp(self):
        unittest.TestCase.setUp(self)
        os.environ['GITHUB_TOKEN'] = 'false'

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_parse_github_url(self):
        """
        TestGithub: Test the components are pulled out of github urls
        """
        url = "git@github.com:test-organisation/test1-formula.git==v1.0.1"
        parsed_info = shaker.libs.github.parse_github_url(url)
        self.assertEqual(parsed_info.get('source', ''),
                         "git@github.com:test-organisation/test1-formula.git",
                         "Source field not equal"
                         "%s!=%s"
                         % (parsed_info.get('source', ''),
                            "git@github.com:test-organisation/test1-formula.git"))
        self.assertEqual(parsed_info.get('name', ''),
                         "test1-formula",
                         "Name field not equal"
                         "%s!=%s"
                         % (parsed_info.get('name', ''),
                            "test1-formula"))

        parsed_info = shaker.libs.github.parse_github_url(url)
        self.assertEqual(parsed_info.get('organisation', ''),
                         "test-organisation",
                         "Organisation field not equal "
                         "%s!=%s"
                         % (parsed_info.get('organisation', ''),
                            "test-organisation"))

        parsed_info = shaker.libs.github.parse_github_url(url)
        self.assertEqual(parsed_info.get('constraint', ''),
                         "==v1.0.1",
                         "Constraint field not equal"
                         "%s!=%s"
                         % (parsed_info.get('constraint', ''),
                            "v1.0.1"))

    @responses.activate
    def test_get_valid_github_token(self):
        """
        TestGithub: Test calling the get token function with a good token
        """
        # Test validating a github token thats missing
        if 'GITHUB_TOKEN' in os.environ:
            del os.environ['GITHUB_TOKEN']
        token = shaker.libs.github.get_valid_github_token()
        self.assertEqual(token, None, "Expected no github token to be found")

        # Test calling with a valid github token. We should expect a
        # 200 status

        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "message": "Successful login.",
                "mock": "True"
            }
        ]

        responses.add(responses.GET,
                      "https://api.github.com",
                      content_type="application/json",
                      body=json.dumps(mock_resp),
                      status=200
                      )

        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "FAKE_VALID_TOKEN"
        expected_token = os.environ['GITHUB_TOKEN']

        # Attempt validating the invalid token
        github_token = shaker.libs.github.get_valid_github_token()
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                                       auth=(github_token, 'x-oauth-basic'))

        # Check we got the right messages and statuses
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code,
                         200,
                         "Expected 200 response, got '%s'"
                         % actual_response.status_code)
        self.assertEqual(github_token,
                         expected_token,
                         "Expected None type token, got '%s'"
                         % github_token)

    @responses.activate
    def test_get_valid_github_token_online(self):
        """
        TestGithub: Test calling the get token function with a bad token
        """
        # Test calling with an invalid github token. We should expect a "Bad Credentials" message
        # and a 401 status

        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "documentation_url": "https://developer.github.com/v3",
                "message": "Bad credentials",
                "mock": "True"
            }
        ]

        responses.add(responses.GET,
                      "https://api.github.com",
                      content_type="application/json",
                      body=json.dumps(mock_resp),
                      status=401
                      )

        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "INVALID_TOKEN"

        # Attempt validating the invalid token
        github_token = shaker.libs.github.get_valid_github_token(online_validation_enabled=True)
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                                       auth=(github_token, 'x-oauth-basic'))

        # Check we got the right messages and statuses
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code,
                         401,
                         "Expected 401 response, got '%s'"
                         % actual_response.status_code)
        self.assertEqual(github_token,
                         None,
                         "Expected None type token, got '%s'"
                         % github_token)

    @responses.activate
    def test_validate_blocked_github_token(self):
        """
        TestGithub: Test calling the get token function with a blocked token
        """
        # Test calling with an blocked github token. We should expect a
        # "Maximum number of login attempts exceeded" message
        # and a 403 status

        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "message": "Maximum number of login attempts exceeded. Please try again later.",
                "documentation_url": "https://developer.github.com/v3",
                "mock": "True"
            }
        ]

        responses.add(responses.GET,
                      "https://api.github.com",
                      content_type="application/json",
                      body=json.dumps(mock_resp),
                      status=403
                      )

        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "INVALID_TOKEN"

        # Attempt validating the invalid token
        github_token = shaker.libs.github.get_valid_github_token(online_validation_enabled=True)
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                                       auth=(github_token, 'x-oauth-basic'))

        # Check we got the right messages and statuses
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code,
                         403,
                         "Expected 401 response, got '%s'"
                         % actual_response.status_code)
        self.assertEqual(github_token,
                         None,
                         "Expected None type token, got '%s'"
                         % github_token)

    @responses.activate
    def test_resolve_constraint_to_tag_equality_resolvable(self):
        """
        TestGithub: Test that we get the right tags for a resolvable constraint
        """

        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v1.0.1'
        constraint = '==%s' % version
        tag_data = shaker.libs.github.resolve_constraint_to_object(org,
                                                                   formula,
                                                                   constraint)
        wanted_tag = tag_data['name']
        # Equality constraint is satisfiable
        self.assertEqual(wanted_tag,
                         version,
                         "Equality constraintshould be satisfiable, "
                         "actual:%s expected:%s"
                         % (wanted_tag,
                            version))

    @responses.activate
    @raises(ConstraintResolutionException)
    def test_resolve_constraint_to_tag_equality_unresolvable(self):
        """
        TestGithub: Test that we throw an unresolvable constraint error
        """
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v666'
        constraint = '==%s' % version
        tag_data = shaker.libs.github.resolve_constraint_to_object(org,
                                                                   formula,
                                                                   constraint)
        self.assertTrue(False, "TODO")

    @responses.activate
    def test_resolve_constraint_to_tag_greater_than_resolvable(self):
        """
        TestGithub: Test that we get the right tags for a resolvable constraint
        """
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v1.1'
        expected_version = 'v2.0.1'
        constraint = '>=%s' % version
        tag_data = shaker.libs.github.resolve_constraint_to_object(org,
                                                                   formula,
                                                                   constraint)
        wanted_tag = tag_data.get('name', None)
        # Equality constraint is satisfiable
        self.assertEqual(wanted_tag,
                         expected_version,
                         "Greater than constraint should be satisfiable, "
                         "actual:%s expected:%s"
                         % (wanted_tag,
                            expected_version))

    @responses.activate
    @raises(ConstraintResolutionException)
    def test_resolve_constraint_to_tag_greater_than_unresolvable(self):
        """
        TestGithub: Test that we throw an unresolvable constraint error
        """
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v2.1'
        constraint = '>=%s' % version
        shaker.libs.github.resolve_constraint_to_object(org,
                                                        formula,
                                                        constraint)
        # We're testing for exceptions, No assertion needed

    @responses.activate
    def test_resolve_constraint_to_tag_less_than_resolvable(self):
        """
        TestGithub: Test that we get the right tags for a resolvable constraint
        """
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v1.1'
        expected_version = 'v1.0.1'
        constraint = '<=%s' % version
        tag_data = shaker.libs.github.resolve_constraint_to_object(org,
                                                                   formula,
                                                                   constraint)
        wanted_tag = tag_data['name']
        # Equality constraint is satisfiable
        self.assertEqual(wanted_tag,
                         expected_version,
                         "Less than constraint should be satisfiable, "
                         "actual:%s expected:%s"
                         % (wanted_tag,
                            expected_version))

    @responses.activate
    @raises(ConstraintResolutionException)
    def test_resolve_constraint_to_tag_lesser_than_unresolvable(self):
        """
        TestGithub: Test that we throw an unresolvable constraint error
        """
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        version = 'v1.0'
        constraint = '<=%s' % version
        tag_data = shaker.libs.github.resolve_constraint_to_object(org,
                                                                   formula,
                                                                   constraint)
        self.assertTrue(False, "TODO")

    @responses.activate
    def test_get_tags(self):
        responses.add(responses.GET,
                      'https://api.github.com/repos/ministryofjustice/test-formula/tags',
                      content_type="application/json",
                      body=json.dumps(self._sample_response_tags),
                      status=200
                      )
        org = 'ministryofjustice'
        formula = 'test-formula'
        wanted_tag, tag_versions, _ = shaker.libs.github.get_tags(org, formula)
        expected_wanted_tag = "v2.0.1"
        expected_tag_versions = ["1.0.1", "2.0.1"]

        self.assertEqual(wanted_tag, expected_wanted_tag, "Expected wanted tag '%s, got '%s'"
                         % (wanted_tag, expected_wanted_tag))
        self.assertEqual(tag_versions, expected_tag_versions, "Expected wanted tag '%s, got '%s'"
                         % (tag_versions, expected_tag_versions))
