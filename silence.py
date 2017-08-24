
import itertools
import os
from hashlib import sha1

import yaml
from functools32 import lru_cache
from pydub.silence import detect_silence
from unstdlib import listify

SILENCE_LEVELS = [{'silence_thresh': t, 'min_silence_len': l}
                  for t in range(-42, -33)
                  for l in range(500, 100, -100)]
NO_LABEL = '?'


def detect_silence_and_audible(audio_segment, level=0):
    '''Splits audios segments in chunks separated by silence.
    Keep the silence in the beginning of each chunk, as possible,
    and ignore silence after the last chunk.'''

    silent_ranges = detect_silence(audio_segment, seek_step=10,
                                   **SILENCE_LEVELS[level])
    len_seg = len(audio_segment)

    # make sure there is a silence at the beginning (even an empty one)
    if not silent_ranges or silent_ranges[0][0] is not 0:
        silent_ranges.insert(0, (0, 0))
    # make sure there is a silence at the end (even an empty one)
    if silent_ranges[-1][1] is not len_seg:
        silent_ranges.append((len_seg, len_seg))

    return [[start, end, start_next, level]
            for (start, end), (start_next, __) in zip(silent_ranges,
                                                      silent_ranges[1:])]


def seek_split(audio, level=0):
    for level in range(level, len(SILENCE_LEVELS)):
        chunks = detect_silence_and_audible(audio, level)
        if len(chunks) > 1:
            return chunks
    else:
        return chunks


def get_audio_id(audio):
    return sha1(audio[:1000].get_array_of_samples()).hexdigest()[:10]


CACHE_DIR = '.cache'


def get_audio_fragments_filename(audio):
    audio_id = get_audio_id(audio)
    return '{}/{}.fragments.yaml'.format(CACHE_DIR, audio_id)


def save_fragments(audio, chunks):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    filename = get_audio_fragments_filename(audio)
    with open(filename, 'w') as fragments_file:
        yaml.dump(chunks, fragments_file)


def load_fragments(audio):
    filename = get_audio_fragments_filename(audio)
    if os.path.exists(filename):
        with open(filename, 'r') as fragments_file:
            return yaml.load(fragments_file)


def _gen_join_almost_silent(chunks, min_audible_size):
    'join each almost silent chunk as a silence beginning the following one'

    almost_silence_start = None
    for silence_start, start, end, level, label in chunks:
        if end - start < min_audible_size:
            # remember for following silence start
            # note that more than one "almost silence" can accumulate
            almost_silence_start = almost_silence_start or silence_start
        else:
            yield [almost_silence_start or silence_start,
                   start, end, level, label]
            almost_silence_start = None  # reset


@lru_cache()
@listify
def get_fragments(audio, min_audible_size=150, target_audible_size=2000):

    # try to load from disk
    loaded = load_fragments(audio)
    if loaded:
        return loaded

    chunks = [d + [NO_LABEL] for d in detect_silence_and_audible(audio)]
    for iteration in itertools.count(1):
        for pos, (silence_start, start, end, level, label
                  ) in enumerate(chunks):
            if (end - start > target_audible_size and
                    level + 1 < len(SILENCE_LEVELS)):
                subsplit = seek_split(audio[start:end], level + 1)
                if len(subsplit) > 1:
                    # shift all chunks by "start" and add label placeholder
                    # notice we erase the previous label after splitting
                    subsplit = [[s + start, i + start, e + start, l, NO_LABEL]
                                for s, i, e, l in subsplit]
                    # attach previous silence to first chunk of subsplit
                    subsplit[0][0] = silence_start
                    # last end must be the silence start of next global chunk
                    if pos + 1 < len(chunks):
                        chunks[pos + 1][0] = subsplit[-1][2]
                    chunks[pos:pos + 1] = subsplit
                    break
        else:
            # there's nothing more to split
            break

    chunks = list(_gen_join_almost_silent(chunks, min_audible_size))
    save_fragments(audio, chunks)
    return chunks
