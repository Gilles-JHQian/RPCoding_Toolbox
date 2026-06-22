"""Tests for word/nonword list loading and classification."""

from __future__ import annotations

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
