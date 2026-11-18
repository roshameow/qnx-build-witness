# Codelab: From a qcc Build to an Audited QNX 8.0 Evidence Report

**Audience:** developers with access to a QNX 8.0 SDP and a QEMU/QSTI target image.
**Goal:** produce a redacted, hash-chained evidence package for one build-boot-test-review cycle.
**Time:** approximately 30–45 minutes, excluding QNX SDP installation.

This is a task-based tutorial draft. Commands assume a POSIX shell. Replace paths and target addresses with your own values.

## Task 1 — Install and inspect the host tool

```sh
cd qnx-build-witness
python3 -m pip install -e .
qbw --version
qbw doctor
```

Expected result: `doctor` reports what is actually present. If `qcc`, `q++`, `QNX_BASE`, or `qnxsdp-env.sh` are missing, stop and configure a real QNX SDP environment. A missing tool is not a failure of QBW; it is a truthful readiness result.

## Task 2 — Create a minimal QNX target program

Use the QNX-specific example in `examples/qnx8-qemu/qnx_pulse_test.c`. It calls QNX native message-passing APIs (`ChannelCreate`, `ConnectAttach`, `MsgSendPulse`, `MsgReceive`) and prints `QBW_QNX_TARGET_TEST_PASS` only after a successful pulse round trip.

Source your QNX environment and compile once by hand to confirm the toolchain works:

```sh
source /path/to/qnxsdp-env.sh
cd examples/qnx8-qemu
mkdir -p build
qcc -Vgcc_ntox86_64 -o build/qnx_pulse_test qnx_pulse_test.c
cd ../..
```

## Task 3 — Turn the build into an evidence event

Remove the previous artifact so the hash is produced by the witnessed build, then run:

```sh
rm -f examples/qnx8-qemu/build/qnx_pulse_test
qbw build --out evidence \
  --artifact 'examples/qnx8-qemu/build/qnx_pulse_test' \
  -- qcc -Vgcc_ntox86_64 -o examples/qnx8-qemu/build/qnx_pulse_test examples/qnx8-qemu/qnx_pulse_test.c
```

Expected summary:

```text
BUILD qcc_ok (exit=0, seq=1)
  command: qcc -Vgcc_ntox86_64 -o examples/qnx8-qemu/build/qnx_pulse_test examples/qnx8-qemu/qnx_pulse_test.c
  artifacts: 1
```

If you see `BUILD host_only`, your command or environment did not demonstrate QNX toolchain use. Fix that before continuing.

## Task 4 — Boot the QNX 8.0 image and capture a marker

Start QSTI/QEMU through a replayable script that writes serial output to `serial/qnx-serial.log`. Use a boot marker emitted by the guest, for example a login prompt or your application's startup line.

```sh
qbw qemu --out evidence \
  --timeout 240 \
  --boot-marker 'QBW_QNX_BOOT_READY' \
  --serial-log serial/qnx-serial.log \
  -- ./scripts/run-qemu-with-serial.sh
```

Inspect `evidence/report.html` after generating a report later. The boot marker must be associated with the QEMU event. If the marker does not appear, the event will be `boot_failed` even if QEMU exited with code 0.

## Task 5 — Run a target-side test

Copy the built program to the target by your normal method, then witness the test command:

```sh
qbw target-test --out evidence \
  -- ssh qnx-target '/tmp/qnx_pulse_test'
```

`pass` means only that this command exited 0. Do not mark boot success as a test result.

## Task 6 — Exercise a failure path

Run a deliberately failing test:

```sh
qbw target-test --out evidence \
  -- ssh qnx-target '/bin/false'
```

The new event will be `fail`. Later, the report's latest target-test result will remain `not_ready`. This is useful for demonstrating that QBW does not hide failures. Rerun Task 5 successfully before continuing so the final package represents a passing test.

## Task 7 — Add human verification

Review the commands, versions, marker, artifact hashes, and redacted logs. Only then fill in the checklist:

```sh
qbw verify --out evidence \
  --reviewer 'Your Name' \
  --check build=true \
  --check boot=true \
  --check test=true \
  --check logs=true \
  --note 'Reviewed qcc version, serial marker, and test exit code.'
```

Try changing one value to `false`: QBW will reject the command and write no verification event.

## Task 8 — Verify integrity and generate the report

```sh
qbw verify-chain --out evidence
qbw report --out evidence
```

Expected result for a complete real run:

```text
Overall: READY (ok)
Hash chain: VALID
```

Open `evidence/report.html`. Confirm that it shows compiler version, target architecture, redacted SDP path, QEMU marker, target test command, reviewer checklist, failure classification, and the raw log index with SHA-256 digests.

## Task 9 — Prove tampering is visible

Make a harmless-looking edit to `evidence/events.jsonl`, for example changing one character in a payload, then run:

```sh
qbw verify-chain --out evidence
qbw report --out evidence
```

The chain becomes invalid and the report status becomes `not_ready`. Restore the evidence directory from a known-good copy for any presentation.

## Cleanup and evidence boundary

Never use `qbw selftest` output in place of the real events created above. The self-test simulates qcc, QEMU, and target tests with temporary shell scripts and always produces a synthetic, `not_ready` report. It is for validating the tool only.
