# -*- coding: utf-8 -*-
"""CloudyBoss speech to text processing configuration files

This module is designed to load the local language configuration files
for the dynamic use of languages on the server. Please look at the config.json file
to see all of the server application configurations.

Developed by: David Smerkous
"""

from json import loads, dumps
from sys import exit
from os.path import dirname, realpath, join, exists
from os import sep
from logger import logger
from threading import Thread

import re
import pyinotify

log = logger("CONFIGS")

CONFIG_FILE = "configs/config.json"
CONFIGS = {}
"""Global module level definitions
logger: log - The module log object so that printed calls can be backtraced to this file
str: CONFIG_FILE - The relative path and filename of the configs json
dict: CONFIGS - The global configurations for all other modules
"""

class LanguageModel(object):
    """Language model to handle language enum types

    Attributes:
       _model_name (str): The generic name of the language model name (ex: English)
       _model_hmm (str): The absolute path to the Hidden Markov Models (Language statistical analysis)
       _model_lm (str): The absolute path to the language model bin (The core processor to capture the phonetics)
       _model_dict (str): The absolute path to the language N-Gram dictionary (The table lookup for the phonetics to words)

    """
    def __init__(self, m_name = None, m_hmm = None, m_lm = None, m_dict = None):
        """LanguageModel constructor

        Args:
            m_name (str): The generic name of the language model name (ex: English)
            m_hmm (str): The absolute path to the Hidden Markov Models (Language statistical analysis)
            m_lm (str): The absolute path to the language model bin (The core processor to capture the phonetics)
            m_dict (str): The absolute path to the language N-Gram dictionary (The table lookup for the phonetics to words)
        """

        # Check for nulls before passing through the property functions
        if m_name is None:
            self._model_name = None
        else:
            self.name = m_name
        
        if m_hmm is None:
            self._model_hmm = None
        else:
            self.hmm = m_hmm

        if m_lm is None:
            self._model_lm = None
        else:
            self.lm = m_lm

        if m_dict is None:
            self._model_dict = None
        else:
            self.dict = m_dict

    def is_valid_model(self):
        """Private method to check and see if the model is valid

        Note:
            This will not fix the model if it's currently broken!

        Returns: (bool)
            True if the model is valid, else, False
        """
        
        # If any of the model paths are none, then return a False
        if None in [self.hmm, self.lm, self.dict]:
            return False
        return True


    @property
    def name(self):
        """str: model name property
            
        Get the current language model name
        """
        return self._model_name

    @name.setter
    def name(self, name):
        # Check to see if hmm is a string
        if not isinstance(name, basestring):
            raise TypeError("name must be a string!")

        if len(name) == 0:
            raise ("The name cannot be blank")
        self._model_name = name

    @property
    def hmm(self):
        """str: hmm absolute path property
            
        Get the current path to the Hiden Markov Models
        """
        return self._model_hmm

    @hmm.setter
    def hmm(self, hmm):
        # Check to see if hmm is a string
        if not isinstance(hmm, basestring):
            raise TypeError("hmm must be a string!")

        # Check to see if the hmm file exists
        if not exists(hmm):
            raise SystemError("hmm doesn't exist!")
        self._model_hmm = hmm

    @property
    def lm(self):
        """str: lm absolute path property
            
        Get the current path to the language model bin
        """
        return self._model_lm

    @lm.setter
    def lm(self, lm):
        # Check to see if lm is a string
        if not isinstance(lm, basestring):
            raise TypeError("lm must be a string!")

        # Check to see if the lm file exists
        if not exists(lm):
            raise SystemError("lm doesn't exist!")
        self._model_lm = lm

    @property
    def dict(self):
        """str: dict absolute path property
            
        Get the current path to the N-Gram dictionary
        """
        return self._model_dict

    @dict.setter
    def dict(self, ngrams):
        # Check to see if ngrams is a string
        if not isinstance(ngrams, basestring):
            raise TypeError("dict must be a string!")

        # Check to see if the ngrams file exists
        if not exists(ngrams):
            raise SystemError("dict doesn't exist!")
        self._model_dict = ngrams

