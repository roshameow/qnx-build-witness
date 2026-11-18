"""Read-only QNX environment and toolchain detection helpers."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from .executor import run_command
from .redact import normalize_paths, redact_text

QNX_ENVIRONMENT_KEYS = (
    "QNX_BASE",
    "QNX_TARGET",
    "QNX_HOST",
    "QNX_VERSION",
    "QNX_PRODUCT",
    "QNX_CONFIGURATION",
)
COMPILER_NAMES = ("qcc", "q++")
ARCH_PATTERNS = (
    re.compile(r"\baarch64\b|\barm64\b", re.IGNORECASE),
    re.compile(r"\bx86[_-]?64\b|\bamd64\b", re.IGNORECASE),
    re.compile(r"\barmv7\w*\b", re.IGNORECASE),
    re.compile(r"\bi[3-6]86\b|\bx86\b", re.IGNORECASE),
)


def detect_target_arch(*texts: object) -> Optional[str]:
    """Return the first recognizable target architecture in supplied text."""
    for text in texts:
        if not text:
            continue
        value = str(text)
        for pattern in ARCH_PATTERNS:
            match = pattern.search(value)
            if match:
                return match.group(0).lower().replace("_", "-")
    return None


def qnx_environment(env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Return present QNX environment variables with redacted values."""
    source: Mapping[str, str] = os.environ if env is None else env
    return {key: redact_text(source[key]) for key in QNX_ENVIRONMENT_KEYS if key in source}


def analyze_build_context(
    command: Sequence[object], env: Optional[Mapping[str, str]] = None
) -> dict[str, object]:
    """Classify whether a build command has credible QNX toolchain context."""
    argv = [str(arg) for arg in command]
    basenames = [Path(arg).name for arg in argv]
    direct = sorted({name for name in basenames if name in COMPILER_NAMES})
    cmake = "cmake" in basenames
    qnx_env = qnx_environment(env)
    qnx_argument = any("qnx" in arg.lower() for arg in argv)

    if direct:
        classification = "qcc_direct"
    elif cmake and (qnx_env or qnx_argument):
        classification = "cmake_qnx"
    elif qnx_env:
        classification = "qnx_env_no_compiler"
    else:
        classification = "host_only"

    return {
        "classification": classification,
        "direct_compilers": direct,
        "cmake_invoked": cmake,
        "qnx_argument_present": qnx_argument,
        "qnx_environment": qnx_env,
        "host_only": classification == "host_only",
    }


def _compiler_candidates(command: Iterable[object]) -> list[str]:
    candidates: list[str] = []
    for arg in command:
        value = str(arg)
        name = Path(value).name
        if name in COMPILER_NAMES or name.startswith(("qcc-", "q++-")):
            if value not in candidates:
                candidates.append(value)
    for name in COMPILER_NAMES:
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    return candidates


def detect_compiler_versions(command: Sequence[object]) -> dict[str, dict[str, object]]:
    """Probe qcc/q++ with ``-V`` and record concise version evidence."""
    results: dict[str, dict[str, object]] = {
        name: {"detected": False, "version": None, "arch": None, "path": None}
        for name in COMPILER_NAMES
    }
    for candidate in _compiler_candidates(command):
        name = Path(candidate).name
        key = "q++" if name.startswith("q++") else "qcc"
        if results[key]["detected"]:
            continue
        try:
            result = run_command([candidate, "-V"], timeout=5)
        except (OSError, ValueError):
            continue
        if result.exit_code != 0:
            continue
        output = redact_text(result.stdout + "\n" + result.stderr)
        version_line = next((line.strip() for line in output.splitlines() if line.strip()), None)
        results[key] = {
            "detected": True,
            "version": version_line[:300] if version_line else None,
            "arch": detect_target_arch(output),
            "path": normalize_paths(candidate),
        }
    return results


def env_target_arch(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Infer a target architecture from QNX environment paths."""
    source: Mapping[str, str] = os.environ if env is None else env
    values = [source.get(key, "") for key in ("QNX_TARGET", "QNX_BASE")]
    return detect_target_arch(*values)


def find_qnxsdp_env(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Locate qnxsdp-env.sh without executing or modifying anything."""
    source: Mapping[str, str] = os.environ if env is None else env
    candidates: list[Path] = []
    for key in ("QNX_BASE", "QNX_HOST", "QNX_CONFIGURATION"):
        value = source.get(key)
        if not value:
            continue
        supplied = Path(value).expanduser()
        candidates.append(supplied if supplied.name == "qnxsdp-env.sh" else supplied / "qnxsdp-env.sh")
        candidates.append(supplied / "scripts" / "qnxsdp-env.sh")
    home = Path.home()
    candidates.extend(
        [
            home / "qnx800" / "qnxsdp-env.sh",
            home / "qnx800" / "scripts" / "qnxsdp-env.sh",
            Path("/qnx800/qnxsdp-env.sh"),
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return normalize_paths(str(candidate))
    return None
