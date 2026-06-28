"""Tests for word/nonword list loading and classification."""

from __future__ import annotations

import csv

import numpy as np
import scipy.io as sio

from rpcoding.core import wordlists


def test_load_and_classify(tmp_path):
    wp = tmp_path / "word_lst.mat"
    sio.savemat(str(wp), {"words": np.array(["casef.wav", "forum.wav"], dtype=object)})
    nwp = tmp_path / "nonword_lst.mat"
    sio.savemat(str(nwp), {"nonwords": np.array(["galef.wav"], dtype=object)})

    words = set(wordlists.load_name_list(wp, "words"))
    nonwords = set(wordlists.load_name_list(nwp, "nonwords"))

    assert words == {"casef.wav", "forum.wav"}
    assert nonwords == {"galef.wav"}
    assert wordlists.classify("casef.wav", words, nonwords) == "Word"
    assert wordlists.classify("galef.wav", words, nonwords) == "Nonword"
    assert wordlists.classify("missing.wav", words, nonwords) is None


def test_single_element_list(tmp_path):
    wp = tmp_path / "word_lst.mat"
    sio.savemat(str(wp), {"words": np.array(["solo.wav"], dtype=object)})
    assert wordlists.load_name_list(wp, "words") == ["solo.wav"]


def test_bundled_lists_cover_lexical_and_uniqueness_point():
    """The default bundled lists are the Lexical ∪ Uniqueness Point union (built by
    scripts/build_wordlists.py): both tasks' stimuli classify, and no token is in both lists."""
    words = set(wordlists.load_name_list(wordlists.DEFAULT_WORD_LIST, "words"))
    nonwords = set(wordlists.load_name_list(wordlists.DEFAULT_NONWORD_LIST, "nonwords"))
    assert not (words & nonwords)  # nothing is both a word and a nonword
    # Lexical stimuli
    assert wordlists.classify("bacon.wav", words, nonwords) == "Word"
    assert wordlists.classify("banel.wav", words, nonwords) == "Nonword"
    # Uniqueness Point stimuli (previously unclassified)
    assert wordlists.classify("altitude.wav", words, nonwords) == "Word"
    assert wordlists.classify("ahlawjahns.wav", words, nonwords) == "Nonword"
    # at least Lexical (84+84) ∪ UP (40+40)
    assert len(words) >= 124 and len(nonwords) >= 124


def test_vendored_up_stimuli_csv_is_40_40():
    csv_path = wordlists.DEFAULT_WORD_LIST.parent / "uniqueness_point_stimuli.csv"
    words = nonwords = 0
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["wordtype"].strip().lower() == "word":
                words += 1
            else:
                nonwords += 1
    assert (words, nonwords) == (40, 40)
