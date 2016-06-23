import shaker.libs.logger
import paramiko
import pygit2


class Pygit2SSHUnsupportedError(Exception):
    pass


class Pygit2KepairFromAgentUnsupportedError(Exception):
    pass


class Pygit2SSHAgentMissingKeysError(Exception):
    pass


link_installation = "http://www.pygit2.org/install.html"
error_message_ssh_support = ("shaker.libs.util:check_pygit2: No SSH support found in libgit2. "
                             "Please install a version with ssh enabled (%s).\n"
                             "Note, MacOS users using brew should check the output of 'brew info libgit2' "
                             "for ssh support" % (link_installation))

error_message_credentials_support = ("shaker.libs.util:check_pygit2: Module 'KeypairFromAgent' "
                                     "not found in pygit2.features. "
                                     "Please check your pygit installation (%s)."
                                     % (link_installation))

error_message_ssh_missing_keys = ("shaker.libs.util:check_pygit2: The ssh agent doesnt appear to know "
                                  " your github key. "
                                  "Make sure you've added your key with 'ssh-add ~/.id_rsa' or similar. "
                                  " A list of the keys the agent know about can be seen with 'ssh-add -L'.")


def pygit2_parse_error(e):
    """
    Parse a pygit2 specific error into a more understandable context. Will
    also run some checks to try and help with the problem.

    Args:
        e(Exception): The exception that was raised
    """
    # Common errors to look for are,
    # AttributeError: 'module' object has no attribute 'KeypairFromAgent'
    # _pygit2.GitError: Unsupported URL protocol
    if (isinstance(e, pygit2.GitError) and e.message == "Unsupported URL protocol"):
        raise Pygit2SSHUnsupportedError(Pygit2SSHUnsupportedError)
    elif (isinstance(e, AttributeError) and e.message == "'module' object has no attribute 'KeypairFromAgent'"):
        raise Pygit2KepairFromAgentUnsupportedError(error_message_credentials_support)
    else:
        raise Pygit2SSHAgentMissingKeysError(error_message_ssh_missing_keys)


def pygit2_info():
    """
    Output key pygit2/libgit2 information
    """
    link_versions = "http://www.pygit2.org/install.html#version-numbers"
    message_versions = ("shaker.libs.util:check_pygit2: pygit2 *requires* the correct "
                        "version of libgit2, this version was built against libgit2 version '%s'. "
                        "Please check the versions on your system if you experience "
                        "problems. (For compatibility, please refer to %s)"
                        % (pygit2.LIBGIT2_VERSION, link_versions))
    shaker.libs.logger.Logger().warning(message_versions)


def pygit2_check():
    """
    Run all checks for pygit2 sanity and raise exceptions if checks fail

    Raises:
        Pygit2SSHUnsupportedError: On ssh support check failed
        Pygit2KepairFromAgentUnsupportedError: On credential support check failed
    """
    if not pygit2_check_ssh():
        raise Pygit2SSHUnsupportedError(error_message_ssh_support)
    elif not pygit2_check_credentials():
        raise Pygit2KepairFromAgentUnsupportedError(error_message_credentials_support)
    elif not pygit2_agent_has_keys():
        raise Pygit2SSHAgentMissingKeysError(error_message_ssh_missing_keys)


def pygit2_check_ssh():
    """
    Check for common pygit2 ssh problems

    Return:
        bool: True if no problems found, False otherwise
    """
    # Check for ssh support in libgit2
    if not (pygit2.features & pygit2.GIT_FEATURE_SSH):
        shaker.libs.logger.Logger().critical(error_message_ssh_support)
        return False
    message_ok = ("shaker.libs.util:pygit2_check_ssh: No ssh problems found. ")
    shaker.libs.logger.Logger().debug(message_ok)
    return True


def pygit2_check_credentials():
    """
    Check for common pygit2 credentials problems

    Return:
        bool: True if no problems found, False otherwise
    """
    link_installation = "http://www.pygit2.org/install.html"
    # Check for KeypairFromAgent support in pygit2
    if "KeypairFromAgent" not in vars(pygit2.credentials):
        shaker.libs.logger.Logger().critical(error_message_credentials_support)
        return False

    message_ok = ("shaker.libs.util:pygit2_check_credentials: No credential problems found. ")
    shaker.libs.logger.Logger().debug(message_ok)
    return True


def pygit2_agent_has_keys():
    """
    Check for common pygit2 ssh agent problems

    Return:
        bool: True if no problems found, False otherwise
    """
    agent = paramiko.Agent()
    keys = agent.get_keys()
    if len(keys) < 1:
        return False
    shaker.libs.logger.Logger().debug("shaker.libs.util:check_pygit2: "
                                      "Please check that the keys listed contain your github key...")
    for key in keys:
        shaker.libs.logger.Logger().debug("shaker.libs.util:check_pygit2: "
                                          "Found ssh agent key: %s" % key.get_base64())
    return True
