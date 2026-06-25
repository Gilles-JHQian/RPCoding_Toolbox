"""Run the vendored MFA pipeline as a subprocess in the current Python environment."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent / "pipeline"
PIPELINE_SCRIPT = "mfa_pipeline.py"
TASK_CONF_SUBDIR = "conf/task"
REQUIRED_INPUTS = ("allblocks.wav", "cue_events.txt", "trialInfo.mat")

_STIM_DIR_RE = re.compile(r"^\s*stim_dir\s*:\s*(.+?)\s*$")


def _configured_stim_dir(task_config: str, pipeline_dir: Path | str | None = None) -> str | None:
    """The raw ``stim_dir`` value from a task's vendored YAML config (or None if absent)."""
    pdir = Path(pipeline_dir) if pipeline_dir else PIPELINE_DIR
    conf = pdir / TASK_CONF_SUBDIR / f"{task_config}.yaml"
    try:
        text = conf.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        m = _STIM_DIR_RE.match(line)
        if m:
            return m.group(1).strip().strip("'\"") or None
    return None


def resolve_stim_dir(
    droot: Path | str, task_config: str, *, pipeline_dir: Path | str | None = None
) -> Path | None:
    """Absolute stim-annotation dir for ``task_config``, re-rooted onto ``droot`` ($BOX/CoganLab).

    The vendored task YAMLs hardcode a Windows path such as
    ``Box\\CoganLab\\...\\stim_annotations`` that the pipeline joins to ``home_dir``. Off Windows
    the backslashes aren't separators, and the Box mount isn't always named literally ``Box`` (it
    is ``Box-Box`` on macOS), so that join silently points nowhere — MFA finds zero annotations,
    writes an empty ``mfa_stim_words.txt``, and dies in ``mergeAnnots`` with "list index out of
    range". We keep only the portion after the last ``CoganLab`` segment and join it under ``droot``
    (which already resolves to the real ``$BOX/CoganLab``). Returns ``None`` if the task has no
    ``stim_dir`` configured.
    """
    raw = _configured_stim_dir(task_config, pipeline_dir)
    if not raw:
        return None
    parts = [p for p in raw.replace("\\", "/").split("/") if p]
    lowered = [p.lower() for p in parts]
    if "coganlab" in lowered:
        last = max(i for i, p in enumerate(lowered) if p == "coganlab")
        parts = parts[last + 1 :]
    return Path(droot).joinpath(*parts)


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


def _subprocess_env(python_exe: str | None) -> dict[str, str]:
    """Env for the pipeline subprocess that can find the ``mfa`` console script even when the conda
    env isn't activated. The vendored pipeline calls ``mfa`` by bare name (``subprocess.run(['mfa',
    ...])``), which relies on PATH; launching the GUI without ``conda activate`` (a desktop
    shortcut, an IDE, a bare ``python`` path) leaves the env's bin off PATH, so ``mfa`` isn't found.
    Prepend the interpreter's bin dir — where ``mfa`` is installed next to ``python`` — to PATH."""
    env = os.environ.copy()
    bin_dir = str(Path(python_exe or sys.executable).parent)
    parts = env.get("PATH", "").split(os.pathsep)
    if bin_dir not in parts:
        env["PATH"] = os.pathsep.join([bin_dir, *parts]) if parts != [""] else bin_dir
    return env


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
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_subprocess_env(python_exe),
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        lines.append(line)
        if on_line is not None:
            on_line(line)
    proc.wait()
    return MfaResult(returncode=proc.returncode, command=cmd, log="\n".join(lines))
