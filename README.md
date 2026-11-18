# QNX Build Witness

QNX Build Witness (`qbw`) is a **host-based command-line tool that targets QNX 8.0**. It wraps real build, QEMU/QSTI boot, and target-side test commands, then records what happened in a redacted, hash-chained evidence package that another person can review.

It does **not** run QNX by itself. Producing competition-grade QNX 8.0 evidence requires a real QNX SDP installation, a working `qcc`/`q++` toolchain, and a real QSTI/QEMU or target session. The built-in `selftest` is deliberately synthetic and is always marked **not QNX evidence**.

## What it proves

For each workflow stage, QBW records:

- the exact argv, working directory, UTC start/end times, and exit status of a real command;
- redacted stdout/stderr files with SHA-256 digests;
- qcc/q++ version probes and any detected target architecture;
- hashes of build artifacts selected with `--artifact` globs;
- QEMU/QSTI exit or timeout state and whether a required boot marker actually appeared;
- target-test pass/fail derived only from the test command's exit code;
- a manual reviewer's true/false checklist, recorded separately from automated events;
- a SHA-256 hash chain over every evidence event.

QBW never promotes a package to `ready` unless all of these are true: build result is `qcc_ok`, the boot marker was found and boot succeeded, the target test passed, manual verification passed, and the hash chain is valid.

## Requirements

- Python 3.9+ on macOS or Linux; standard library only.
- For real evidence: QNX 8.0 SDP with `qcc`/`q++`, a sourced `qnxsdp-env.sh`, and QSTI/QEMU or an equivalent target connection.
- No QNX installation is needed to run the unit tests or `selftest`.

## Install

From this directory:

```sh
python3 -m pip install -e .
qbw --version
```

For a source checkout without installation, `python3 -m qbw ...` also works from the repository root.

## Quick start

```sh
# 0. Read-only environment check; writes no evidence.
qbw doctor

# 1. Real QNX build. The command is executed for real after the -- separator.
qbw build --out evidence \
  --artifact 'build/hello' \
  -- qcc -o build/hello src/hello.c

# 2. Real QEMU/QSTI launch. No marker means no boot success claim.
qbw qemu --out evidence \
  --timeout 180 \
  --boot-marker 'QNX 8.0 console ready' \
  --serial-log serial/qnx-serial.log \
  -- mkqnximage --run

# 3. Target-side test. "boot ok" is never treated as "test pass".
qbw target-test --out evidence \
  -- ssh qnx-target '/usr/local/bin/qnx_test --suite smoke'

# 4. Human review. Missing or non-true checklist items are rejected.
qbw verify --out evidence \
  --reviewer 'Reviewer Name' \
  --check build=true \
  --check boot=true \
  --check test=true \
  --check logs=true

# 5. Verify integrity and render the report.
qbw verify-chain --out evidence
qbw report --out evidence
```

The generated package is:

```text
evidence/
├── events.jsonl       # canonical JSONL events + SHA-256 chain
├── logs/              # redacted stdout, stderr, and serial logs
├── manifest.json      # machine-readable summary
├── report.md          # plain-text review report
└── report.html        # self-contained HTML, no external assets
```

Open `evidence/report.html` in a browser or read `evidence/report.md`.

## Commands

| Command | Purpose |
| --- | --- |
| `doctor` | Read-only check for `qcc`, `q++`, `mkqnximage`, QNX environment variables, `qnxsdp-env.sh`, and serial tools. |
| `build -- <command...>` | Execute a real build; record outputs, compiler versions, environment allowlist, and artifact hashes. |
| `qemu -- <command...>` | Execute a real QEMU/QSTI command with optional timeout, boot marker, and serial logs. |
| `target-test -- <command...>` | Execute a real target-side test; pass/fail is determined solely by exit code. |
| `verify --reviewer NAME --check KEY=VALUE ...` | Record a manual review only when all required checks are explicitly true. |
| `report` | Generate `manifest.json`, `report.md`, and self-contained `report.html`. |
| `verify-chain` | Recompute every event hash and previous-hash link. |
| `selftest --out DIR` | Run an end-to-end software test using simulated tools; output is synthetic. |

Useful options include `--out`, `--cwd`, `--artifact` (repeatable), `--timeout`, `--boot-marker`, and `--serial-log` (repeatable). Run `qbw <command> --help` for details.

## Failure classification

The report uses explicit classes rather than a generic success message:

`ok`, `build_failed`, `boot_failed`, `boot_timeout`, `test_failed`, `evidence_missing`, `manual_review_missing`, `host_only`, and `mixed_failure`.

If a build command contains no `qcc`, `q++`, or `cmake` and no QNX environment is detected, it is classified as `host_only`; QBW will not describe it as a QNX build. If a QEMU command exits cleanly but the boot marker is absent, boot is not confirmed. If no reviewer checklist exists, the package is `not_ready`.

Example report summary:

```text
Overall: NOT_READY (manual_review_missing)
  missing/failed: Manual verification is absent or has incomplete/true checklist values.
Hash chain: VALID
  manifest: evidence/manifest.json
  markdown: evidence/report.md
  html:     evidence/report.html
```

## Privacy and redaction

- Only a small environment allowlist is stored: selected non-secret `QNX_*`, `QSTI_*`, and `QEMU_*` names. `PATH` is not stored.
- Logs and commands are scanned for license keys, tokens, passwords, API keys, email addresses, bearer/JWT/AWS-style credentials, temporary credentials, and private-key blocks.
- Home directories are normalized to `~`.
- Reviewer notes and names pass through the same redaction.

Redaction is defensive but not a substitute for reviewing the generated package before sharing it.

## Tests and synthetic self-test

```sh
python3 -m unittest discover -s tests -v
python3 -m qbw selftest --out /tmp/qbw-selftest
```

The self-test prints `SYNTHETIC SELFTEST - NOT QNX EVIDENCE`, uses temporary scripts instead of a QNX toolchain, and produces a report whose overall status is `not_ready`. Its fixtures must never be presented as QNX 8.0 evidence.

## Known limitations

- QBW is a witness, not a QNX installer, license manager, CI runner, or bootloader.
- QEMU/QSTI behavior depends on the host and image; the documented QNX QSTI workflow commonly uses a supported Ubuntu host.
- Target architecture detection is best-effort, based on compiler probes and QNX environment paths.
- The hash chain detects local tampering after the fact; it is not signatures, blockchain, or cryptographic attestation.
- Shell wrappers and interactive commands are recorded as opaque argv; QBW does not parse every vendor-specific serial protocol.
- This repository contains no QNX logos or third-party trademark images.

## QNX-specific example

[`examples/qnx8-qemu/`](examples/qnx8-qemu/) contains a minimal QNX 8.0 target program using native channel and pulse APIs, plus a QNX CMake toolchain file. It gives reviewers QNX-specific source and APIs to inspect in addition to witnessed tool output. See [`docs/qnx-evidence.md`](docs/qnx-evidence.md) for the evidence rules.

## License

MIT. See [`LICENSE`](LICENSE). Copyright 2026 Wen Liu.
