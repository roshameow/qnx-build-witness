"""Implementations of the QBW subcommands."""

from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from typing import Any, NamedTuple, Sequence

from .chain import EventStore, verify_chain
from .classification import REQUIRED_CHECKLIST
from .executor import run_command, store_log
from .qnx import (
    analyze_build_context,
    detect_compiler_versions,
    env_target_arch,
    find_qnxsdp_env,
    qnx_environment,
)
from .redact import (
    normalize_paths,
    redact_command,
    redact_text,
    whitelist_environment,
)
from .utils import relative_path, sha256_file, utc_now


class CommandError(Exception):
    """A user-facing command error that should not produce an evidence event."""


class EvidenceContext(NamedTuple):
    root: Path
    store: EventStore
    logs: Path


def _context(out: str) -> EvidenceContext:
    root = Path(out).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return EvidenceContext(root=root, store=EventStore(root / "events.jsonl"), logs=logs)


def _command(args: Any) -> list[str]:
    command = [str(arg) for arg in getattr(args, "command", [])]
    # argparse REMAINDER retains the delimiter; it is syntax, not argv.
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise CommandError("a command after '--' is required")
    return command


def _cwd(args: Any) -> Path:
    value = getattr(args, "cwd", None)
    return Path(value).expanduser().resolve() if value else Path.cwd().resolve()


