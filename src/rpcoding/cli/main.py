"""Thin headless CLI for the RPCoding pipeline.

Scaffolding stub: only ``--version`` and help are wired up. Subcommands
(``scan``, ``run-step``, ``batch``, ``validate``) arrive in feat/project-session.
"""

from __future__ import annotations

import argparse

from rpcoding import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpcoding",
        description="Cogan Lab Response Coding pipeline (headless).",
    )
    parser.add_argument("--version", action="version", version=f"rpcoding {__version__}")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
