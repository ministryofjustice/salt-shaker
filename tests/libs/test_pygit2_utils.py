import sys
import traceback

from unittest import TestCase
from shaker.libs import pygit2_utils
from mock import patch
from nose.tools import raises

import pygit2


class TestPygit2Utils(TestCase):

    @raises(pygit2_utils.Pygit2KepairFromAgentUnsupportedError)
    def test_pygit2_parse_error__attributeerror(self):
        """
        Test pygit2_parse_error raises correct exception on attribute error
        """
        e = AttributeError("'module' object has no attribute 'KeypairFromAgent'")
        pygit2_utils.pygit2_parse_error(e)

    @raises(pygit2_utils.Pygit2SSHUnsupportedError)
    def test_pygit2_parse_error__credentialserror(self):
        """
        Test pygit2_parse_error raises correct exception on credentials error
        """
        e = pygit2.GitError("Unsupported URL protocol")
        pygit2_utils.pygit2_parse_error(e)

    def test_pygit2_parse_error__preserves_backtrace(self):

        def sub_func():
            x = {}
            x.i_should_throw()

        try:
            try:
                sub_func()
            except AttributeError as e:
                pygit2_utils.pygit2_parse_error(e)

            self.fail("Should have thrown an exception")
        except:
            tb = traceback.extract_tb(sys.exc_info()[2])
            filename,lineno,method,code = tb[-1]
            self.assertEqual(method, "sub_func")
            self.assertEqual(code, "x.i_should_throw()")

    @patch("pygit2.credentials", spec={})
    def test_pygit2_check_credentials__no_keychain(self, mock_pygit2_credentials):
        """
        TestPygit2Utils:test_pygit2_check_credentials_no_keychain: Check for missing credentials support
        """
        mock_pygit2_credentials.return_value = None
        result = pygit2_utils.pygit2_check_credentials()
        self.assertFalse(result)

    @raises(pygit2_utils.Pygit2SSHUnsupportedError)
    @patch("shaker.libs.pygit2_utils.pygit2_check_ssh")
    def test_pygit2_check__no_ssh(self,
                                  mock_check_ssh):
        """
        Test pygit_check raises exception when ssh check fails
        """
        mock_check_ssh.return_value = False
        pygit2_utils.pygit2_check()

    @raises(pygit2_utils.Pygit2KepairFromAgentUnsupportedError)
    @patch("shaker.libs.pygit2_utils.pygit2_check_credentials")
    @patch("shaker.libs.pygit2_utils.pygit2_check_ssh")
    def test_pygit2_check__no_credentials(self,
                                          mock_check_ssh,
                                          mock_check_credentials):
        """
        Test pygit_check raises exception when credential check fails
        """
        mock_check_ssh.return_value = True
        mock_check_credentials.return_value = False
        pygit2_utils.pygit2_check()

    @patch("shaker.libs.pygit2_utils.pygit2")
    def test_pygit2_check_ssh__have_ssh(self,
                                        mock_pygit2):
        """
        TestPygit2Utils:test_pygit2_check_ssh: Check for successful ssh support
        """
        # Mock needed pygit2 components
        mock_pygit2.features = pygit2.GIT_FEATURE_SSH
        mock_pygit2.GIT_FEATURE_SSH = pygit2.GIT_FEATURE_SSH
        mock_pygit2.GIT_FEATURE_HTTPS = pygit2.GIT_FEATURE_HTTPS

        result = pygit2_utils.pygit2_check_ssh()
        self.assertTrue(result)

    @patch("shaker.libs.pygit2_utils.pygit2")
    def test_pygit2_check_ssh__no_ssh(self,
                                      mock_pygit2):
        """
        TestPygit2Utils:test_pygit2_check_no_ssh: Check for missing ssh support
        """
        # Mock needed pygit2 components
        mock_pygit2.features = pygit2.GIT_FEATURE_HTTPS
        mock_pygit2.GIT_FEATURE_SSH = pygit2.GIT_FEATURE_SSH
        mock_pygit2.GIT_FEATURE_HTTPS = pygit2.GIT_FEATURE_HTTPS

        result = pygit2_utils.pygit2_check_ssh()
        self.assertFalse(result)

    @patch("pygit2.credentials", spec={})
    def test_pygit2_check_credentials__have_keychain(self, mock_pygit2_credentials):
        """
        TestPygit2Utils:test_pygit2_check_credentials_keychain: Check for successful credentials support
        """
        mock_pygit2_credentials.KeypairFromAgent = ""
        result = pygit2_utils.pygit2_check_credentials()
        self.assertTrue(result)
