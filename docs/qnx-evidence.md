# QNX 8.0 Evidence Guide

This guide defines what QBW considers credible QNX 8.0 evidence. It is intentionally strict: a host-only build, a shell prompt, or a synthetic fixture is not enough.

## 1. Real toolchain evidence

A build event is classified `qcc_ok` only when:

- the executed argv directly invokes `qcc` or `q++`, or invokes `cmake` with explicit QNX context;
- the command exits successfully;
- a compiler version probe (`qcc -V` or `q++ -V`) produces a version string;
- any requested `--artifact` glob matches a real file, which is then hashed.

Before starting, source a real QNX 8.0 environment:

```sh
source /path/to/qnxsdp-env.sh
qbw doctor
```

`doctor` is read-only. It reports missing tools and environment values rather than guessing. It does not create evidence.

The report shows:

- compiler version text;
- detected target architecture, when present in compiler output or QNX environment paths;
- redacted SDP path;
- build context classification;
- command, cwd, times, exit code, and artifact hashes.

If the command contains no `qcc`, `q++`, or `cmake` and no QNX environment is detected, the event is `host_only`. A `host_only` event can be useful for debugging, but it must not be presented as a QNX build.

## 2. Boot evidence

A QEMU/QSTI event is `boot_ok` only when:

- the command exits successfully and does not time out;
- a non-empty `--boot-marker` was supplied;
- that exact marker appears in the serial log, stdout, or stderr;
- every requested serial log file was found and indexed.

A clean QEMU exit without a marker is `boot_failed`. A timed-out command is `boot_timeout`. Neither case is a successful boot. Choose a marker emitted by the actual QNX boot process, not by your host wrapper script.

Example:

```sh
qbw qemu --out evidence \
  --timeout 240 \
  --boot-marker 'QNX 8.0 console ready' \
  --serial-log serial/qnx-serial.log \
  -- ./scripts/run-qemu-and-capture-serial.sh
```

If your launch command is interactive, use a real script that starts QSTI/QEMU and captures its serial output. QBW records that script as the command; the script itself must be replayable by a reviewer.

## 3. Target-test evidence

Target tests are recorded separately from boot. A test result is `pass` only when the test command exits with code 0 and did not time out. Seeing a QNX prompt, a boot marker, or a successful SSH login is not a test pass.

```sh
qbw target-test --out evidence \
  -- ssh qnx-target '/usr/local/bin/qnx_test --suite smoke'
```

The report stores the redacted test command, exit status, timing, output summary, and raw output log index.

## 4. Manual review

Automated events can show what a machine observed. They cannot show that a person inspected the evidence. Run:

```sh
qbw verify --out evidence \
  --reviewer 'Reviewer Name' \
  --check build=true \
  --check boot=true \
  --check test=true \
  --check logs=true
```

Required keys:

| Key | Meaning |
| --- | --- |
| `build` | Reviewer checked qcc/q++ version, command, and artifact hashes. |
| `boot` | Reviewer checked the QEMU/QSTI command and boot marker. |
| `test` | Reviewer checked the target-test command and exit result. |
| `logs` | Reviewer checked the redacted raw log index for unexpected content or gaps. |

QBW rejects missing keys and any value other than `true`, `1`, or `yes`. It never writes `true` on the reviewer's behalf. The verification event includes the reviewer, normalized checklist, note, and UTC timestamp.

## 5. Integrity and report

```sh
qbw verify-chain --out evidence
qbw report --out evidence
```

The chain check detects changed or removed events. The report combines the timeline, QNX evidence details, failure classification, raw log index, and manual checklist. A package is `ready` only if build, boot marker, target test, manual review, and chain verification all pass, and no synthetic event is present.

## 6. What is not evidence

- Output from `qbw selftest`.
- Fake `qcc` scripts, echoed boot markers, or fabricated target-test exits.
- A host-only compiler or generic `cmake` build with no QNX context.
- Redacted logs without their corresponding command and exit-status events.
- A manual checklist filled in automatically by a script.
- An edited `events.jsonl` whose chain no longer verifies.

Synthetic fixtures are valid for testing QBW itself. They must never be submitted or described as QNX 8.0 runtime evidence.
