import numpy as np
import pytest
from pydub.generators import Sine

from speechsplit import (SPEAKER_CLASS, TRANSLATOR_CLASS, build_training_data,
                         extract_audio_features, smooth_bumps,
                         split_by_silence)


def example_lines(example):
    '''Test util that converts a spec string to a list of lines

    Ignore:
        * empty lines
        * lines starting with "___"
        * lines starting with "#"

    and discard "|" at line borders'''
    return [line.strip('|') for line in example.strip().splitlines()
            if (line and
                not line.startswith('___') and
                not line.startswith('|___') and
                not line.startswith('#'))]


def pairs(items):
    "Test util that returns a list of pairs from a sequence"
    items = iter(items)
    return zip(items, items)


def test_pairwise():
    assert pairs([]) == []
    assert pairs([1, 2, 3]) == [(1, 2)]
    assert pairs([1, 2, 3, 4]) == [(1, 2), (3, 4)]


# upper line is the input and bottom one the output
smooth_bumps_examples = pairs(example_lines('''
_______________|
    ...    ....|
           ....|
_______________|
..     ......  |
       ......  |
_______________|
'''))


@pytest.mark.parametrize('data, output', smooth_bumps_examples)
def test_smooth_bumps(data, output):
    data = np.array(list(data))
    smooth_bumps(data, '.', margin=4, width=3)
    assert ''.join(data) == output


SPE, TRA = SPEAKER_CLASS, TRANSLATOR_CLASS
___, BIG = False, True


AUDIO_STUB = Sine(440).to_audio_segment(10100)


# remove lru caching for testing
extract_audio_features = extract_audio_features.__wrapped__


@pytest.mark.parametrize('size', [100, 333])
def test_split_does_not_change_extract_audio_features(size):
    assert len(AUDIO_STUB) == 10100
    mfcc1, loud1 = extract_audio_features(AUDIO_STUB)  # no segmentation
    mfcc2, loud2 = extract_audio_features(
        AUDIO_STUB, max_windows_per_segment=size)
    assert np.all(np.isclose(mfcc1, mfcc2))
    assert np.all(np.isclose(loud1, loud2))


@pytest.mark.xfail(raises=AssertionError)
def test_split_too_small_in_extract_audio_features():
    extract_audio_features(AUDIO_STUB, max_windows_per_segment=10)


# examples of how split by silence must work
# each X corresponds to a loud audio section of 100 ms
# each dot (.) corresponds to a silent audio section of 100 ms
# each space marks a split point
# numbers mark the starts of split intervals
silence_split_examples = pairs(example_lines('''
________________________________________
# only silence
 .....
 0
________________________________________
# only NON silence
 XXXXX
#012345
 0    5
________________________________________
# starting and finishing WITHOUT silence

 XX ....XXX.XX
#01 23456789012
 0  2         12
________________________________________
# starting and finishing WITH silence

 ....XXX ...XX.XXX ...XX...
#0123456 789012345 678901234
 0       7         16      24
________________________________________
'''))
LOUD_OR_SILENT = {'X': AUDIO_STUB[:100],                  # loud
                  '.': AUDIO_STUB[:100].apply_gain(-40)}  # quiet
silence_split_examples = [
    (sum(LOUD_OR_SILENT[w] for w in segment if w in 'X.'),
     [int(s) * 10 for s in starts.split()])
    for segment, starts in silence_split_examples
]

assert LOUD_OR_SILENT['X'].dBFS > -20
assert LOUD_OR_SILENT['.'].dBFS < -20


@pytest.mark.parametrize('audio, starts', silence_split_examples)
def test_split_by_silence(audio, starts):
    intervals = zip(starts, starts[1:])
    assert intervals == split_by_silence(
        audio, max_silence_loudness=-20, min_silence_len=20)


@pytest.mark.parametrize(
    'speaker_features, translator_features, X_all, y_all', [[
        (
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            [___, BIG, ___, ___, ___, BIG, BIG, BIG, BIG, ___],
        ),
        (
            [0.1, 1.1, 2.1, 3.1, 4.1, 5.1, 6.1],
            [___, BIG, ___, ___, ___, BIG, BIG],
        ),
        [1.0, 5.0, 6.0, 7.0, 8.0, 1.1, 5.1, 6.1],
        [SPE, SPE, SPE, SPE, SPE, TRA, TRA, TRA]
    ], ])
def test_build_training_data(
        speaker_features, translator_features, X_all, y_all):

    speaker_features, translator_features, X_all, y_all = map(
        np.array, (speaker_features, translator_features, X_all, y_all))

    X, y = build_training_data(
        speaker_features, translator_features,
        lambda mfcc, loudness: mfcc[loudness.astype(bool)])
    assert all(X_all == X)
    assert all(y_all == y)
