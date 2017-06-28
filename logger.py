from logging import getLogger, INFO, Formatter, FileHandler, StreamHandler
from os.path import dirname, realpath, isdir, exists
from os import makedirs
from time import strftime
from sys import stdout

# Define logging characteristics
LOGGER_NAME = "cB-Audio"
LOGGER_LEVEL = INFO

LOGGER_FORMAT = Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
LOGGER_FILE_PATH = "%s/logs" % dirname(realpath(__file__))
LOGGER_FILE_DATE = strftime("%d-%m-%y--%H-%M-%S") 
LOGGER_FILE_FORMAT = "%s/%s.log" % (LOGGER_FILE_PATH, LOGGER_FILE_DATE)

if not isdir(LOGGER_FILE_PATH):
    print("Creating new log location %s..." % LOGGER_FILE_PATH),
    makedirs(LOGGER_FILE_PATH)
    print("Done")

if not exists(LOGGER_FILE_FORMAT):
    print("Creating new log file %s..." % LOGGER_FILE_FORMAT),
    open(LOGGER_FILE_FORMAT, 'w').close()
    print("Done")

LOGGER_FILE_HANDLER = FileHandler(LOGGER_FILE_FORMAT)
LOGGER_FILE_HANDLER.setFormatter(LOGGER_FORMAT)
LOGGER_CONSOLE_HANDLER = StreamHandler(stdout)
LOGGER_CONSOLE_HANDLER.setFormatter(LOGGER_FORMAT)
LOGGER = getLogger(LOGGER_NAME)
LOGGER.addHandler(LOGGER_FILE_HANDLER)

# Uncomment when not using tornado, which already has a console handler
# LOGGER.addHandler(LOGGER_CONSOLE_HANDLER)


class logger(object):
    def __init__(self, name_space, logger_level=LOGGER_LEVEL):
        LOGGER.setLevel(logger_level)
        LOGGER.debug("Starting logger!")
        self._name_space = name_space

    def __base_log(self, to_log):
        return "|%s|: %s" % (self._name_space, str(to_log))

    def info(self, to_log):
        LOGGER.info(self.__base_log(to_log))

    def debug(self, to_log):
        LOGGER.debug(self.__base_log(to_log))

    def warning(self, to_log):
        LOGGER.warning(self.__base_log(to_log))

    def error(self, to_log):
        LOGGER.error(self.__base_log(to_log))