def _artifact_hashes(patterns: Sequence[str], cwd: Path) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for pattern in patterns:
        expanded = Path(pattern).expanduser()
        if expanded.is_absolute():
            matches = glob.glob(str(expanded), recursive=True)
        else:
            matches = glob.glob(pattern, root_dir=str(cwd), recursive=True)
        for match in sorted(matches):
            path = Path(match) if expanded.is_absolute() else cwd / match
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in found:
                continue
            found[resolved] = {
                "path": normalize_paths(relative_path(path, cwd)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "pattern": redact_text(pattern),
            }
    return sorted(found.values(), key=lambda item: item["path"])


def cmd_doctor(args: Any) -> int:
    """Report observed QNX readiness without creating evidence."""
    tools = {name: shutil.which(name) for name in ("qcc", "q++", "mkqnximage")}
    serial_tools = {
        name: shutil.which(name)
        for name in ("screen", "minicom", "picocom", "cu", "socat")
    }
    qnx_env = qnx_environment()
    env_script = find_qnxsdp_env()
    serial_available = [name for name, path in serial_tools.items() if path]
    build_ready = bool(
        tools["qcc"] and tools["q++"] and qnx_env.get("QNX_BASE") and env_script
    )
    boot_ready = build_ready and bool(tools["mkqnximage"] and serial_available)

    print("QNX readiness: " + ("BUILD+BOOT READY" if boot_ready else "NOT FULLY READY"))
    print("This is a read-only observation. No evidence was written.")
    for name, path in tools.items():
        print(f"  {name:12} {'FOUND ' + normalize_paths(path) if path else 'MISSING'}")
    for key in ("QNX_BASE", "QNX_TARGET", "QNX_HOST"):
        value = qnx_env.get(key)
        print(f"  {key:12} {value if value else 'unset'}")
    print(f"  {'qnxsdp-env.sh':12} {env_script if env_script else 'NOT FOUND'}")
    print(
        "  serial tools  "
        + (", ".join(f"{name}=FOUND" for name in serial_available) or "NONE FOUND")
    )
    if not build_ready:
        print("  Build prerequisites missing: source a real QNX 8.0 SDP environment first.")
    if not boot_ready:
        print("  Boot prerequisites missing: QSTI/QEMU image and a serial tool are required.")
    return 0


def cmd_build(args: Any, synthetic: bool = False) -> int:
    command = _command(args)
    cwd = _cwd(args)
    ctx = _context(args.out)
    timeout = getattr(args, "timeout", None)

    context = analyze_build_context(command)
    versions = detect_compiler_versions(command)
    started_payload = {
        "command": redact_command(command),
        "argv": redact_argv_local(command),
        "cwd": normalize_paths(str(cwd)),
    }
    result = run_command(command, cwd=cwd, timeout=timeout)
    stdout_log = store_log(ctx.root, ctx.logs, "build-stdout", result.stdout)
    stderr_log = store_log(ctx.root, ctx.logs, "build-stderr", result.stderr)
    artifacts = _artifact_hashes(getattr(args, "artifact", []) or [], cwd)

    reasons: list[str] = []
    if result.timed_out:
        build_status = "build_failed"
        reasons.append("Build command timed out.")
    elif context["host_only"]:
        build_status = "host_only"
        reasons.append("No qcc/q++/cmake command and no QNX environment were detected.")
    elif context["classification"] == "qnx_env_no_compiler":
        build_status = "evidence_missing"
        reasons.append("QNX environment exists but the command did not invoke qcc/q++/cmake.")
    elif result.exit_code != 0:
        build_status = "build_failed"
        reasons.append(f"Build command exited with {result.exit_code}.")
    elif context["classification"] not in {"qcc_direct", "cmake_qnx"}:
        build_status = "evidence_missing"
        reasons.append("The command could not be tied to a QNX toolchain.")
    elif not any(item["detected"] for item in versions.values()):
        build_status = "evidence_missing"
        reasons.append("The qcc/q++ version probe produced no version evidence.")
    else:
        build_status = "qcc_ok"

    if (getattr(args, "artifact", None) or []) and not artifacts:
        reasons.append("No files matched the requested --artifact patterns.")
        if build_status == "qcc_ok":
            build_status = "evidence_missing"

    target_arch = env_target_arch() or next(
        (item["arch"] for item in versions.values() if item.get("arch")), None
    )
    payload = {
        **started_payload,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "artifacts": artifacts,
        "compiler_versions": versions,
        "qnx_context": context,
        "qnx_environment": qnx_environment(),
        "environment_allowlist": whitelist_environment(),
        "sdp_path": (qnx_environment() or {}).get("QNX_BASE"),
        "target_arch": target_arch,
        "result": build_status,
        "failure_reasons": reasons,
        "synthetic": synthetic,
    }
    event = ctx.store.append("build", payload)
    print(f"BUILD {build_status} (exit={result.exit_code}, seq={event['seq']})")
    print(f"  command: {payload['command']}")
    print(f"  artifacts: {len(artifacts)}")
    for reason in reasons:
        print(f"  reason: {reason}")
    if build_status == "host_only":
        print("  HOST-ONLY: no QNX build is claimed by this event.")
    return 0


def redact_argv_local(argv: Sequence[object]) -> list[str]:
    """Local alias keeps command payload construction readable."""
    from .redact import redact_argv

    return redact_argv(argv)


def _serial_logs(
    cwd: Path, paths: Sequence[str], ctx: EvidenceContext
) -> tuple[list[str], list[dict[str, Any]]]:
    texts: list[str] = []
    records: list[dict[str, Any]] = []
    for raw in paths:
        supplied = Path(raw).expanduser()
        path = supplied if supplied.is_absolute() else cwd / supplied
        record: dict[str, Any] = {
            "requested": normalize_paths(str(supplied)),
            "present": False,
            "stored": None,
        }
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            texts.append(text)
            stored = store_log(ctx.root, ctx.logs, "qemu-serial", text)
            record.update({"present": True, "stored": stored})
        records.append(record)
    return texts, records


def cmd_qemu(args: Any, synthetic: bool = False) -> int:
    command = _command(args)
    cwd = _cwd(args)
    ctx = _context(args.out)
    marker = args.boot_marker
    result = run_command(command, cwd=cwd, timeout=args.timeout)
    stdout_log = store_log(ctx.root, ctx.logs, "qemu-stdout", result.stdout)
    stderr_log = store_log(ctx.root, ctx.logs, "qemu-stderr", result.stderr)
    serial_texts, serial_records = _serial_logs(cwd, args.serial_log or [], ctx)

    haystack = "\n".join([result.stdout, result.stderr, *serial_texts])
    marker_found = bool(marker and marker in haystack)
    reasons: list[str] = []
    if result.timed_out:
        boot_status = "boot_timeout"
        reasons.append("QEMU/QSTI command timed out.")
    elif result.exit_code != 0:
        boot_status = "boot_failed"
        reasons.append(f"QEMU/QSTI command exited with {result.exit_code}.")
    elif not marker:
        boot_status = "boot_failed"
        reasons.append("No --boot-marker was supplied; boot cannot be declared ok.")
    elif not marker_found:
        boot_status = "boot_failed"
        reasons.append("Boot marker was not present in serial/stdout/stderr output.")
    elif any(not item["present"] for item in serial_records):
        boot_status = "evidence_missing"
        reasons.append("A requested serial log file was not found.")
    else:
        boot_status = "boot_ok"

    payload = {
        "command": redact_command(command),
        "argv": redact_argv_local(command),
        "cwd": normalize_paths(str(cwd)),
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "serial_logs": serial_records,
        "boot_marker": redact_text(marker) if marker else None,
        "marker_found": marker_found,
        "result": boot_status,
        "boot_ok": boot_status == "boot_ok",
        "failure_reasons": reasons,
        "environment_allowlist": whitelist_environment(),
        "synthetic": synthetic,
    }
    event = ctx.store.append("qemu_boot", payload)
    print(f"QEMU {boot_status} (exit={result.exit_code}, seq={event['seq']})")
    print(f"  boot marker found: {marker_found}")
    for reason in reasons:
        print(f"  reason: {reason}")
    if boot_status != "boot_ok":
        print("  BOOT NOT CONFIRMED: no boot success is claimed by this event.")
    return 0


def cmd_target_test(args: Any, synthetic: bool = False) -> int:
    command = _command(args)
    cwd = _cwd(args)
    ctx = _context(args.out)
    result = run_command(command, cwd=cwd, timeout=args.timeout)
    stdout_log = store_log(ctx.root, ctx.logs, "test-stdout", result.stdout)
    stderr_log = store_log(ctx.root, ctx.logs, "test-stderr", result.stderr)
    preview = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[:20])[:4000]
    passed = result.exit_code == 0 and not result.timed_out
    reasons: list[str] = []
    if result.timed_out:
        reasons.append("Target test timed out.")
    elif result.exit_code != 0:
        reasons.append(f"Target test exited with {result.exit_code}.")

    payload = {
        "command": redact_command(command),
        "argv": redact_argv_local(command),
        "cwd": normalize_paths(str(cwd)),
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "result": "pass" if passed else "fail",
        "output_summary": redact_text(preview),
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "failure_reasons": reasons,
        "environment_allowlist": whitelist_environment(),
        "synthetic": synthetic,
    }
    event = ctx.store.append("target_test", payload)
    print(f"TARGET TEST {payload['result']} (exit={result.exit_code}, seq={event['seq']})")
    print(f"  command: {payload['command']}")
    return 0


