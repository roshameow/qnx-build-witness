# Architecture

QBW is a single-process host CLI with no runtime dependencies outside the Python standard library. It executes user-supplied commands directly with `subprocess.Popen`; it never synthesizes a command result.

## Module map

| Module | Responsibility |
| --- | --- |
| `src/qbw/cli.py` | argparse command tree, option validation, exit codes. |
| `src/qbw/commands.py` | Command implementations and event payload construction. |
| `src/qbw/executor.py` | Real subprocess execution with timeout handling and redacted log storage. |
| `src/qbw/chain.py` | Canonical JSON, event creation, append-only JSONL store, chain verification. |
| `src/qbw/redact.py` | Environment allowlist, secret masking, command and path normalization. |
| `src/qbw/qnx.py` | Read-only QNX environment/toolchain detection helpers. |
| `src/qbw/classification.py` | Strict readiness criteria and failure-classification logic. |
| `src/qbw/report.py` | Manifest, Markdown, and self-contained HTML generation. |
| `src/qbw/selftest.py` | Synthetic end-to-end exercise of the full pipeline. |

The root `qbw/` directory contains only a source-checkout shim so `python3 -m qbw` works without installation. The installed package is discovered from `src/qbw`.

## Data flow

```text
real command (qcc / QEMU / target test)
        |
        v
subprocess execution -> raw stdout/stderr/exit status
        |
        v
redaction + log files + artifact hashes
        |
        v
append one canonical JSON event -> events.jsonl + SHA-256 link
        |
        v
manual verification event (only if checklist is complete and true)
        |
        v
classify -> manifest.json -> report.md / report.html
```

## Event record

Every line in `events.jsonl` has this shape:

```json
{
  "seq": 3,
  "type": "target_test",
  "timestamp": "2026-11-18T09:12:33.123456Z",
  "prev_hash": "<sha256 of event 2>",
  "hash": "<sha256 of this event without hash>",
  "payload": {}
}
```

Canonicalization uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The digest covers the complete event except the `hash` field itself. `verify-chain` recomputes each digest, checks sequence numbers from 1, and checks each `prev_hash` link. Any changed log, command, or checklist value changes its event hash and all later links.

Event types used by the current pipeline are `build`, `qemu_boot`, `target_test`, `verification`, and `selftest`.

## Redaction model

Security is applied at write time:

1. The environment is filtered through an explicit allowlist. `PATH` is excluded.
2. Each argv element and free-form string passes through regex masking for license keys, tokens, passwords, API/access keys, emails, bearer/JWT/AWS-style credentials, temporary credentials, and private-key blocks.
3. Home paths are normalized to `~`.
4. Only redacted text is written to `logs/` and copied into event payloads.

The hash chain protects the redacted evidence that was actually stored. It does not prove the absent secret never existed in the original process output.

## Classification

`classification.py` reads the newest event of each kind and evaluates five independent criteria:

- `build_qcc_ok`
- `boot_marker_found`
- `target_test_pass`
- `manual_verify_pass`
- `chain_valid`

It also requires `no_synthetic_evidence`. A package is `ready` only when every criterion passes. Otherwise the report names the concrete missing checks and uses one of the documented failure classes. Synthetic events are modeled as `host_only` for classification because they cannot establish QNX use.

## Reporting

`report.py` derives all human-readable output from events and the current log directory. It does not inject a success state. The HTML is generated with inline CSS and escaped values; it contains no external stylesheets, scripts, image URLs, or anchors. This keeps the report self-contained and avoids accidentally loading third-party assets.

## Non-goals

QBW does not deploy QNX licenses, parse arbitrary serial consoles into semantic boot states, sign evidence with a private key, or guarantee that a reviewer told the truth. Its value is making claims explicit, separating machine observations from human review, and making later edits detectable.
