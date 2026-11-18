"""Argument parsing and top-level CLI behavior for QBW."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Optional, Sequence

from . import __version__, commands
from .selftest import run_selftest


class _ArgumentParser(argparse.ArgumentParser):
    """Parser that keeps long help readable in a terminal."""


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _add_out(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        default="evidence",
        metavar="DIR",
        help="evidence directory (default: evidence)",
    )


def _add_cwd(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cwd",
        metavar="DIR",
        help="working directory for the executed command (default: current directory)",
    )


def _add_command(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="real command to execute; place it after --",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="qbw",
        description=(
            "QNX Build Witness: host-based evidence for QNX 8.0 build, boot, "
            "target-test, and manual-review workflows. QBW does not fabricate "
            "QNX evidence; synthetic selftest output is always labeled as such."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"qbw {__version__}")
    subparsers = parser.add_subparsers(dest="subcommand", metavar="COMMAND")

    doctor = subparsers.add_parser(
        "doctor", help="read-only QNX readiness check (writes no evidence)"
    )
    doctor.set_defaults(func=commands.cmd_doctor)

    build = subparsers.add_parser("build", help="execute a real build command and witness it")
    _add_out(build)
    _add_cwd(build)
    build.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="GLOB",
        help="glob for output files to hash; repeat for multiple patterns",
    )
    build.add_argument(
        "--timeout", type=positive_float, metavar="SECONDS", help="optional command timeout"
    )
    _add_command(build)
    build.set_defaults(func=commands.cmd_build)

    qemu = subparsers.add_parser("qemu", help="execute a real QEMU/QSTI command and witness boot")
    _add_out(qemu)
    _add_cwd(qemu)
    qemu.add_argument(
        "--timeout", type=positive_float, metavar="SECONDS", help="optional command timeout"
    )
    qemu.add_argument(
        "--boot-marker", metavar="TEXT", help="string that must appear before boot can be called ok"
    )
    qemu.add_argument(
        "--serial-log",
        action="append",
        default=[],
        metavar="PATH",
        help="serial log path to index and search; repeat for multiple logs",
    )
    _add_command(qemu)
    qemu.set_defaults(func=commands.cmd_qemu)

    target = subparsers.add_parser(
        "target-test", help="execute a target-side test command and record pass/fail"
    )
    _add_out(target)
    _add_cwd(target)
    target.add_argument(
        "--timeout", type=positive_float, metavar="SECONDS", help="optional command timeout"
    )
    _add_command(target)
    target.set_defaults(func=commands.cmd_target_test)

    verify = subparsers.add_parser(
        "verify", help="write a manual verification event after all checklist items are true"
    )
    _add_out(verify)
    verify.add_argument("--reviewer", required=True, metavar="NAME", help="reviewer name or alias")
    verify.add_argument(
        "--check",
        action="append",
        required=True,
        metavar="KEY=VALUE",
        help="required key/value: build, boot, test, logs; all must be true",
    )
    verify.add_argument("--note", metavar="TEXT", help="optional redacted reviewer note")
    verify.set_defaults(func=commands.cmd_verify)

    report = subparsers.add_parser(
        "report", help="generate manifest.json, report.md, and self-contained report.html"
    )
    _add_out(report)
    report.set_defaults(func=commands.cmd_report)

    chain = subparsers.add_parser("verify-chain", help="verify the SHA-256 event hash chain")
    _add_out(chain)
    chain.set_defaults(func=commands.cmd_verify_chain)

    selftest = subparsers.add_parser(
        "selftest", help="run a synthetic end-to-end test (NOT QNX evidence)"
    )
    _add_out(selftest)
    selftest.set_defaults(func=lambda _args: run_selftest(_args.out))

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except (commands.CommandError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
