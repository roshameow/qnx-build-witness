"""Real subprocess execution and redacted log storage."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .redact import normalize_paths, redact_text
from .utils import relative_path, sha256_bytes, utc_now


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    cwd: str
    started_at: str
    ended_at: str
    exit_code: Optional[int]
    timed_out: bool
    stdout: str
    stderr: str


def run_command(
    argv: Sequence[object],
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
    env: Optional[Mapping[str, str]] = None,
) -> CommandResult:
    """Execute a real command. No shell is inserted by QBW."""
    command = [str(arg) for arg in argv]
    if not command:
        raise ValueError("command must not be empty")

    working_dir = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    started_at = utc_now()
    process = subprocess.Popen(
        command,
        cwd=str(working_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env) if env is not None else None,
    )
    try:
        stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        process.kill()
        stdout_bytes, stderr_bytes = process.communicate()
        timed_out = True
    ended_at = utc_now()

    return CommandResult(
        argv=command,
        cwd=normalize_paths(str(working_dir)),
        started_at=started_at,
        ended_at=ended_at,
        exit_code=process.returncode,
        timed_out=timed_out,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


def store_log(evidence_root: Path, logs_dir: Path, label: str, text: str) -> dict[str, str]:
    """Write redacted text into ``logs/`` and return an indexed description."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    redacted = redact_text(text)
    path = logs_dir / f"{label}-{uuid.uuid4().hex[:10]}.log"
    path.write_text(redacted, encoding="utf-8")
    data = redacted.encode("utf-8")
    return {
        "path": relative_path(path, evidence_root),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
    }
