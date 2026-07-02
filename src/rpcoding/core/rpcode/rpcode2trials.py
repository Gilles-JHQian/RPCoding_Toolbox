r"""Port of bsliang_rpcode2trials.m: write response coding into each subject's Trials.

Realigns response-coding times (audio seconds) into the EDF sample space of Trials, sets per-trial
StimCue / StimEnd_mfa / ResponseStart / ResponseEnd, and builds the Cue / Auditory / (Delay / Go) /
Response tags encoding task type, Word/Nonword, stimulus, and the response-error status.

Normal path only: the per-subject index corrections and the D23 word remap
(D90/D28/D26/D92/D100/D102/D117/D23) are intentionally out of scope here (irregular-subjects work).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rpcoding.core.labels import read_tier
from rpcoding.core.matio import load_trials, save_mat, trial_cue, trial_stim
from rpcoding.core.rpcode import errors as E
from rpcoding.core.rpcode.response_fill import NOISY, count_omitted
from rpcoding.core.tasks import Task
from rpcoding.core.wordlists import NONWORD, WORD, classify

EDF_RATE = 30000.0
_EARLY_STIM_MARGIN = 0.1 * 3e4  # NoDelay EARLY_RESP margin (ticks)
_NOISY_BSL_MARGIN = 0.5 * 30000  # NOISY_BSL baseline margin (ticks)


def _task_type_tag(cue: str) -> str:
    if cue == "Yes/No":
        return "Yes_No"
    if cue == "Repeat":
        return "Repeat"
    return ":=:"  # Just Listen


def _delay_resp_err(err_tag: str, cue: str, word_tag: str, resp_yn: str | None) -> str | None:
    """Map a Delay error code (bsliang_errors Var3) + yes/no mismatch to a Resp_Err string."""
    if err_tag:
        if "ERR_TASK_YN_REP" in err_tag:
            return E.ERR_TASK_YN_REP
        if "ERR_TASK_REP_YN" in err_tag:
            return E.ERR_TASK_REP_YN
        if "ERR_RESP_REP_WRO" in err_tag:
            sub = err_tag[17:]  # MATLAB Err_Tag(18:end)
            return E.ERR_RESP_REP_WRO + (f"/{sub}" if sub else "")
        if "ERR_RESP_REP_MIS" in err_tag:
            sub = err_tag[17:]
            return E.ERR_RESP_REP_MIS + (f"/{sub}" if sub else "")
        if "NOISE" in err_tag:
            return E.NOISE
        return None
    if cue == "Yes/No":
        if word_tag == WORD and str(resp_yn).lower() == "no":
            return E.ERR_RESP_YN_YN
        if word_tag == NONWORD and str(resp_yn).lower() == "yes":
            return E.ERR_RESP_YN_NY
    return None


def _append(resp_err: str | None, code: str) -> str:
    return code if not resp_err else f"{resp_err}/{code}"


def rpcode_to_trials(
    trials: list[dict],
    trialinfo: list[dict],
    stim_code: list,
    response_code: list,
    words: set[str],
    nonwords: set[str],
    *,
    task: Task,
    error_code: list | None = None,
) -> list[dict]:
    """Return Trials augmented with StimCue/timings/tags. ``*_code`` args are lists of Intervals."""
    n = len(trials)
    if len(trialinfo) != n:
        raise ValueError(f"Trials ({n}) and trialInfo ({len(trialinfo)}) length mismatch")
    stim_starts = [iv.start for iv in stim_code]
    stim_ends = [iv.end for iv in stim_code]
    stim_cues = [iv.label for iv in stim_code]
    if len(stim_cues) != n:
        raise ValueError(f"mfa_stim_words ({len(stim_cues)}) != trials ({n})")

    is_ps = task == Task.PHONEME_SEQUENCING
    is_delay = task == Task.LEXICAL_DELAY
    has_go = is_delay or is_ps  # tasks with a delay + Go cue: Delay/Go tags + Go-based EARLY check
    resp_starts = [0.0] * n
    resp_ends = [0.0] * n
    err_code = [0] * n  # NoDelay numeric correctness code
    resp_words: list[str] | None = None
    err_tags: list[str] = [""] * n

    if is_delay:
        if len(response_code) != n:
            raise ValueError(f"response_code ({len(response_code)}) != trialInfo ({n})")
        resp_starts = [iv.start for iv in response_code]
        resp_ends = [iv.end for iv in response_code]
        resp_words = [iv.label for iv in response_code]
        if error_code is not None:
            err_tags = [iv.label for iv in error_code]
    elif is_ps:
        # Phoneme Sequencing: one spoken repeat per trial (1:1), single "Listen" cue, no Yes/No and
        # no word/nonword. Response file is bsliang_resp_words_errors.txt (like NoDelay/UP).
        if len(response_code) != n:
            raise ValueError(
                f"response_code ({len(response_code)}) != trialInfo ({n}) "
                "(Phoneme Sequencing expects one response per trial)"
            )
        resp_starts = [iv.start for iv in response_code]
        resp_ends = [iv.end for iv in response_code]
        resp_words = [iv.label for iv in response_code]
    else:
        if 3 * len(response_code) != n:
            raise ValueError(
                f"3*response_code ({3 * len(response_code)}) != trialInfo ({n}) "
                "(NoDelay expects only Repeat trials in the response file)"
            )
        rc_starts = [iv.start for iv in response_code]
        rc_ends = [iv.end for iv in response_code]
        rc_codes = [iv.label for iv in response_code]
        rep_idx = 0
        for t in range(n):
            cue = trial_cue(trialinfo[t])
            resp = trialinfo[t].get("Resp")
            if cue == ":=:":
                resp_starts[t] = resp_ends[t] = stim_ends[t]
                err_code[t] = 1 if str(resp) == "No Response" else 0
            elif cue == "Yes/No":
                rt = float(trialinfo[t]["ReactionTime"])
                resp_starts[t] = resp_ends[t] = stim_starts[t] + rt
                err_code[t] = int(round(float(trialinfo[t]["RespCorrect"])))
            elif cue == "Repeat":
                resp_starts[t] = rc_starts[rep_idx]
                resp_ends[t] = rc_ends[rep_idx]
                err_code[t] = 1 if rc_codes[rep_idx] == stim_cues[t] else 0
                rep_idx += 1

    out = [dict(tr) for tr in trials]
    for t in range(n):
        diff = EDF_RATE * stim_starts[t] - float(out[t]["Auditory"])
        out[t]["StimEnd_mfa"] = EDF_RATE * stim_ends[t] - diff
        out[t]["StimCue"] = stim_cues[t]
        out[t]["ResponseStart"] = EDF_RATE * resp_starts[t] - diff
        out[t]["ResponseEnd"] = EDF_RATE * resp_ends[t] - diff

        cue = trial_cue(trialinfo[t])
        if is_ps:
            ttag = "Listen"  # PS: single cue, every trial is a spoken repeat
            wtag = None  # no word/nonword classification for PS nonsense syllables
        else:
            ttag = _task_type_tag(cue)
            cue_word = trial_stim(trialinfo[t])
            wtag = classify(cue_word, words, nonwords)
            if wtag is None:
                raise ValueError(f"trial {t + 1}: '{cue_word}' not in the word/nonword lists")

        if is_delay:
            resp_yn = resp_words[t] if resp_words is not None else None
            resp_err = _delay_resp_err(err_tags[t], cue, wtag, resp_yn)
        elif is_ps:
            # Only NOISY / no-response is a coder error for PS; timing checks below add the rest.
            resp_err = NOISY if resp_words is not None and NOISY in resp_words[t].upper() else None
        else:
            resp_err = None if err_code[t] == 1 else E.RESP_ERR

        if t < n - 1 and float(out[t + 1]["Start"]) - out[t]["ResponseEnd"] < 0:
            resp_err = _append(resp_err, E.LATE_RESP)
        if t > 0 and float(out[t]["Start"]) - _NOISY_BSL_MARGIN - out[t - 1]["ResponseEnd"] < 0:
            resp_err = _append(resp_err, E.NOISY_BSL)
        no_earlier = float(out[t]["Go"]) if has_go else out[t]["StimEnd_mfa"] - _EARLY_STIM_MARGIN
        if out[t]["ResponseStart"] - no_earlier < 0:
            resp_err = _append(resp_err, E.EARLY_RESP)
        if not resp_err:
            resp_err = E.CORRECT

        if is_ps:  # PS drops the Word/Nonword field (its syllables aren't classified)
            suffix = f"/{ttag}/{stim_cues[t]}/{resp_err}"
        else:
            suffix = f"/{ttag}/{wtag}/{stim_cues[t]}/{resp_err}"
        out[t]["Cue_Tag"] = "Cue" + suffix
        out[t]["Auditory_Tag"] = "Auditory_stim" + suffix
        if has_go:
            out[t]["Delay_Tag"] = "Delay" + suffix
            out[t]["Go_Tag"] = "Go" + suffix
        out[t]["Response_Tag"] = "Resp" + suffix
    return out


def save_trials(path: Path | str, trials: list[dict]) -> None:
    """Write ``trials`` as ``Trials.mat`` — a 1xN MATLAB **struct array**, like the MATLAB pipeline.

    A struct array (not a *cell array of structs*) requires a numpy **structured** dtype with named
    fields: an ``object`` array of dicts round-trips through scipy as a cell array instead (and is
    bigger, since every cell re-stores the field names).
    """
    n = len(trials)
    if n == 0:
        save_mat(path, {"Trials": np.zeros((0, 0))})  # MATLAB []
        return
    # Field order = first trial's fields, then any extra fields later trials introduce (union).
    fields: list[str] = []
    seen: set[str] = set()
    for t in trials:
        for k in t:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    arr = np.empty((1, n), dtype=[(f, object) for f in fields])
    empty = np.zeros((0, 0))  # MATLAB [] for a field a given trial happens not to have
    for i, t in enumerate(trials):
        for f in fields:
            arr[0, i][f] = t.get(f, empty)
    save_mat(path, {"Trials": arr})


def _read_intervals(path: Path) -> list:
    return list(read_tier(path).intervals) if path.exists() else []


def generate_trials(
    results_dir: Path | str,
    trials_mat: Path | str,
    trialinfo: list[dict],
    words: set[str],
    nonwords: set[str],
    *,
    task: Task,
) -> list[dict]:
    """Load inputs, run rpcode_to_trials, back up Trials_org.mat, and write Trials.mat in place."""
    results_dir = Path(results_dir)
    trials_mat = Path(trials_mat)
    # Mirror MATLAB: a re-run starts from the untouched original (Trials_org.mat) so the step is
    # idempotent; on the first run the current Trials.mat *is* the original, so back it up first.
    org = trials_mat.with_name("Trials_org.mat")
    if org.exists():
        trials = load_trials(org)
    else:
        trials = load_trials(trials_mat)
        save_trials(org, trials)
    stim_code = list(read_tier(results_dir / "mfa" / "mfa_stim_words.txt").intervals)
    if task == Task.LEXICAL_DELAY:
        response_code = _read_intervals(results_dir / "bsliang_resp_words.txt")
        error_code = _read_intervals(results_dir / "bsliang_errors.txt")
    else:
        response_code = list(read_tier(results_dir / "bsliang_resp_words_errors.txt").intervals)
        error_code = None

    # Un-reviewed MFA-drop placeholders (see response_fill): the subject responded but nothing was
    # coded, so refuse to write Trials.mat until a coder reviews them.
    n_omitted = count_omitted(response_code)
    if n_omitted:
        raise ValueError(
            f"还有 {n_omitted} 个 Omitted 没有检查 — {n_omitted} response(s) are still labelled "
            "'Omitted' (MFA missed them and they weren't reviewed). Code them in the editor, then "
            "re-run write-Trials."
        )

    result = rpcode_to_trials(
        trials,
        trialinfo,
        stim_code,
        response_code,
        words,
        nonwords,
        task=task,
        error_code=error_code,
    )
    save_trials(trials_mat, result)
    return result
