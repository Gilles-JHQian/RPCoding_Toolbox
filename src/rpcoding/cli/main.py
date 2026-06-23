"""Thin headless CLI for the RPCoding pipeline.

Subcommands: ``scan`` (list subjects), ``status`` (per-step state), ``run`` (automated pipeline for
a subject), ``run-step`` (one step), ``batch`` (automated pipeline across subjects).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rpcoding import __version__
from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.runner import run_batch, run_pipeline, run_step
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import Step
from rpcoding.core.tasks import Task


def _session(args: argparse.Namespace) -> SubjectSession:
    return SubjectSession(AppConfig(droot=Path(args.droot)), Task.from_str(args.task), args.subject)


def _cmd_scan(args: argparse.Namespace) -> int:
    cfg = AppConfig(droot=Path(args.droot))
    for s in scan_subjects(paths.d_data_dir(cfg.droot, Task.from_str(args.task))):
        print(s)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    for step, state in _session(args).effective_states().items():
        print(f"{step.value:18} {state.value}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    ran = run_pipeline(_session(args), force=args.force)
    print("ran:", ", ".join(s.value for s in ran) or "(nothing runnable)")
    return 0


def _cmd_run_step(args: argparse.Namespace) -> int:
    run_step(_session(args), Step(args.step))
    print(f"{args.step}: done")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    cfg = AppConfig(droot=Path(args.droot))
    task = Task.from_str(args.task)
    subjects = (
        args.subjects.split(",")
        if args.subjects
        else scan_subjects(paths.d_data_dir(cfg.droot, task))
    )
    results = run_batch(
        cfg, task, subjects, force=args.force, on_progress=lambda s, r: print(f"{s}: {r[0]}")
    )
    n_err = sum(1 for v in results.values() if v[0] == "error")
    print(f"done: {len(results)} subject(s), {n_err} error(s)")
    return 1 if n_err else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpcoding", description="Cogan Lab Response Coding pipeline (headless)."
    )
    parser.add_argument("--version", action="version", version=f"rpcoding {__version__}")
    sub = parser.add_subparsers(dest="command")

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--droot", required=True, help="CoganLab data root ($BOX/CoganLab)")
        sp.add_argument("--task", required=True, help="task id, e.g. LexicalDecRepNoDelay")

    sp = sub.add_parser("scan", help="list subjects under a task")
    add_common(sp)
    sp.set_defaults(func=_cmd_scan)

    sp = sub.add_parser("status", help="per-step state for a subject")
    add_common(sp)
    sp.add_argument("subject")
    sp.set_defaults(func=_cmd_status)

    sp = sub.add_parser("run", help="run the automated pipeline for a subject")
    add_common(sp)
    sp.add_argument("subject")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=_cmd_run)

    sp = sub.add_parser("run-step", help="run one automated step")
    add_common(sp)
    sp.add_argument("subject")
    sp.add_argument("step")
    sp.set_defaults(func=_cmd_run_step)

    sp = sub.add_parser("batch", help="run the automated pipeline across subjects")
    add_common(sp)
    sp.add_argument("--subjects", default="", help="comma-separated; default: all scanned")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=_cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
