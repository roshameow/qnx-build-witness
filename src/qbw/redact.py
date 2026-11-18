"""Privacy-aware redaction and environment filtering.

QBW stores only a small allowlist of environment variables. Command text and
captured logs are passed through deterministic regular expressions before they
are written to disk. Redaction is intentionally conservative: false positives
are preferable to leaking a credential.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Iterable, Mapping, Match, Optional

REDACTED = "[REDACTED]"

# PATH is deliberately absent. Never add secrets, tokens, license keys, or a
# full PATH to this list.
ENVIRONMENT_ALLOWLIST = (
    "QNX_BASE",
    "QNX_TARGET",
    "QNX_HOST",
    "QNX_VERSION",
    "QNX_PRODUCT",
    "QNX_CONFIGURATION",
    "QSTI_HOME",
    "QEMU_HOME",
    "QEMU_BINARY",
    "QEMU_ARCH",
    "QEMU_IMAGE",
    "QEMU_MACHINE",
    "QEMU_SMP",
    "QEMU_MEMORY",
)

_SECRET_NAME_MARKERS = (
    "PASSWORD",
    "PASSWD",
    "SECRET",
    "TOKEN",
    "LICENSE",
    "LICENCE",
    "APIKEY",
    "API_KEY",
    "ACCESS_KEY",
    "CREDENTIAL",
)

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_ASSIGNMENT_RE = re.compile(
    r"(?P<key>\b(?:license|licence)[ _-]?(?:key|token|number|id)?"
    r"|\b(?:token|password|passwd|pwd|secret|api[ _-]?key|access[ _-]?key"
    r"|credential|temp[ _-]?token)\b)"
    r"(?P<sep>\s*[:=]\s*|\s+)"
    r"(?P<quote>[\"']?)(?P<value>[^\s\"',;]+)(?P=quote)",
    re.IGNORECASE,
)
_CLI_FLAG_RE = re.compile(
    r"(?P<flag>--(?:token|password|passwd|secret|api-key|api_key"
    r"|license-key|license_key|access-key|temp-token))"
    r"(?P<sep>[= ])(?P<value>[^\s]+)",
    re.IGNORECASE,
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HOME_USER_RE = re.compile(r"(?<![\w])/(?:Users|home)/[^/\s]+")
_ROOT_HOME_RE = re.compile(r"(?<![\w])/root(?=/|\b)")


def _assignment_replacement(match: Match[str]) -> str:
    key = match.group("key").lower()
    token_like = any(
        marker in key
        for marker in ("token", "secret", "credential", "api", "access", "license", "licence")
    )
    replacement = "[REDACTED_TOKEN]" if token_like else REDACTED
    return (
        f"{match.group('key')}{match.group('sep')}{match.group('quote')}"
        f"{replacement}{match.group('quote')}"
    )


def normalize_paths(text: str) -> str:
    """Replace recognizable home directories with ``~``."""
    if not text:
        return text
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    text = _HOME_USER_RE.sub("~", text)
    text = _ROOT_HOME_RE.sub("~", text)
    return text


def redact_text(value: object) -> str:
    """Redact secrets and normalize home paths in arbitrary text."""
    text = value if isinstance(value, str) else str(value)
    text = _PRIVATE_KEY_RE.sub(REDACTED, text)
    text = _JWT_RE.sub("[REDACTED_TOKEN]", text)
    text = _AWS_KEY_RE.sub("[REDACTED_TOKEN]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED_TOKEN]", text)
    text = _ASSIGNMENT_RE.sub(_assignment_replacement, text)
    text = _CLI_FLAG_RE.sub(lambda m: f"{m.group('flag')}{m.group('sep')}{REDACTED}", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    return normalize_paths(text)


def redact_bytes(data: bytes) -> str:
    """Decode command output and return its redacted text form."""
    return redact_text(data.decode("utf-8", errors="replace"))


def redact_argv(argv: Iterable[object]) -> list[str]:
    """Redact each argument individually, preserving argv structure."""
    return [redact_text(arg) for arg in argv]


def redact_command(argv: Iterable[object]) -> str:
    """Return a shell-like, redacted display string for an argv list."""
    return redact_text(shlex.join(str(arg) for arg in argv))


def whitelist_environment(environ: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Return only explicitly allowed, non-secret environment values."""
    source: Mapping[str, str] = os.environ if environ is None else environ
    selected: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        allowed = key in ENVIRONMENT_ALLOWLIST or (
            (upper.startswith("QEMU_") or upper.startswith("QSTI_"))
            and not any(marker in upper for marker in _SECRET_NAME_MARKERS)
        )
        if allowed:
            selected[key] = redact_text(value)
    return dict(sorted(selected.items()))
