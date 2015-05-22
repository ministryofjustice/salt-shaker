
class ShakerConfigException(Exception):
    """
    Exception interpreting salt-shakers config
    files
    """
    pass


class ShakerRequirementsUpdateException(Exception):
    """
    Exception updating salt-shakers requirements
    """
    pass


class ShakerRequirementsParsingException(Exception):
    """
    Exception parsing salt-shakers requirements
    """
    pass


class ConstraintFormatException(Exception):
    """
    Exception in the format of a constraint
    """
    pass


class ConstraintResolutionException(Exception):
    """
    Exception resolving a constraint
    """
    pass


class GithubRepositoryConnectionException(Exception):
    """
    Exception caused by connection problems to github
    """
    pass
