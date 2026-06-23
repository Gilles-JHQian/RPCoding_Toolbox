"""Run the vendored MFA pipeline as a subprocess in the current Python environment."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent / "pipeline"
PIPELINE_SCRIPT = "mfa_pipeline.py"
REQUIRED_INPUTS = ("allblocks.wav", "cue_events.txt", "trialInfo.mat")


@dataclass
class MfaResult:
    returncode: int
    command: list[str]
    log: str


def build_mfa_command(
    patient_dir: Path | str,
    task_config: str,
    patients: str,
    *,
    python_exe: str | None = None,
    pipeline_dir: Path | str | None = None,
    home_dir: Path | str | None = None,
    extra: Sequence[str] = (),
) -> tuple[list[str], Path]:
    """Build the ``python mfa_pipeline.py key=value ...`` argv and the cwd (the pipeline dir)."""
    pdir = Path(pipeline_dir) if pipeline_dir else PIPELINE_DIR
    overrides = [
        f"patient_dir={Path(patient_dir).as_posix()}",
        f"task={task_config}",
        f"patients={patients}",
    ]
    if home_dir is not None:
        overrides.append(f"home_dir={Path(home_dir).as_posix()}")
    overrides.extend(extra)
    cmd = [str(python_exe or sys.executable), str(pdir / PIPELINE_SCRIPT), *overrides]
    return cmd, pdir


def verify_inputs(patient_dir: Path | str, patients: str) -> list[Path]:
    """Return any missing required MFA inputs for the given comma-separated patients."""
    missing: list[Path] = []
    for p in str(patients).split(","):
        for req in REQUIRED_INPUTS:
            f = Path(patient_dir) / p / req
            if not f.exists():
                missing.append(f)
    return missing


def run_mfa(
    patient_dir: Path | str,
    task_config: str,
    patients: str,
    *,
    python_exe: str | None = None,
    pipeline_dir: Path | str | None = None,
    home_dir: Path | str | None = None,
    extra: Sequence[str] = (),
    check_inputs: bool = True,
    on_line: Callable[[str], None] | None = None,
) -> MfaResult:
    """Run the vendored pipeline, streaming stdout to ``on_line``. Raises if inputs are missing."""
    if check_inputs:
        missing = verify_inputs(patient_dir, patients)
        if missing:
            shown = ", ".join(str(m) for m in missing[:3])
            more = " ..." if len(missing) > 3 else ""
            raise FileNotFoundError(f"MFA inputs missing: {shown}{more}")

    cmd, cwd = build_mfa_command(
        patient_dir,
        task_config,
        patients,
        python_exe=python_exe,
        pipeline_dir=pipeline_dir,
        home_dir=home_dir,
        extra=extra,
    )
    lines: list[str] = []
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        lines.append(line)
        if on_line is not None:
            on_line(line)
    proc.wait()
    return MfaResult(returncode=proc.returncode, command=cmd, log="\n".join(lines))
