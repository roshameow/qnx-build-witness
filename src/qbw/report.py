"""Generate the human-readable and machine-readable evidence report."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .chain import load_event_file, verify_chain
from .classification import classify_events
from .redact import redact_text
from .utils import sha256_file, utc_now


def _safe(value: Any) -> Any:
    """Redact strings copied from event payloads into report artifacts."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def _latest(events: Sequence[Mapping[str, Any]], event_type: str) -> Optional[dict[str, Any]]:
    for event in reversed(events):
        if event.get("type") == event_type:
            payload = event.get("payload", {})
            return dict(payload) if isinstance(payload, Mapping) else {}
    return None


def _event_summary(event: Mapping[str, Any]) -> str:
    payload = event.get("payload", {})
    if not isinstance(payload, Mapping):
        payload = {}
    event_type = str(event.get("type", "unknown"))
    if event_type == "build":
        return f"build result={payload.get('result')} command={payload.get('command')}"
    if event_type == "qemu_boot":
        return (
            f"qemu result={payload.get('result')} "
            f"marker_found={payload.get('marker_found')}"
        )
    if event_type == "target_test":
        return f"target test result={payload.get('result')}"
    if event_type == "verification":
        return f"manual verification reviewer={payload.get('reviewer')}"
    if event_type == "selftest":
        return "synthetic selftest marker"
    return event_type


def _compiler_summary(versions: Any) -> str:
    if not isinstance(versions, Mapping):
        return "not recorded"
    parts = []
    for name in ("qcc", "q++"):
        item = versions.get(name)
        if isinstance(item, Mapping) and item.get("detected"):
            parts.append(f"{name}: {item.get('version')}")
        else:
            parts.append(f"{name}: not detected")
    return " | ".join(parts)


