"""Tests for bsliang_rpcode2trials.m port (response coding -> Trials tags + timings)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpcoding.core.labels import Interval, read_tier
from rpcoding.core.matio import load_trials
from rpcoding.core.paths import find_trials_mat
from rpcoding.core.rpcode.errors import response_tags
from rpcoding.core.rpcode.rpcode2trials import _delay_resp_err, rpcode_to_trials
from rpcoding.core.tasks import Task
from rpcoding.core.trialinfo.build import discover_trialdata_files, select_and_combine
from rpcoding.core.wordlists import NONWORD, WORD, load_name_list


def test_response_tags_per_task():
    # Lexical Delay palette = the Wiki's pp.9-10 error table (input codes, underscore-separated).
    codes = [c for c, _desc in response_tags(Task.LEXICAL_DELAY)]
    assert codes == [
        "ERR_TASK_YN_REP",
        "ERR_TASK_REP_YN",
        "ERR_RESP_YN_YN",
        "ERR_RESP_YN_NY",
        "ERR_RESP_REP_WRO",
        "ERR_RESP_REP_MIS",
        "NOISY",
        "LATE_RESP",
    ]
    # No-Delay reuses the same set; every tag carries a tooltip description.
    assert response_tags(Task.LEXICAL_NODELAY) == response_tags(Task.LEXICAL_DELAY)
    assert all(desc for _c, desc in response_tags(Task.LEXICAL_DELAY))


# ---- synthetic NoDelay scenarios ----

_WORDS = {"w.wav", "w2.wav"}
_NONWORDS = {"nw.wav"}


def _ti(cue, sound, **kw):
    return {"block": 1.0, "cue": cue, "sound": sound, **kw}


def _run_nodelay(trials, trialinfo, stim_code, response_code):
    return rpcode_to_trials(
        trials, trialinfo, stim_code, response_code, _WORDS, _NONWORDS, task=Task.LEXICAL_NODELAY
    )


def test_nodelay_all_correct():
    # diff == 0 (Auditory == 30000*stim_start), so EDF values are 30000*seconds.
    trials = [
        {"Auditory": 30000 * 10, "Start": 290000, "Go": None},
        {"Auditory": 30000 * 20, "Start": 590000, "Go": None},
        {"Auditory": 30000 * 30, "Start": 890000, "Go": None},
    ]
    trialinfo = [
        _ti("Yes/No", "w.wav", Resp="yes", RespCorrect=1, ReactionTime=2.0),
        _ti(":=:", "nw.wav", Resp="No Response"),
        _ti("Repeat", "w2.wav", Resp="w2"),
    ]
    stim_code = [Interval(10, 10.5, "x0"), Interval(20, 20.5, "x1"), Interval(30, 30.5, "w2")]
    response_code = [Interval(32, 32.5, "w2")]  # only the Repeat trial

    out = _run_nodelay(trials, trialinfo, stim_code, response_code)
    assert out[0]["Cue_Tag"] == "Cue/Yes_No/Word/x0/CORRECT"
    assert out[1]["Cue_Tag"] == "Cue/:=:/Nonword/x1/CORRECT"
    assert out[2]["Cue_Tag"] == "Cue/Repeat/Word/w2/CORRECT"
    assert out[0]["Response_Tag"] == "Resp/Yes_No/Word/x0/CORRECT"
    assert out[0]["StimCue"] == "x0"
    # realignment with diff==0: response start = 30000*(stim_start + RT)
    assert out[0]["ResponseStart"] == pytest.approx(30000 * 12.0)
    assert out[1]["StimEnd_mfa"] == pytest.approx(30000 * 20.5)


def test_nodelay_resp_err_when_incorrect():
    trials = [
        {"Auditory": 30000 * 10, "Start": 290000, "Go": None},
        {"Auditory": 30000 * 20, "Start": 590000, "Go": None},
        {"Auditory": 30000 * 30, "Start": 890000, "Go": None},
    ]
    trialinfo = [
        _ti("Yes/No", "w.wav", Resp="no", RespCorrect=0, ReactionTime=2.0),  # incorrect
        _ti(":=:", "nw.wav", Resp="No Response"),
        _ti("Repeat", "w2.wav", Resp="w2"),
    ]
    stim_code = [Interval(10, 10.5, "x0"), Interval(20, 20.5, "x1"), Interval(30, 30.5, "w2")]
    response_code = [Interval(32, 32.5, "w2")]
    out = _run_nodelay(trials, trialinfo, stim_code, response_code)
    assert out[0]["Cue_Tag"] == "Cue/Yes_No/Word/x0/RESP_ERR"


def test_nodelay_three_one_invariant():
    trials = [{"Auditory": 0, "Start": 0, "Go": None}]
    trialinfo = [_ti("Yes/No", "w.wav", Resp="no", RespCorrect=0, ReactionTime=0.0)]
    with pytest.raises(ValueError, match="response"):
        _run_nodelay(trials, trialinfo, [Interval(0, 1, "x")], [])  # 3*0 != 1


def test_nodelay_early_and_late():
    trials = [
        {"Auditory": 30000 * 10, "Start": 290000, "Go": None},
        {"Auditory": 30000 * 20, "Start": 100, "Go": None},  # next.Start tiny -> LATE for trial 0
        {"Auditory": 30000 * 30, "Start": 890000, "Go": None},
    ]
    trialinfo = [
        _ti("Yes/No", "w.wav", Resp="yes", RespCorrect=1, ReactionTime=2.0),
        _ti(":=:", "nw.wav", Resp="No Response"),
        _ti("Repeat", "w2.wav", Resp="w2"),
    ]
    stim_code = [Interval(10, 10.5, "x0"), Interval(20, 20.5, "x1"), Interval(30, 30.5, "w2")]
    # Repeat response starts well before its stim end -> EARLY_RESP
    response_code = [Interval(5, 5.2, "w2")]
    out = _run_nodelay(trials, trialinfo, stim_code, response_code)
    assert "LATE_RESP" in out[0]["Cue_Tag"]
    assert out[2]["Cue_Tag"].endswith("EARLY_RESP")


def test_realignment_with_nonzero_diff():
    trials = [
        {"Auditory": 500_000, "Start": 0, "Go": None},
        {"Auditory": 1_000_000, "Start": 5_000_000, "Go": None},
        {"Auditory": 1_500_000, "Start": 9_000_000, "Go": None},
    ]
    trialinfo = [
        _ti("Yes/No", "w.wav", Resp="yes", RespCorrect=1, ReactionTime=2.0),
        _ti(":=:", "nw.wav", Resp="No Response"),
        _ti("Repeat", "w2.wav", Resp="w2"),
    ]
    stim_code = [Interval(10, 10.5, "x0"), Interval(2.0, 2.5, "x1"), Interval(30, 30.5, "w2")]
    out = _run_nodelay(trials, trialinfo, stim_code, [Interval(40, 40.5, "w2")])
    diff1 = 30000 * 2.0 - 1_000_000  # nonzero realignment offset for trial 2
    assert out[1]["StimEnd_mfa"] == pytest.approx(30000 * 2.5 - diff1)


# ---- Delay error-tag parsing ----


def test_delay_error_parsing():
    assert _delay_resp_err("ERR_TASK_YN_REP", "Repeat", WORD, None) == "ERR_TASK/YN_REP"
    wro = _delay_resp_err("ERR_RESP_REP_WRO_galef", "Repeat", WORD, None)
    assert wro == "ERR_RESP/REP_WRO/galef"
    assert _delay_resp_err("ERR_RESP_REP_MIS", "Repeat", WORD, None) == "ERR_RESP/REP_MIS"
    assert _delay_resp_err("NOISE", "Repeat", WORD, None) == "NOISE"
    # empty tag -> yes/no mismatch check
    assert _delay_resp_err("", "Yes/No", WORD, "no") == "ERR_RESP/YN_YN"
    assert _delay_resp_err("", "Yes/No", NONWORD, "yes") == "ERR_RESP/YN_NY"
    assert _delay_resp_err("", "Yes/No", WORD, "yes") is None


# ---- real-data golden (NoDelay): reproduce the saved Trials.mat tags ----

_BOX = Path("F:/CloudStorage/Box/CoganLab")
_RESULTS = (
    _BOX / "ECoG_Task_Data" / "response_coding" / "response_coding_results" / "LexicalDecRepNoDelay"
)
_CTD = _BOX / "ECoG_Task_Data" / "Cogan_Task_Data"
_DDATA = _BOX / "D_Data" / "LexicalDecRepNoDelay"
_WORDLIST = Path("references/lexical/word_lst.mat")


@pytest.mark.skipif(
    not (_RESULTS.exists() and _WORDLIST.exists()),
    reason="CoganLab data / word lists not available",
)
@pytest.mark.parametrize("subject", ["D134", "D140"])
def test_real_rpcode_nodelay_golden(subject):
    rdir = _RESULTS / subject
    saved = load_trials(find_trials_mat(_DDATA / subject))  # input (.Auditory/.Start) + golden tags
    trialinfo, _ = select_and_combine(
        discover_trialdata_files(_CTD / subject / "Lexical No Delay" / "All Blocks")
    )
    stim_code = list(read_tier(rdir / "mfa" / "mfa_stim_words.txt").intervals)
    response_code = list(read_tier(rdir / "bsliang_resp_words_errors.txt").intervals)
    words = set(load_name_list(_WORDLIST, "words"))
    nonwords = set(load_name_list(_WORDLIST.with_name("nonword_lst.mat"), "nonwords"))

    out = rpcode_to_trials(
        saved, trialinfo, stim_code, response_code, words, nonwords, task=Task.LEXICAL_NODELAY
    )

    assert len(out) == len(saved)
    for t in range(len(out)):
        for tag in ("Cue_Tag", "Auditory_Tag", "Response_Tag"):
            assert out[t][tag] == saved[t][tag], f"trial {t + 1} {tag}"
        assert out[t]["StimCue"] == saved[t]["StimCue"], f"trial {t + 1} StimCue"
        for num in ("StimEnd_mfa", "ResponseStart", "ResponseEnd"):
            assert out[t][num] == pytest.approx(saved[t][num], abs=1e-2), f"trial {t + 1} {num}"


def test_save_trials_writes_struct_array_not_cell(tmp_path):
    import numpy as np
    import scipy.io as sio

    from rpcoding.core.matio import load_trials
    from rpcoding.core.rpcode.rpcode2trials import save_trials

    trials = [
        {"Start": 1.0, "Auditory": 30000.0, "Cue_Tag": "Cue/x/CORRECT"},
        {"Start": 2.0, "Auditory": 60000.0, "Cue_Tag": "Cue/y/CORRECT"},
    ]
    out = tmp_path / "Trials.mat"
    save_trials(out, trials)

    # No simplify_cells: a MATLAB struct array keeps named fields (dtype.names); a cell array of
    # structs round-trips as a plain object dtype (names is None) — that was the bug.
    raw = sio.loadmat(str(out))
    T = raw["Trials"]
    assert T.dtype.names is not None, "Trials must be a struct array, not a cell array"
    assert set(T.dtype.names) >= {"Start", "Auditory", "Cue_Tag"}
    assert T.shape == (1, 2)
    assert float(np.asarray(T["Auditory"][0, 1]).ravel()[0]) == 60000.0

    # …and it still round-trips through our normalising loader.
    back = load_trials(out)
    assert [t["Cue_Tag"] for t in back] == ["Cue/x/CORRECT", "Cue/y/CORRECT"]


def test_generate_trials_blocks_on_unreviewed_omitted(tmp_path):
    from rpcoding.core.labels import Interval, Tier, write_tier
    from rpcoding.core.rpcode.rpcode2trials import generate_trials, save_trials

    rdir = tmp_path / "res"
    (rdir / "mfa").mkdir(parents=True)
    trials_mat = tmp_path / "Trials.mat"
    save_trials(trials_mat, [{"Auditory": 0.0, "Start": 0.0}])
    write_tier(Tier("s", [Interval(0, 1, "w.wav")]), rdir / "mfa" / "mfa_stim_words.txt")
    write_tier(Tier("r", [Interval(0, 1, "Omitted")]), rdir / "bsliang_resp_words_errors.txt")
    with pytest.raises(ValueError, match="Omitted"):
        generate_trials(
            rdir,
            trials_mat,
            [{"cue": "Repeat", "sound": "w.wav"}],
            {"w.wav"},
            set(),
            task=Task.LEXICAL_NODELAY,
        )


def test_save_mat_is_compressed_like_matlab(tmp_path):
    import numpy as np
    import scipy.io as sio

    from rpcoding.core.matio import save_mat

    data = {"x": np.tile(np.arange(1000.0), 50)}  # 50k repetitive doubles -> very compressible
    comp = tmp_path / "c.mat"
    save_mat(comp, data)
    uncomp = tmp_path / "u.mat"
    sio.savemat(str(uncomp), data, do_compression=False)
    assert comp.stat().st_size < uncomp.stat().st_size / 2  # matches MATLAB's compressed save
    assert np.array_equal(sio.loadmat(str(comp))["x"].ravel(), data["x"])  # lossless round-trip
