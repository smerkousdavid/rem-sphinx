# -*- coding: utf-8 -*-
"""RemSphinx speech to text processing nltk download

This module is designed to just purely download all of the nltk
corpous, collection, and model packages.

Developed by: David Smerkous
"""

from sys import exit

import nltk

print("Starting the installation...")

nltk.download("all")

print("Running a few tests...")
try:
    print("Tokenizing a string... "),
    _ = nltk.tokenize.word_tokenize("Tokenize this string please.")
    print("PASSED")
except Exception as err:
    print("FAILED (err: %s)" % str(err))
    exit(1)

test_languages = ["english", "german", "french", "russian"]

for test_language in test_languages:
    try:
        print("Testing stopwords for %s..." % test_language),
        a = nltk.corpus.stopwords.words(test_language)
        print("PASSED")
    except Exception as err:
        print("FAILED (err: %s)" % str(err))
        exit(1)

print("Done. Finished the installation!")