def qnx_details(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Extract the evidence fields reviewers are expected to inspect."""
    build = _latest(events, "build") or {}
    boot = _latest(events, "qemu_boot") or {}
    test = _latest(events, "target_test") or {}
    verification = _latest(events, "verification") or {}
    context = build.get("qnx_context", {}) if isinstance(build, Mapping) else {}
    serial_logs = boot.get("serial_logs", []) if isinstance(boot, Mapping) else []

    checks = verification.get("checks", {}) if isinstance(verification, Mapping) else {}
    if not isinstance(checks, Mapping):
        checks = {}

    return _safe(
        {
            "compiler_versions": _compiler_summary(build.get("compiler_versions")),
            "target_arch": build.get("target_arch"),
            "sdp_path": build.get("sdp_path"),
            "qnx_context": context.get("classification") if isinstance(context, Mapping) else None,
            "qemu_boot_marker": boot.get("boot_marker"),
            "qemu_marker_found": boot.get("marker_found", False),
            "qemu_result": boot.get("result"),
            "serial_logs": serial_logs,
            "target_test_command": test.get("command"),
            "target_test_result": test.get("result"),
            "reviewer": verification.get("reviewer"),
            "checklist": [{"key": key, "value": value} for key, value in sorted(checks.items())],
            "manual_verification_time": None
            if not verification
            else next(
                (
                    event.get("timestamp")
                    for event in reversed(events)
                    if event.get("type") == "verification"
                ),
                None,
            ),
        }
    )


def _index_logs(root: Path) -> list[dict[str, Any]]:
    logs_dir = root / "logs"
    records: list[dict[str, Any]] = []
    if not logs_dir.exists():
        return records
    for path in sorted(logs_dir.rglob("*")):
        if not path.is_file():
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return records


def generate_report(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Write manifest.json, report.md, and report.html into ``root``."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    events, parse_errors = load_event_file(root / "events.jsonl")
    chain = verify_chain(events=events, load_errors=parse_errors)
    overall = classify_events(events, chain["valid"])

    timeline = [
        {
            "seq": event.get("seq"),
            "type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "summary": redact_text(_event_summary(event)),
            "hash": event.get("hash"),
        }
        for event in events
    ]
    logs = _index_logs(root)
    details = qnx_details(events)

    manifest = {
        "schema": "qbw-manifest/1",
        "generated_at": utc_now(),
        "evidence_root": str(root),
        "notice": "Produced by a host-based witness. Synthetic events are not QNX evidence.",
        "overall": overall,
        "chain": chain,
        "timeline": timeline,
        "qnx_evidence": details,
        "raw_logs": logs,
        "output_files": {
            "manifest": "manifest.json",
            "report_md": "report.md",
            "report_html": "report.html",
        },
    }
    manifest["overall"] = _safe(overall)
    manifest["chain"] = _safe(chain)

    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_md_path = root / "report.md"
    report_html_path = root / "report.html"
    report_md_path.write_text(render_markdown(manifest), encoding="utf-8")
    report_html_path.write_text(render_html(manifest), encoding="utf-8")

    paths = {
        "manifest": str(manifest_path),
        "report_md": str(report_md_path),
        "report_html": str(report_html_path),
    }
    return manifest, paths


def _md(value: Any) -> str:
    text = str("" if value is None else value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_md(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_markdown(manifest: Mapping[str, Any]) -> str:
    overall = manifest["overall"]
    chain = manifest["chain"]
    details = manifest["qnx_evidence"]
    checklist = details.get("checklist", [])
    warnings = []
    if overall.get("individual", {}).get("synthetic_evidence"):
        warnings.append(
            "> **SYNTHETIC EVIDENCE NOTICE:** this package came from `qbw selftest`. "
            "It is not QNX 8.0 evidence."
        )
    lines = [
        "# QNX Build Witness Report",
        "",
        f"Generated (UTC): {manifest['generated_at']}",
        "",
        f"**Overall: {str(overall.get('status')).upper()}** — "
        f"classification `{overall.get('classification')}`",
        "",
        *warnings,
        "",
        "## Readiness criteria",
        "",
        _md_table(
            ["Criterion", "Result"],
            [[name, "PASS" if passed else "MISSING"] for name, passed in overall["criteria"].items()],
        ),
        "",
        "## Status timeline",
        "",
        _md_table(
            ["Seq", "UTC timestamp", "Type", "Summary", "Event hash"],
            [
                [item["seq"], item["timestamp"], item["type"], item["summary"], item["hash"]]
                for item in manifest["timeline"]
            ]
            or [["-", "-", "-", "no events recorded", "-"]],
        ),
        "",
        "## QNX evidence details",
        "",
        _md_table(
            ["Field", "Observed value"],
            [
                ["Compiler version(s)", details.get("compiler_versions")],
                ["Target architecture", details.get("target_arch") or "not detected"],
                ["SDP path (redacted)", details.get("sdp_path") or "not recorded"],
                ["QNX build context", details.get("qnx_context") or "not recorded"],
                ["QEMU boot marker", details.get("qemu_boot_marker") or "none"],
                ["Marker found", details.get("qemu_marker_found")],
                ["QEMU result", details.get("qemu_result") or "not recorded"],
                ["Target test command", details.get("target_test_command") or "not recorded"],
                ["Target test result", details.get("target_test_result") or "not recorded"],
                ["Reviewer", details.get("reviewer") or "not recorded"],
                ["Manual verification time", details.get("manual_verification_time") or "not recorded"],
            ],
        ),
        "",
        "### Manual checklist",
        "",
        _md_table(
            ["Key", "Value"],
            [[item["key"], item["value"]] for item in checklist]
            or [["-", "no verification event"]],
        ),
        "",
        "## Failure classification",
        "",
        f"Classification: `{overall.get('classification')}`",
        "",
    ]
    if overall.get("reasons"):
        lines.extend([f"- {reason}" for reason in overall["reasons"]])
    else:
        lines.append("- No failure reasons recorded.")
    lines.extend(
        [
            "",
            "## Raw log index",
            "",
            _md_table(
                ["Path", "Bytes", "SHA-256"],
                [[item["path"], item["bytes"], item["sha256"]] for item in manifest["raw_logs"]]
                or [["-", "-", "no logs"]],
            ),
            "",
            "## Hash chain verification",
            "",
            f"Status: **{'VALID' if chain.get('valid') else 'INVALID'}**",
            "",
            f"Events: {chain.get('event_count')}",
            "",
            f"Last hash: `{chain.get('last_hash')}`",
            "",
        ]
    )
    if chain.get("errors"):
        lines.extend([f"- {error}" for error in chain["errors"]])
    lines.append("")
    return "\n".join(lines)


def _h(value: Any) -> str:
    return html.escape(str("" if value is None else value), quote=True)


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{_h(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(manifest: Mapping[str, Any]) -> str:
    overall = manifest["overall"]
    chain = manifest["chain"]
    details = manifest["qnx_evidence"]
    status = str(overall.get("status", "not_ready")).upper()
    status_class = "ok" if status == "READY" else "bad"
    notice = ""
    if overall.get("individual", {}).get("synthetic_evidence"):
        notice = (
            '<p class="notice"><strong>SYNTHETIC EVIDENCE NOTICE:</strong> '
            "This package came from <code>qbw selftest</code> and is not QNX 8.0 evidence.</p>"
        )
    criteria_rows = [
        [name, "PASS" if passed else "MISSING"] for name, passed in overall["criteria"].items()
    ]
    timeline_rows = [
        [item["seq"], item["timestamp"], item["type"], item["summary"], item["hash"]]
        for item in manifest["timeline"]
    ] or [["-", "-", "-", "no events recorded", "-"]]
    detail_rows = [
        ["Compiler version(s)", details.get("compiler_versions")],
        ["Target architecture", details.get("target_arch") or "not detected"],
        ["SDP path (redacted)", details.get("sdp_path") or "not recorded"],
        ["QNX build context", details.get("qnx_context") or "not recorded"],
        ["QEMU boot marker", details.get("qemu_boot_marker") or "none"],
        ["Marker found", details.get("qemu_marker_found")],
        ["QEMU result", details.get("qemu_result") or "not recorded"],
        ["Target test command", details.get("target_test_command") or "not recorded"],
        ["Target test result", details.get("target_test_result") or "not recorded"],
        ["Reviewer", details.get("reviewer") or "not recorded"],
        ["Manual verification time", details.get("manual_verification_time") or "not recorded"],
    ]
    checklist_rows = [
        [item["key"], item["value"]] for item in details.get("checklist", [])
    ] or [["-", "no verification event"]]
    reason_html = "".join(f"<li>{_h(reason)}</li>" for reason in overall.get("reasons", []))
    if not reason_html:
        reason_html = "<li>No failure reasons recorded.</li>"
    log_rows = [
        [item["path"], item["bytes"], item["sha256"]] for item in manifest["raw_logs"]
    ] or [["-", "-", "no logs"]]
    chain_errors = "".join(f"<li>{_h(error)}</li>" for error in chain.get("errors", []))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QNX Build Witness Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; color: #1b1f24; line-height: 1.5; }}
h1, h2 {{ border-bottom: 1px solid #d7dce2; padding-bottom: .3rem; }}
.status {{ display: inline-block; padding: .35rem .7rem; border-radius: .3rem; font-weight: 700; }}
.ok {{ background: #ddf3e4; color: #14532d; }}
.bad {{ background: #fde2e2; color: #7f1d1d; }}
.notice {{ background: #fff4cc; border-left: 4px solid #d97706; padding: .75rem 1rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: .9rem; }}
th, td {{ border: 1px solid #d7dce2; padding: .45rem .6rem; text-align: left; vertical-align: top; word-break: break-word; }}
th {{ background: #f3f5f7; }}
code {{ background: #f3f5f7; padding: .1rem .25rem; border-radius: .2rem; }}
</style>
</head>
<body>
<h1>QNX Build Witness Report</h1>
<p>Generated (UTC): {_h(manifest['generated_at'])}</p>
<p><span class="status {status_class}">Overall: {_h(status)}</span>
Classification: <code>{_h(overall.get('classification'))}</code></p>
{notice}
<h2>Readiness criteria</h2>
{_html_table(['Criterion', 'Result'], criteria_rows)}
<h2>Status timeline</h2>
{_html_table(['Seq', 'UTC timestamp', 'Type', 'Summary', 'Event hash'], timeline_rows)}
<h2>QNX evidence details</h2>
{_html_table(['Field', 'Observed value'], detail_rows)}
<h3>Manual checklist</h3>
{_html_table(['Key', 'Value'], checklist_rows)}
<h2>Failure classification</h2>
<ul>{reason_html}</ul>
<h2>Raw log index</h2>
{_html_table(['Path', 'Bytes', 'SHA-256'], log_rows)}
<h2>Hash chain verification</h2>
<p>Status: <strong>{'VALID' if chain.get('valid') else 'INVALID'}</strong>;
events: {_h(chain.get('event_count'))}; last hash: <code>{_h(chain.get('last_hash'))}</code></p>
{('<ul>' + chain_errors + '</ul>') if chain_errors else ''}
</body>
</html>
"""
