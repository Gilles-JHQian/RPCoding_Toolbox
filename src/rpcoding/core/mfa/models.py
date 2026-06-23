"""Ensure MFA acoustic model + dictionaries are available; install the vendored custom dicts.

Run as a module from the setup script::

    python -m rpcoding.core.mfa.models --install-dicts
    python -m rpcoding.core.mfa.models --ensure-models
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VENDORED_DICT_DIR = Path(__file__).parent / "pipeline" / "dictionary"
ACOUSTIC_MODEL = "english_us_arpa"
BASE_DICTIONARY = "english_us_arpa"


def default_mfa_dict_dir() -> Path:
    """Where MFA keeps downloaded dictionaries (~/Documents/MFA/pretrained_models/dictionary)."""
    return Path.home() / "Documents" / "MFA" / "pretrained_models" / "dictionary"


def find_mfa_exe(python_exe: str | None = None) -> Path | None:
    """Locate the ``mfa`` console script next to the given (or current) Python."""
    base = Path(python_exe or sys.executable).parent
    for cand in (
        base / "mfa.exe",
        base / "mfa",
        base / "Scripts" / "mfa.exe",
        base / "Scripts" / "mfa",
    ):
        if cand.exists():
            return cand
    return None


def install_custom_dicts(target_dir: Path | str | None = None) -> list[Path]:
    """Copy the vendored ``*.dict`` files into the MFA dictionary dir; returns the destinations."""
    target = Path(target_dir) if target_dir else default_mfa_dict_dir()
    target.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for src in sorted(VENDORED_DICT_DIR.glob("*.dict")):
        dst = target / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def ensure_models(python_exe: str | None = None) -> None:
    """Download the acoustic model + base dictionary, then install the vendored custom dicts."""
    mfa = find_mfa_exe(python_exe)
    if mfa is None:
        raise FileNotFoundError("mfa executable not found in the environment")
    for kind, name in (("acoustic", ACOUSTIC_MODEL), ("dictionary", BASE_DICTIONARY)):
        subprocess.run([str(mfa), "model", "download", kind, name], check=False)
    install_custom_dicts()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rpcoding.core.mfa.models")
    parser.add_argument("--install-dicts", action="store_true", help="copy vendored custom dicts")
    parser.add_argument("--ensure-models", action="store_true", help="download models + dicts")
    args = parser.parse_args(argv)
    if args.install_dicts:
        copied = install_custom_dicts()
        print(f"installed {len(copied)} dict(s) to {default_mfa_dict_dir()}")
    if args.ensure_models:
        ensure_models()
    if not (args.install_dicts or args.ensure_models):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
