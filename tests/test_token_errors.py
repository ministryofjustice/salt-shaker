import unittest
import os
import requests
import responses
import json
import logging
from shaker import helpers

class TestTokenErrors(unittest.TestCase):
        
    @classmethod
    def setup_class(obj):
        logging.basicConfig(level=logging.DEBUG)
        pass
    
    @classmethod
    def teardown_class(obj):
        pass
    
    @responses.activate
    def test_get_valid_github_token(self):
        # Test validating a github token thats missing
        if 'GITHUB_TOKEN' in os.environ:
            del os.environ['GITHUB_TOKEN']
        token = helpers.get_valid_github_token()
        self.assertEqual(token, None, "Expected no github token to be found")
        
         # Test calling with a valid github token. We should expect a 
        # 200 status
        
        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "message": "Successful login.",
                "mock" : "True"
            }
        ]
        
        responses.add (responses.GET,
                       "https://api.github.com",
                       content_type="application/json",
                       body=json.dumps(mock_resp),
                       status = 200
                       )
         
        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "FAKE_VALID_TOKEN"
        expected_token = os.environ['GITHUB_TOKEN']

        # Attempt validating the invalid token
        github_token = helpers.get_valid_github_token()
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                             auth=(github_token, 'x-oauth-basic'))

        # Check we got the right messages and statuses
        response_message = json.loads(actual_response.text)[0]["message"]
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code, 200, "Expected 200 response, got '%s'" %actual_response.status_code)
        self.assertEqual(github_token, expected_token, "Expected None type token, got '%s'" %github_token)
        
    @responses.activate
    def test_get_valid_github_token_online(self):
        """ 
        Test calling the get token function with a bad token,
        using its online validation attempts to catch the mistake
        """
        
        # Test calling with an invalid github token. We should expect a "Bad Credentials" message
        # and a 401 status
        
        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "documentation_url": "https://developer.github.com/v3",
                "message": "Bad credentials",
                "mock" : "True"
            }
        ]
        
        responses.add (responses.GET,
                       "https://api.github.com",
                       content_type="application/json",
                       body=json.dumps(mock_resp),
                       status = 401
                       )
         
        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "INVALID_TOKEN"
        token = os.environ['GITHUB_TOKEN']

        # Attempt validating the invalid token
        github_token = helpers.get_valid_github_token(online_validation_enabled = True)
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                             auth=(github_token, 'x-oauth-basic'))
        
        # Check we got the right messages and statuses
        response_message = json.loads(actual_response.text)[0]["message"]
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code, 401, "Expected 401 response, got '%s'" %actual_response.status_code)
        self.assertEqual(github_token, None, "Expected None type token, got '%s'" %github_token)

    @responses.activate
    def test_validate_blocked_github_token(self):
        """ 
        Test calling the get token function with a bad token that has now
        been blocked, using its online validation attempts to catch the mistake
        """
        
        # Test calling with an blocked github token. We should expect a 
        #"Maximum number of login attempts exceeded" message
        # and a 403 status
        
        # Setup the incorrect credential mock responses
        mock_resp = [
            {
                "message": "Maximum number of login attempts exceeded. Please try again later.",
                "documentation_url": "https://developer.github.com/v3",
                "mock" : "True"
            }
        ]
        
        responses.add (responses.GET,
                       "https://api.github.com",
                       content_type="application/json",
                       body=json.dumps(mock_resp),
                       status = 403
                       )
         
        # Setup an invalid github token
        os.environ['GITHUB_TOKEN'] = "INVALID_TOKEN"
        token = os.environ['GITHUB_TOKEN']

        # Attempt validating the invalid token
        github_token = helpers.get_valid_github_token(online_validation_enabled = True)
        url = 'https://api.github.com'
        actual_response = requests.get(url,
                             auth=(github_token, 'x-oauth-basic'))
        
        # Check we got the right messages and statuses
        response_message = json.loads(actual_response.text)[0]["message"]
        response_mock = json.loads(actual_response.text)[0]["mock"]
        self.assertTrue(response_mock, "Not working with the mocked response")
        self.assertEqual(actual_response.status_code, 403, "Expected 401 response, got '%s'" %actual_response.status_code)
        self.assertEqual(github_token, None, "Expected None type token, got '%s'" %github_token)
