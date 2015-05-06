import logging


class Logger(object):

    # Singleton class for our logger
    class __Logger:
        def __init__(self, logger_name):
            self.logger_name = logger_name

        def __str__(self):
            return repr(self) + self.logger_name

        logger_name = ''

        def setLevel(self, level):
            logging.info("Logger::setLevel: Logging level '%s' enabled"
                         % level)
            logging.getLogger(self.logger_name).setLevel(level)

        def info(self, msg):
            logging.getLogger(self.logger_name).info(msg)

        def warning(self, msg):
            logging.getLogger(self.logger_name).warning(msg)

        def error(self, msg):
            logging.getLogger(self.logger_name).error(msg)

        def critical(self, msg):
            logging.getLogger(self.logger_name).critical(msg)

        def debug(self, msg):
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
