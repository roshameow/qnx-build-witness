"""End-to-end self test using deliberately synthetic commands."""

from __future__ import annotations

import shutil
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

from . import commands
from .chain import verify_chain
from .report import generate_report

MARKER = "SYNTHETIC_QEMU_BOOT_MARKER"


def _write_script(path: Path, body: str) -> None:
    path.write_text(body.lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _workspace(work: Path) -> tuple[Path, Path, Path, Path]:
    bin_dir = work / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    qcc = bin_dir / "qcc"
    qemu = bin_dir / "qemu-synthetic"
    test = bin_dir / "target-test-synthetic"

    _write_script(
        qcc,
        f"""#!/bin/sh
if [ "$1" = "-V" ]; then
  echo "Synthetic qcc 8.0.0 target=x86_64"
  exit 0
fi
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    shift
    out="$1"
  fi
  shift
done
[ -n "$out" ] || exit 2
printf 'synthetic artifact\\n' > "$out"
echo "synthetic compile complete"
exit 0
""",
    )
    _write_script(
        qemu,
        f"""#!/bin/sh
echo "{MARKER}"
if [ -n "$1" ]; then
  printf '%s\\n' "{MARKER}" > "$1"
fi
exit 0
""",
    )
    _write_script(
        test,
        """#!/bin/sh
echo "synthetic target test: pass"
exit 0
""",
    )
    source = work / "hello.c"
    source.write_text("/* synthetic source: not QNX evidence */\n", encoding="utf-8")
    return qcc, qemu, test, source


def run_selftest(out: str) -> int:
    """Run the whole workflow with fake tools and verify its guard rails."""
    root = Path(out).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="qbw-selftest-work-", dir=str(root)))
    print("=" * 68)
    print("SYNTHETIC SELFTEST - NOT QNX EVIDENCE")
    print("All commands below are simulated. No QNX SDP, compiler, or boot is used.")
    print("=" * 68)
    try:
        ctx = commands._context(str(root))
        start_seq, _ = ctx.store.last_state()
        qcc, qemu, test, source = _workspace(work)
        artifact = work / "hello-qnx"
        serial = work / "serial.log"

        commands.cmd_build(
            SimpleNamespace(
                out=str(root),
                command=[str(qcc), "-o", str(artifact), str(source)],
                artifact=[str(artifact)],
                cwd=str(work),
                timeout=None,
            ),
            synthetic=True,
        )
        commands.cmd_qemu(
            SimpleNamespace(
                out=str(root),
                command=[str(qemu), str(serial)],
                boot_marker=MARKER,
                serial_log=[str(serial)],
                cwd=str(work),
                timeout=30,
            ),
            synthetic=True,
        )
        commands.cmd_target_test(
            SimpleNamespace(
                out=str(root),
                command=[str(test)],
                cwd=str(work),
                timeout=30,
            ),
            synthetic=True,
        )
        commands.cmd_verify(
            SimpleNamespace(
                out=str(root),
                reviewer="selftest",
                check=["build=true", "boot=true", "test=true", "logs=true"],
                note="Synthetic end-to-end self test only.",
            ),
            synthetic=True,
        )

        ctx.store.append(
            "selftest",
            {
                "synthetic": True,
                "notice": "Synthetic selftest; not QNX 8.0 evidence.",
                "marker": MARKER,
            },
        )
        events, parse_errors = commands._read_events(str(root))
        chain = verify_chain(events=events, load_errors=parse_errors)
        manifest, paths = generate_report(root)

        new_events = [event for event in events if int(event.get("seq", 0)) > start_seq]
        checks = {
            "chain_valid": chain["valid"],
            "new_events_synthetic": bool(new_events)
            and all(
                bool(event.get("payload", {}).get("synthetic"))
                for event in new_events
                if isinstance(event.get("payload"), dict)
            ),
            "overall_not_ready": manifest["overall"]["status"] == "not_ready",
            "synthetic_flag_propagated": bool(
                manifest["overall"]["individual"]["synthetic_evidence"]
            ),
            "html_notice": "not QNX 8.0 evidence" in Path(paths["report_html"]).read_text(
                encoding="utf-8"
            ),
        }
        print("-" * 68)
        print(f"Hash chain: {'VALID' if chain['valid'] else 'INVALID'}")
        print(f"Overall: {manifest['overall']['status'].upper()} "
              f"({manifest['overall']['classification']})")
        print(f"Manifest: {paths['manifest']}")
        print(f"Report:   {paths['report_html']}")
        print("SELFTEST RESULT: " + ("PASS" if all(checks.values()) else "FAIL"))
        print("NOTICE: synthetic fixtures must never be submitted as QNX evidence.")
        return 0 if all(checks.values()) else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
