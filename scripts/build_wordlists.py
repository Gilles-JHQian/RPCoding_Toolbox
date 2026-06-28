r"""Build the bundled Word/Nonword lists = the Lexical lists UNION the Uniqueness Point set.

Word/Nonword classification (``rpcode2trials``) matches a trial's stimulus filename against these
lists. The lab's lists only covered Lexical, so UP stimuli (``altitude.wav`` / ``ahlawjahns.wav`` …)
classified as neither. This unions the canonical Lexical lists (``references/lexical/*_lst.mat``)
with the vendored UP stimulus metadata (``uniqueness_point_stimuli.csv``) — the two sets are
disjoint — and rewrites the bundled ``word_lst.mat`` / ``nonword_lst.mat`` that are the defaults for
both tasks. Re-runnable (sorted + de-duplicated, so it's idempotent).

    python scripts/build_wordlists.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from rpcoding.core.matio import save_mat
from rpcoding.core.wordlists import load_name_list

REPO = Path(__file__).resolve().parents[1]
LEX_WORDS = REPO / "references" / "lexical" / "word_lst.mat"
LEX_NONWORDS = REPO / "references" / "lexical" / "nonword_lst.mat"
BUNDLE = REPO / "src" / "rpcoding" / "core" / "rpcode" / "wordlists"
UP_CSV = BUNDLE / "uniqueness_point_stimuli.csv"


def up_split(csv_path: Path = UP_CSV) -> tuple[list[str], list[str]]:
    """``(words, nonwords)`` token-wav filenames from the UP stimulus metadata CSV."""
    words: list[str] = []
    nonwords: list[str] = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            (words if row["wordtype"].strip().lower() == "word" else nonwords).append(
                row["token_wav"].strip()
            )
    return words, nonwords


def _as_cell(items: list[str]) -> np.ndarray:
    """A 1xN object array -> a MATLAB cell array of char (matches the lab's *_lst.mat)."""
    arr = np.empty((1, len(items)), dtype=object)
    for i, x in enumerate(items):
        arr[0, i] = x
    return arr


def main() -> int:
    lex_w = load_name_list(LEX_WORDS, "words")
    lex_n = load_name_list(LEX_NONWORDS, "nonwords")
    up_w, up_n = up_split()

    words = sorted(set(lex_w) | set(up_w))
    nonwords = sorted(set(lex_n) | set(up_n))
    conflict = set(words) & set(nonwords)
    if conflict:
        raise SystemExit(f"refusing to write: token(s) in BOTH lists: {sorted(conflict)}")

    save_mat(BUNDLE / "word_lst.mat", {"words": _as_cell(words)})
    save_mat(BUNDLE / "nonword_lst.mat", {"nonwords": _as_cell(nonwords)})
    print(f"words   : {len(lex_w)} lexical + {len(up_w)} UP -> {len(words)} merged")
    print(f"nonwords: {len(lex_n)} lexical + {len(up_n)} UP -> {len(nonwords)} merged")
    print(f"wrote {BUNDLE / 'word_lst.mat'} and {BUNDLE / 'nonword_lst.mat'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
