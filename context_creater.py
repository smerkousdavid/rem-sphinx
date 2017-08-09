

class ContextBase(object):
    def __init__(self, dictionaries=[]):
        self._dictionaries = dictionaries

    def load_dictionaries(self, dictionaries):