def cmd_verify(args: Any, synthetic: bool = False) -> int:
    reviewer = redact_text(args.reviewer).strip()
    if not reviewer or reviewer == "[REDACTED]":
        raise CommandError("a non-empty --reviewer is required")

    checks: dict[str, str] = {}
    for raw in args.check or []:
        if "=" not in raw:
            raise CommandError(f"invalid --check {raw!r}; use KEY=VALUE")
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        if not key:
            raise CommandError("check keys must not be empty")
        if key in checks:
            raise CommandError(f"duplicate check key: {key}")
        checks[key] = value.strip()

    missing = [key for key in REQUIRED_CHECKLIST if key not in checks]
    false_keys = [
        key for key, value in checks.items() if value.lower() not in {"true", "1", "yes"}
    ]
    if missing:
        raise CommandError("missing required checklist item(s): " + ", ".join(missing))
    if false_keys:
        raise CommandError("checklist item(s) are not true: " + ", ".join(false_keys))

    normalized = {key: "true" for key in checks}
    ctx = _context(args.out)
    payload = {
        "reviewer": reviewer,
        "checks": normalized,
        "check_count": len(normalized),
        "all_true": True,
        "result": "pass",
        "note": redact_text(getattr(args, "note", "") or ""),
        "synthetic": synthetic,
    }
    event = ctx.store.append("verification", payload)
    print(f"VERIFICATION pass (reviewer={reviewer}, seq={event['seq']})")
    print("  checks: " + ", ".join(f"{key}=true" for key in sorted(normalized)))
    return 0


def cmd_verify_chain(args: Any) -> int:
    events, parse_errors = _read_events(args.out)
    result = verify_chain(events=events, load_errors=parse_errors)
    print("Hash chain: " + ("VALID" if result["valid"] else "INVALID"))
    print(f"  events: {result['event_count']}")
    print(f"  last hash: {result['last_hash']}")
    for error in result["errors"]:
        print(f"  error: {error}")
    return 0 if result["valid"] else 1


def _read_events(out: str) -> tuple[list[dict[str, Any]], list[str]]:
    from .chain import load_event_file

    return load_event_file(Path(out).expanduser().resolve() / "events.jsonl")


def cmd_report(args: Any) -> int:
    from .report import generate_report

    root = Path(args.out).expanduser().resolve()
    manifest, paths = generate_report(root)
    overall = manifest["overall"]
    chain = manifest["chain"]
    print(f"Overall: {overall['status'].upper()} ({overall['classification']})")
    if overall["status"] != "ready":
        for reason in overall["reasons"]:
            print(f"  missing/failed: {reason}")
    print(f"Hash chain: {'VALID' if chain['valid'] else 'INVALID'}")
    print(f"  manifest: {paths['manifest']}")
    print(f"  markdown: {paths['report_md']}")
    print(f"  html:     {paths['report_html']}")
    return 0
