"""Response-coding error taxonomy (lab wiki + bsliang_rpcode2trials.m).

Tag strings use ``/`` separators; multiple derived errors are joined with ``/`` in order
LATE_RESP, NOISY_BSL, EARLY_RESP.
"""

from rpcoding.core.tasks import Task

# Lexical NoDelay: generic response error
RESP_ERR = "RESP_ERR"

# Lexical Delay: parsed from bsliang_errors.txt (input codes use '_' separators)
ERR_TASK_YN_REP = "ERR_TASK/YN_REP"
ERR_TASK_REP_YN = "ERR_TASK/REP_YN"
ERR_RESP_REP_WRO = "ERR_RESP/REP_WRO"
ERR_RESP_REP_MIS = "ERR_RESP/REP_MIS"
ERR_RESP_YN_YN = "ERR_RESP/YN_YN"
ERR_RESP_YN_NY = "ERR_RESP/YN_NY"
NOISE = "NOISE"

# Derived in both tasks
LATE_RESP = "LATE_RESP"
NOISY_BSL = "NOISY_BSL"
EARLY_RESP = "EARLY_RESP"
CORRECT = "CORRECT"


# ---- Response-coding "quick tag" palettes (per task), straight from the lab Wiki ----
# These are the *input* codes a coder writes into a response label (underscore-separated). The
# REP_WRO / REP_MIS codes take a suffix — the specific (wrong/mistaken) response — added by editing
# the label after clicking. Tooltips are the Wiki's error descriptions (Lexical, pp. 9-10).
_LEXICAL_TAGS: list[tuple[str, str]] = [
    ("ERR_TASK_YN_REP", "Task error: yes/no task but repeated the word"),
    ("ERR_TASK_REP_YN", "Task error: repetition task but said yes/no"),
    ("ERR_RESP_YN_YN", "Response error: should say yes, but said no"),
    ("ERR_RESP_YN_NY", "Response error: should say no, but said yes"),
    ("ERR_RESP_REP_WRO", "Repetition: a totally wrong word/nonword (edit to add it)"),
    ("ERR_RESP_REP_MIS", "Repetition: phonemic/syllabic mistakes (edit to add it)"),
    ("NOISY", "Noisy / response unclear"),
    # LATE_RESP matches the timing-derived tag rpcode2trials writes (MATLAB bsliang_rpcode2trials.m
    # uses 'LATE_RESP'); the Wiki's "LATR_RESP" spelling was a typo.
    ("LATE_RESP", "Late response (responding out of the trial)"),
]

# Phoneme Sequencing: every trial is a spoken repeat of a nonsense syllable — no Yes/No and no
# word/nonword, so only the "unclear / no response" and out-of-trial timing tags apply.
_PS_TAGS: list[tuple[str, str]] = [
    ("NOISY", "Noisy / no or unclear response"),
    ("LATE_RESP", "Late response (responding out of the trial)"),
]

# Wiki: Lexical Delay (pp. 9-10); Lexical No-Delay (p. 15) reuses the same set (coded only in Repeat
# trials); Uniqueness Point isn't in the Wiki and behaves like lexical.
RESPONSE_TAG_PALETTE: dict[str, list[tuple[str, str]]] = {
    Task.LEXICAL_DELAY.value: _LEXICAL_TAGS,
    Task.LEXICAL_NODELAY.value: _LEXICAL_TAGS,
    Task.UNIQUENESS_POINT.value: _LEXICAL_TAGS,
    Task.PHONEME_SEQUENCING.value: _PS_TAGS,
}


def response_tags(task: Task | str) -> list[tuple[str, str]]:
    """``(code, description)`` quick-tags for a task's response-coding palette (Wiki-defined)."""
    key = task.value if isinstance(task, Task) else str(task)
    return RESPONSE_TAG_PALETTE.get(key, _LEXICAL_TAGS)
