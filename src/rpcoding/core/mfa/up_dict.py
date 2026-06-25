"""Build an MFA pronunciation dictionary for the Uniqueness Point task.

UP's 80 tokens (40 words + 40 nonwords) aren't all in ``english_us_arpa`` — the nonwords are
pseudowords (e.g. ``aartahstrah``). But each token's ARPABET pronunciation already exists in its
per-token stim annotation ``<token>/<token>_phones.txt``, so we assemble the dictionary straight
from those files. The dictionary keys (token names) match the stim labels the pipeline writes into
``merged_stim_times.txt``, which become the response transcripts MFA aligns.

Run (reads the Box stim tree, writes the vendored dictionary file — never writes back to Box)::

    python -m rpcoding.core.mfa.up_dict --stim-dir <.../UniquenessPoint/mfa/stim_annotations>

The ``*_phones.txt`` files are inconsistent — some carry a leading word-level row (lowercase token),
some don't — so we keep only rows whose label looks like an ARPABET phone, not a fixed line skip.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# ARPABET phones are 1-3 uppercase letters + an optional stress digit (AA1, R, AH0, NG, SH). This
# excludes the lowercase word-level row some files carry, plus any sil/sp/spn markers.
_PHONE_RE = re.compile(r"^[A-Z]{1,3}[0-9]?$")

DEFAULT_OUT = Path(__file__).parent / "pipeline" / "dictionary" / "english_us_up.dict"


def parse_phones(phones_txt: Path | str) -> list[str]:
    """ARPABET phone sequence from a ``<token>_phones.txt`` (``start<TAB>end<TAB>label`` rows)."""
    phones: list[str] = []
    for line in Path(phones_txt).read_text(encoding="utf-8").splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 3:
            continue
        label = parts[2].strip()
        if _PHONE_RE.match(label):
            phones.append(label)
    return phones


def build_up_dictionary(stim_annotations_dir: Path | str) -> dict[str, list[str]]:
    """``{token: [phones]}`` from ``stim_annotations/<token>/<token>_phones.txt`` (UP nested).

    Also tolerates a flat ``stim_annotations/<token>_phones.txt`` layout. Tokens whose phones file
    has no usable ARPABET rows are skipped.
    """
    root = Path(stim_annotations_dir)
    files = sorted(root.glob("*/*_phones.txt")) + sorted(root.glob("*_phones.txt"))
    entries: dict[str, list[str]] = {}
    for f in files:
        token = f.name[: -len("_phones.txt")]
        if token in entries:
            continue
        phones = parse_phones(f)
        if phones:
            entries[token] = phones
    return entries


def format_dictionary(entries: dict[str, list[str]]) -> str:
    """MFA dictionary text — one ``token<TAB>PH PH PH`` line per token, tokens sorted."""
    return "".join(f"{tok}\t{' '.join(phones)}\n" for tok, phones in sorted(entries.items()))


def write_mfa_dictionary(path: Path | str, entries: dict[str, list[str]]) -> int:
    """Write ``entries`` as an MFA dictionary; returns the entry count."""
    Path(path).write_text(format_dictionary(entries), encoding="utf-8")
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rpcoding.core.mfa.up_dict")
    parser.add_argument(
        "--stim-dir", required=True, help="UniquenessPoint/mfa/stim_annotations directory"
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output .dict path")
    args = parser.parse_args(argv)
    entries = build_up_dictionary(args.stim_dir)
    n = write_mfa_dictionary(args.out, entries)
    print(f"wrote {n} entries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
