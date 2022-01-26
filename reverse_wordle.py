#!/usr/bin/python3

# Attempt at implementing reverse wordle:
# Try to guess the word of the day by looking at all
# the wordle scores (i.e. hints) people have posted
# on Twitter
#
# Unfortunately this one doesn't work very well
# After incorporating about 10 sets of hints,
# the candidates had only narrowed down to 700ish
#
# Including this just in case someone wants to try
# improving the algorithm

from pathlib import Path
import shelve

import logging
logger = logging.getLogger(__name__)


MYDIR = Path(__file__).parent
WORDS_FILE = MYDIR/"wordle_words.txt"
DICT_FILE = MYDIR/"wordle_dict.txt"
INV_INDEX = MYDIR/"inv_index.shv"


HINTS_MAP = {
    '⬛': 'b',   # black/grey: letter not in word
    '⬜': 'b',   # same
    '🟨': 'y',  # yellow: letter in word but wrong position
    '🟩': 'g',  # green: letter in correct position
}


def canonical_hint(letter: str) -> str:
    return HINTS_MAP[letter] or letter


def canonical_hint_str(hint_str: str) -> str:
    hint_str = hint_str.lower().strip()
    if hint_str in ('', 'end', 'show'):
        return
    return ''.join(canonical_hint(letter) for letter in hint_str)


def hint(word: str, letter: str, index: int) -> str:
    '''Return a wordle hint for one `letter` which is at `index' in guess

    `word` is the actual word. 
    return 'b', 'y' or 'g' as the hint'''
    if letter in word:
        if word[index] == letter:
            return 'g'
        else:
            return 'y'
    else:
        return 'b'

def get_hint_str(word: str, guess: str) -> str:
    '''Return a string of length 5, each letter is a b,y,g hint

    If `word` is the real word and `guess` is a guess the
    return value is the 5-letter hint
    '''
    return ''.join([hint(word, letter, idx)
                    for idx, letter in enumerate(guess)])


def create_inverted_indexes() -> None:
    with shelve.open(str(INV_INDEX), writeback=True) as inv_index:
        wordle_words = set(open(WORDS_FILE, 'r').read().split())
        wordle_dict = set(open(DICT_FILE, 'r').read().split())
        all_words = wordle_dict | wordle_words
        for i, word in enumerate(wordle_words):
            logger.debug(f'Starting word number {i}: {word}')
            for guess in all_words:
                hint_str = get_hint_str(word, guess)
                if hint_str not in inv_index:
                    inv_index[hint_str] = set()
                inv_index[hint_str].add(word)
            # shelve.sync()


def reverse_wordle() -> None:
    with shelve.open(str(INV_INDEX), writeback=True) as inv_index:
        candidates = None
        accumulate = []
        while True:
            hint_str = input('Next hint: ')
            hint_str = canonical_hint_str(hint_str)
            if not hint_str or hint_str == 'ggggg':
                # 'ggggg' gives us no new information
                continue
            if hint_str == 'end':
                break
            matches = inv_index[hint_str]
            if not candidates:
                candidates = matches
            else:
                candidates &= matches
            status = f'{hint_str} {len(candidates)}'
            accumulate.append(status)
            print(status)
        print(f'Reverse Wordle {len(accumulate)}')
        print('\n'.join(accumulate))

if __name__ == '__main__':
    logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    # create_inverted_indexes()
    reverse_wordle()
