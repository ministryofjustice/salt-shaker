import logging


class Logger(object):

    """
    A wrapped logger class that allows us to implement a
    singleton.
    """

    class __Logger:
        """
        Class that enables singleton behaviour
        """
        def __init__(self, logger_name):
            """
            Initialise singleton

            Args:
                logger_name(string): The name of the logger
            """
            self.logger_name = logger_name

        def __str__(self):
            """
            Get a string representation of this instance

            Returns:
                (string): String representation of this instance
            """
            return repr(self) + self.logger_name

        logger_name = ''

        def setLevel(self, level):
            """
            Set logging to be at level

            Args:
                level(logging.LEVEL): The logging level to set
            """
            logging.info("Logger::setLevel: Logging level '%s' enabled"
                         % level)
            logging.getLogger(self.logger_name).setLevel(level)

        def info(self, msg):
            """
            Log message at level info

            Args:
                msg(string): The message to log
            """
            logging.getLogger(self.logger_name).info(msg)

        def warning(self, msg):
            """
            Log message at level warning

            Args:
                msg(string): The message to log
            """
            logging.getLogger(self.logger_name).warning(msg)

        def error(self, msg):
            """
            Log message at level error

            Args:
                msg(string): The message to log
            """
            logging.getLogger(self.logger_name).error(msg)

        def critical(self, msg):
            """
            Log message at level critical

            Args:
                msg(string): The message to log
            """
            logging.getLogger(self.logger_name).critical(msg)

        def debug(self, msg):
            """
            Log message at level debug

            Args:
                msg(string): The message to log
            """
            logging.getLogger(self.logger_name).debug(msg)

    # Wrapping singleton class begins
    instance = None

    def __new__(cls, logger_name="default"):
        if not Logger.instance:
            Logger.instance = Logger.__Logger(logger_name)
        return Logger.instance

    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __setattr__(self, name):
        return setattr(self.instance, name)
