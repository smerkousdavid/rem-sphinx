# -*- coding: utf-8 -*-
"""RemSphinx speech to text processing text files

This module is for the text processing of the RemSphinx system. It will handle keyphrases,
synonyms, and antonyms for simplifying and improving the Speech To Text results.

Developed by: David Smerkous
"""

from logger import logger
from configs import NLTKModel, Configs
from collections import defaultdict
from itertools import chain, groupby, product
from nltk.tokenize import wordpunct_tokenize

import string
import nltk

log = logger("TEXTPR")


class TextProcessor(object):
    def __init__(self):
        self._nltk_model = None
        self._stop_words = None
        self._frequency_dist = None
        self._degree = None
        self._rank_list = None
        self._ranked_phrases = None
        self._ignore_list = set()
        self._punctuation = list(string.punctuation) # Load the entire (default) puncuation list

    def set_nltk_model(self, nltk_model):
        """Method to set the TextProcessor's language model

        Note:
            This will reload the NLTK model data and this may take some time

        Arguments:
            nltk_model (NLTKModel): The loaded nltk model to be processed
        """

        self._nltk_model = nltk_model
        self._stop_words = nltk.corpus.stopwords.words(self._nltk_model.stop_words) # Load the nltk stopwords list
        self._ignore_list = set(self._stop_words + self._punctuation)

    def get_sentences(self, text):
        """Method to extract sentences from the text

        Arguments:
            text (str): The text to extract keyphrases from

        """
        return nltk.tokenize.sent_tokenize(text)

    def generate_keyphrases(self, text):
        """Method to extract keyphrases from the text

        Arguments:
            text (str): The text to extract keyphrases from
        """
        sentences = self.get_sentences(text) # Get all the sentences from the text
        self.generate_keyphrases_from_sentences(sentences) # Process each sentence individually

    def generate_keyphrases_from_sentences(self, sentences):
        """Method to extract keyphrases from a list of sentences

        Arguments:
            sentences (:obj: list - str): A list of strings that represent sentences
        """
        phrase_list = self.__make_phrases(sentences)

        if phrase_list is None:
            log.error("The nltk model has not yet been loaded. Failed processing keyphrases!")
            return

        self.__frequency_distribution(phrase_list)
        self.__word_co_occurance_graph(phrase_list)
        self.__ranklist(phrase_list)

    def get_keyphrases(self):
        """Method to return the processed keyphrases and their scores
        
        Returns: (list)
            A list of tuples where each tuple is a keyphrase and the associated score
        """
        return self._rank_list

    def __frequency_distribution(self, phrase_list):
        """Builds a frequency distribution of the words inside the phrase list

        Arguments:
            phrase_list (list): A list of list of strings that have an association with each other
        
        Note:
            For those of you who don't understand what frequency means. All it means is the total
            count of word in a sentence. Lets say that "I have two dogs, and I have two cats." The
            frequency of "I" is 2, and the frequency of "dogs" is 1.
        """
        self._frequency_dist = defaultdict(lambda: 0) # Populate the list with 0 (0 word maps)
        for word in chain.from_iterable(phrase_list):
            self._frequency_dist[word] +=1

    def __word_co_occurance_graph(self, phrase_list):
        """Builds a co-occurance graph of words in the phrase_list

        Arguments:
            phrase_list (list): A list of list of strings that have an association with each other

        """
        co_occurance_graph = defaultdict(lambda: defaultdict(lambda: 0)) # Create a default dictionary with a secondary subset of dictionaries

        for phrase in phrase_list:

            # Process within a secondary (nested) for loop
            for (word, coword) in product(phrase, phrase):
                co_occurance_graph[word][coword] += 1 # Add the phrase product occurance to each word and sub co-word mathc

        self._degree = defaultdict(lambda: 0)
        for key in co_occurance_graph:
            self._degree[key] = sum(co_occurance_graph[key].values()) # Add all co-word phrase matches to the degree associated with the top-level word

    def __ranklist(self, phrase_list):
        """Method to rank each phrase

        Arguments:
            phrase_list (list): A list of list of strings that have an association with each other
        """
        self._rank_list = []
        for phrase in phrase_list:
            rank = 0.0
            for word in phrase:
                rank += 1.0 * self._degree[word] / self._frequency_dist[word] # The higher the frequencey the lower the rank (depening on the occurance count of the word in that same phrase)
            self._rank_list.append((rank, ' '.join(phrase))) # Add the rank and the associated phrase
        self._rank_list.sort(reverse=True) # We want the highest rank to be first
        self._ranked_phrases = [ph[1] for ph in self._rank_list] # We only want the ranked phrases

    def __make_phrases(self, sentences):
        """Method to create co-related phrases from a list of sentences

        Arguments:
            sentences (:obj: list - str): A list of strings that represent sentences
        
        Returns (set):
            A set of string tuples where each tuple is a subgrouped phrase
        """
        phrase_list = set()

        for sentence in sentences:
            word_list = [word.lower() for word in wordpunct_tokenize(sentence)] # Extract a list of words from the sentence string
            phrase_list.update(self.__get_phrase_list(word_list))
        return phrase_list

    def __get_phrase_list(self, word_list):
        """Method that extracts phrases from a word_list and seperates common punctuation
        to subgroup phrases to then be used as keyphrases

        Arguments:
            word_list (list): A list of words that should be an exact copy of original sentence if joined back together

        Returns: (list)
            A list of subgrouped phrase
        """
        if self._ignore_list is None:
            return None

        phrase_list = []
        for group in groupby(word_list, lambda x: x in self._ignore_list):
            if not group[0]:
                phrase_list.append(tuple(group[1]))
        return phrase_list