class Configs(object):
    """Configs handler and dynamic file change detection

    Attributes:
        _current_dir (str): The current global working directory 
        _json_config (str): The path to the json config file
    """

    class __ConfigFileEventHandler(pyinotify.ProcessEvent):
        """Config file change handler

        Attributes:
            _config_file (str): The full path of the configuration file to watch for
            _config_reload (obj: method): The method reference to reload the configuration file

        Note:
            This is a nested class for the sole purpose that the other
            Classes do not need access to this ConfigEvent listener
        """
        def __init__(self, config_file, config_reload):
            self._config_file = config_file
            self._config_reload = config_reload

        def process_IN_CLOSE_WRITE(self, event):
            """Pyinotify's method of handling file modification

            Note:
                This is called in the backend of pyinotify and can be called on ANY file
                within the selected folder. This is just the front end handler.
            """
            if self._config_file in event.pathname: # Make sure we are only checking for the loaded configuration file and not some other file
                log.info("The config file %s has been modified!" % event.pathname)
                log.info("Reloading configurations!")
                self._config_reload() # Reload the configuration files
                log.info("Reloading complete!")

    def __init__(self):
        self._current_dir = dirname(realpath(__file__)) 
        self._json_config = self.get_full_path(CONFIG_FILE)
        if not self.__load_configs(): # Attempt to read from the configuration file
            exit(0) # Exit the program on the first configuration error
        log.info("Succesfully loaded initial configs from %s" % self._json_config)

        # Create and attach the inotify file watch for the configuration files
        self._wm = pyinotify.WatchManager()
        self._handler = Configs.__ConfigFileEventHandler(self._json_config, self.__load_configs)
        self._notifier = pyinotify.Notifier(self._wm, self._handler)
        self._wdd = self._wm.add_watch(dirname(self._json_config), pyinotify.IN_CLOSE_WRITE)

        # Create and start the config file event loop
        self._event_thread = Thread(target=self._notifier.loop)
        self._event_thread.setName("ConfigFileEventLoop")
        self._event_thread.setDaemon(True)
        self._event_thread.start()

    @staticmethod
    def get_available_languages():
        """Method to return all language codes from the configuration file

        Returns: (:obj: dict - string pairs)
            Pairs of language names and id's
        """
        try:
            return CONFIGS["language_codes"]
        except Exception as err:
            log.error("Failed loading available languages! (err: %s)" % str(err))
            return None

    @staticmethod
    def get_language_name_by_id(l_id):
        """Method to return the language model name based on the id

        Arguments:
            l_id (int): The language model id to get the language model name

        Returns (str):
            The language model name
        """

        try:
            a_l = Configs.get_available_languages()
            if a_l is None:
                return None
            return a_l[str(l_id)]
        except Exception as err:
            log.error("Failed getting language name by id! (id: %d) (err: %s)" % (l_id, str(err)))
            return None

    @staticmethod
    def get_stt():
        global CONFIGS
        """Public method to get the current stt configurations

        Returns: (dict)
            The STT configuration object
        """
        return CONFIGS["stt"]

    def get_stt_data(self, l_id):
        """Method to return all speech to text configuration data

        Arguments:
            l_id (int): The language model id to get speech to text data from
        
        Returns (LanguageModel)
        """

        try:
            n_id = str(l_id) # Turn the id into a str because the json only accepts str keys
            name = Configs.get_language_name_by_id(l_id)
            stt = Configs.get_stt() # Get the speech to text sub objects
            model_data = self.parse_config_path(stt["model_dir"]) # Parse the model directory from the configuration file
            # Get the current language's model data
            m_hmm = join(model_data, stt["hmm"][n_id])
            m_lm = join(model_data, stt["lm"][n_id])
            m_dict = join(model_data, stt["dict"][n_id])
            return LanguageModel(name, m_hmm, m_lm, m_dict) # Create the new language model object
        except Exception as err:
            log.error("Failed loading language model! (id: %d) (err: %s)" % (l_id, str(err)))
            return None

    @staticmethod
    def dump_configs(configs):
        """Json dumps wrapper to printy print dicts to the console

        Arguments:
            configs (dict): The dictionary to log with indendation

        Note:
            This will only print in the CONFIGS namespace
        """

        try:
            log.info("Configurations:\n%s" % dumps(configs, indent=4))
        except Exception as err:
            log.error("Failed to dump json! (err: %s)" % str(err))

    def __load_configs(self):
        global CONFIGS
        """Private method to reload the configuration file

            Note:
                This should really only be called on configs creation and on the file change listener

            Returns: (bool)
                True on success or False on failure to load configurations:we
        """

        try:
            c_f = open(self._json_config, 'r') # Open the config file for reading
            c_f_data = c_f.read()
            CONFIGS = loads(c_f_data)
            c_f.close()

            # Log the new configurations
            log.info("Dumping configs")
            Configs.dump_configs(CONFIGS)
            return True
        except Exception as err:
            log.error("Failed to load configuration file! (err: %s)" % str(err))
            if c_f is not None:
                c_f.close()
        return False

    def get_cwd(self):
        """Return the absolute path of the current working directory

        Returns: (str)
            The absolute path of the current working directory
        """

        return self._current_dir

    def get_full_path(self, relative_path):
        """Return the absolute path of a file that's located relative to the absolute path

        Returns: (str)
            The absolute path of the current file that's relative to the path
        """

        return join(self.get_cwd(), relative_path)

    def parse_config_path(self, path_parse):
        """Method to replace common path symbols in the configuration files

        Note:
            If there's a path separator at the end of the path, then this method will remove it

        Arguments:
            path_parse (str): The configuration symbolic filled path to be parsed

        Returns: (str)
            The parsed and non-symbolic and non-variabled path data
        """

        try:
            cwd = self.get_cwd()
            if cwd[-1] == sep:
                cwd = cwd[:len(cwd) - 2]
            path_parse = re.sub(r'\(!CWD!\)', cwd, path_parse)
            return path_parse
        except Exception as err:
            log.error("Failed parsing config path! (path: %s) (err: %s)" % (path_parse, str(err)))
            return None

#log.debug("YES")
#c = Configs()
#while True:
#    pass
