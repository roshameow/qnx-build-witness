"""Canonical JSONL evidence events with a SHA-256 hash chain."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .utils import utc_now

GENESIS_HASH = "0" * 64
REQUIRED_EVENT_FIELDS = ("seq", "type", "timestamp", "prev_hash", "hash", "payload")


class ChainError(ValueError):
    """Raised when the evidence log cannot be read or extended safely."""


def canonical_json(value: Any) -> str:
    """Return a deterministic JSON representation used for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def event_hash(unsigned_event: Mapping[str, Any]) -> str:
    """Hash an event without its ``hash`` field."""
    import hashlib

    return hashlib.sha256(canonical_json(unsigned_event).encode("utf-8")).hexdigest()


def create_event(
    seq: int,
    event_type: str,
    payload: Mapping[str, Any],
    prev_hash: str = GENESIS_HASH,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Create one chained event."""
    unsigned = {
        "seq": seq,
        "type": event_type,
        "timestamp": timestamp or utc_now(),
        "prev_hash": prev_hash,
        "payload": dict(payload),
    }
    unsigned["hash"] = event_hash(unsigned)
    return unsigned


def load_event_file(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read all parseable events and report malformed lines separately."""
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    file_path = Path(path)
    if not file_path.exists():
        return events, errors
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return events, [f"cannot read {file_path}: {exc}"]
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: event is not a JSON object")
            continue
        events.append(value)
    return events, errors


class EventStore:
    """Append-only JSONL event store."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def last_state(self) -> tuple[int, str]:
        events, errors = load_event_file(self.path)
        if errors:
            raise ChainError("; ".join(errors))
        if not events:
            return 0, GENESIS_HASH
        last = events[-1]
        if not isinstance(last.get("seq"), int) or not isinstance(last.get("hash"), str):
            raise ChainError("last event has an invalid seq or hash")
        return last["seq"], last["hash"]

    def append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Append a new event and return it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seq, prev_hash = self.last_state()
        event = create_event(seq + 1, event_type, payload, prev_hash)
        line = canonical_json(event) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def events(self) -> list[dict[str, Any]]:
        events, errors = load_event_file(self.path)
        if errors:
            raise ChainError("; ".join(errors))
        return events


def verify_chain(
    events: Optional[Iterable[Mapping[str, Any]]] = None,
    path: Optional[Path] = None,
    load_errors: Iterable[str] = (),
) -> dict[str, Any]:
    """Verify sequence numbers, hashes, and previous-hash linkage.

    Supply either parsed ``events`` or a ``path``. ``load_errors`` can carry
    parse errors from a previous read so report generation does not reread the
    file.
    """
    errors: list[str] = list(load_errors)
    if events is None:
        if path is None:
            raise ValueError("verify_chain requires events or path")
        parsed, parse_errors = load_event_file(path)
        events = parsed
        errors.extend(parse_errors)

    event_list = list(events)
    previous_hash = GENESIS_HASH
    chain_hashes: list[str] = []

    for index, event in enumerate(event_list, start=1):
        missing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
        if missing:
            errors.append(f"event {index}: missing field(s): {', '.join(missing)}")
            continue
        if event["seq"] != index:
            errors.append(f"event {index}: seq is {event['seq']!r}, expected {index}")
        if event["prev_hash"] != previous_hash:
            errors.append(
                f"event {index}: prev_hash {event['prev_hash']!r} does not match "
                f"expected {previous_hash!r}"
            )

        unsigned = {key: value for key, value in event.items() if key != "hash"}
        computed = event_hash(unsigned)
        if event["hash"] != computed:
            errors.append(f"event {index}: hash mismatch (payload may have been changed)")
        chain_hashes.append(computed)
        previous_hash = computed

    return {
        "valid": not errors,
        "event_count": len(event_list),
        "errors": errors,
        "first_hash": chain_hashes[0] if chain_hashes else GENESIS_HASH,
        "last_hash": chain_hashes[-1] if chain_hashes else GENESIS_HASH,
    }
