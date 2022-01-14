#!/usr/bin/python3

from collections import defaultdict
from enum import Enum
import math
from pathlib import Path
import re
from typing import NamedTuple

import logging
logger = logging.getLogger(__name__)


# TODO: These should become commandline options using argparse
MYDIR = Path(__file__).parent
WORDFREQ_FILE =  MYDIR/"wordfreq.txt"
NUMBER_OF_EXPLORE_ROUNDS = 2
# If there are no candidate words generated in EXPLORE mode
# the algorithm automatically switches to GUESS mode.
# Thus setting this variable to a large number (i.e. 6 or more)
# is equivalent to saying that the algorithm should decide
# when to switch to GUESS mode
VALID_WORDS_FILE = MYDIR/"unix_words.txt"


# The words used by WORDLE are visible in the JavaScript
# file used by Wordle. Thus, it is possible to use those
# words directly. However, I feel that using Wordle's word list
# is a little bit of cheating. So it is not used by default.
CHEAT_BY_USING_WORDLE_WORDS = False
if CHEAT_BY_USING_WORDLE_WORDS:
    VALID_WORDS_FILE = MYDIR/"wordle_words.txt"

# set this to a small value like 0.1
# to implement @ainvvy's heuristic of using words
# with mostly consonants during EXPLORE mode (e.g. MONTH)
#
# Or set it to a large value like 20 to
# implement the opposite heuristic of using
# words with mostly vowels during EXPLORE mode (e.g. ADIEU) 
# The default value of 1 gives both equal importance
VOWEL_MULTIPLIER = 1


MODE = Enum("MODE", "EXPLORE GUESS")


class Wordle:
    '''
    In EXPLORE mode, we are not trying to guess the correct word; 
    we are just trying to gather information about which *other* letters
    are there in the word. So we only include letters that are not
    contained in any of the exact_matches, or the disallowed_letters, 
    or the included_letters. 

    In GUESS mode, we try to guess the correct word, so we
    only include words where the exact_matches are in the correct
    places, *all* the included letters are there in the word, and
    none of the disallowed_letters are there.
    '''
    def __init__(self):
        self.mode = MODE.EXPLORE  # start in EXPLORE mode

        # exact_matches is just a list of 5 letters
        # A None at any position indicates that we don't
        # know the exact match
        self.exact_matches: list[None|str] = [None] * 5

        # set of letters which are *not* present in the word
        # updated after every hint
        self.disallowed_letters: set[str] = set()

        # set of letters which are present in the word
        # but not (necessarily) in the correct place
        self.included_letters: set[str] = set()

        # How many rounds we've completed so far
        self.guesses = 0

        # Words which exist in our word list but
        # which are not in Wordle's list, so wordle
        # rejects them as "Not a word"
        # We need to ensure that we don't submit
        # these words again
        self.bad_guesses: dict[str, bool] = {}

        # dictionary of word to log(frequency) of this
        # word in Google Web Trillion Word Corpus
        self.wordfreqs = self.get_wordfreqs()

    def get_wordfreqs(self) -> dict[str, float]:
        '''
        Read word frequencies from the WORDFREQ_FILE

        However, most of the words in the WORDFREQ_FILE
        are not real words, since it has just taken "words"
        from websites, so they contain misspelled words,
        and a whole bunch of other letter sequences.

        Hence, we need to use the VALID_WORDS_FILE to
        ensure that we only use real words. 

        Convert the integer frequencies to "log" because
        that will give better behavior in our algorithms
        '''
        wordfreqs: dict[str, float] = {}
        with open(VALID_WORDS_FILE, 'r') as f:
            valid_regexp = re.compile(r'^[a-z]{5}$')
            valid_words = set(
                word
                for line in f
                if valid_regexp.match(word := line.strip().lower()))

        with open(WORDFREQ_FILE, 'r') as f:
            for line in f:
                if not line:
                    continue
                word, freq = line.split()
                freq = int(freq)

                if word not in valid_words:
                    # lots of crap in google's dataset
                    continue

                wordfreqs[word] = math.log(int(freq))

        logger.info(f'Read {len(wordfreqs)} words')
        return wordfreqs
 
    def regexp_guess(self) -> str:
        '''
        Get a regexp that will match allowed words in GUESS mode

        Every exact match must be in its place
        All other locations can have any letter that is not 
        in disallowed_letters

        Note: letters from exact_matches
        are also included because they could be repeated
        '''
        allowed_letters = ''.join(sorted(self.disallowed_letters))
        if not allowed_letters:
            allowed_regexp = '[a-z]'
        else:
            allowed_regexp = f'[^{allowed_letters}]'
        all_letters = ''.join(e if e else allowed_regexp
                              for e in self.exact_matches)
        # At this point all_letters will have exactly 5 letters
        logger.debug(f'Using regexp: ^{all_letters}$')
        return f'^{all_letters}$'

    def regexp_explore(self) -> str:
        '''
        Get a regexp that will match allowed words in EXPLORE mode

        In explore mode, an allowed word is simply any word consisting
        of only letters that are not in exact_matches or disallowed_letters
        or included_letters. This is because we are just trying to
        gather information about which words are there in the word and 
        which ones aren't
        '''
        skip_letters = ''.join(sorted(
            self.disallowed_letters |
            self.included_letters |
            set(e for e in self.exact_matches if e)
        ))
        if not skip_letters:
            logger.debug('Using NO regexp')
            return '^.{5}$'
        else:
            logger.debug(f'Using regexp ^[^{skip_letters}]{{5}}$')
            return f'^[^{skip_letters}]{{5}}$'

    def word_score_guess(self, word: str) -> float:
        '''
        In GUESS mode, score of a word is simply frequency of the word

        Of all the eligible words we want to guess the one that is
        most frequent in the real world corpus
        '''
        return self.wordfreqs[word]

    def compute_letter_scores(self, regexp) -> None:
        '''
        A letter_score is just the sum of freq's of all the
        words that the letter appears in. (If the letter
        appears in a word twice then the freq is counted twice. 
        This is because that letter is more important.)

        This method recomputes all the letter scores after 
        each round. Based on the constraints so far, it is
        the list of candidate words changes, and as a result
        the letter scores will also change dynamically.
        '''

        self.letter_scores: dict[str, float] = defaultdict(float)
        for word, freq in self.wordfreqs.items():
            if regexp.match(word):
                for letter in word:
                    if self.mode == MODE.EXPLORE and letter in 'aeiou':
                        # Use VOWEL_MULTIPLIER to decide whether to
                        # give higher importance to words with Vowels
                        # (or lower)
                        freq *= VOWEL_MULTIPLIER
                    self.letter_scores[letter] += freq

    def word_score_explore(self, word: str) -> float:
        '''
        In EXPLORE mode, score of a word = sum of the current letter scores

        Note: in explore mode we want to maximize the number of letters in
        the word, so if a letter shows up multiple times in the word
        it is counted only once. (Hence the set(word))

        Depending on the constraints, only a subset of all the
        words are now eligible. 
        '''
        return sum(self.letter_scores[letter] for letter in set(word))

    def regexp(self) -> re.Pattern:
        '''
        Return correct regexp to find eligible words based on mode
        '''
        match self.mode:
            case MODE.EXPLORE:
                return re.compile(self.regexp_explore())
            case MODE.GUESS:
                return re.compile(self.regexp_guess())

    def word_score(self, word: str) -> float:
        match self.mode:
            case MODE.EXPLORE:
                return self.word_score_explore(word)
            case MODE.GUESS:
                return self.word_score_guess(word)

    def decide_mode(self) -> None:
        '''
        Decide which MODE we want to be in

        If NUMBER_OF_EXPLORE_ROUNDS is set to a small number like
        2 or 3, the algorithm will use only that many rounds
        of EXPLORE and then switch to GUESS

        Is it possible to do something more clever based on the number of
        eligible words remaining?

        Note: if in EXPLORE mode the number of candidate words is 0
        then the algorithm automatically switches to GUESS mode.
        Thus setting NUMBER_OF_EXPLORE_ROUNDS to 6 or more
        is equivalent to saying: EXPLORE for as long as possible
        and then switch to GUESS
        '''
        if self.guesses >= NUMBER_OF_EXPLORE_ROUNDS:
            self.mode = MODE.GUESS
        

    def add_hints(self, guess: str, hint_str: str) -> None:
        '''
        Incorporate hints provided by Wordle 

        hint_str is a 5 letter word with the following meanings:

        b: black: this letter is not in the word
        y: yellow: this letter is in the word but in the wrong position
        g: green: this letter is in the correct position
        '''
        for pos, (letter, hint) in enumerate(zip(guess, hint_str)):
            match hint:
                case 'b':
                    self.disallowed_letters.add(letter)
                case 'y':
                    self.included_letters.add(letter)
                case 'g':
                    self.exact_matches[pos] = letter
                case _:
                    raise ValueError(f'Unknown letter {letter} in hints')

    def eligible(self, word):
        '''Extra eligiblity check (after regexp check succeeds)

        In case of GUESS mode, we need to check whether the 
        self.included_letters are present in the word

        Because, there isn't a good way to incorporate 
        self.included_letters in the regexp
        '''
        match self.mode:
            case MODE.EXPLORE:
                return True
            case MODE.GUESS:
                # TODO: this is broken for double letters
                # self.included_letters shouldn't be a set
                return self.included_letters <= set(word)


    def guess(self) -> str:
        '''
        Return the next guess

        Shortlist and score words based on mode, then return
        the highest scoring word

        Note: in the code below, both, the regexp and the word_score
        will be different depending on the mode

        Returns None if no eligible word found. 
        '''
        best_word = (None, 0)
        regexp = self.regexp()
        self.compute_letter_scores(regexp)
        matches = 0
        for word, freq in self.wordfreqs.items():
            if word in self.bad_guesses:
                # Any word that has been rejected by Wordle
                # as 'Not a word' should not be guessed again
                continue
            if regexp.match(word):
                if not self.eligible(word):
                    continue
                matches += 1
                score = self.word_score(word)
                if score > best_word[1]:
                    best_word = (word, score)
        logger.debug(f'{matches=}')
        return best_word[0]
        

    def play(self):
        while True:
            guess = self.guess()
            if guess is None and self.mode == MODE.EXPLORE:
                # if explore mode doesn't have any candidates
                # switch to GUESS mode
                self.mode = MODE.GUESS
                continue
            print(f'Guess: {guess}')
            hint_str = input('How did that go? Type hints: ').strip()
            if hint_str == 'bad':
                self.bad_guesses[guess] = True
            else:
                self.add_hints(guess, hint_str)
                self.guesses += 1
                self.decide_mode()


if __name__ == '__main__':
    logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    wordle = Wordle()
    wordle.play()
