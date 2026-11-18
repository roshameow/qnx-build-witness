# QNX 8.0 example target program

This directory contains a small **QNX-specific** program used by the codelab. It creates a QNX channel, sends a native pulse, receives it with `MsgReceive`, and prints `QBW_QNX_TARGET_TEST_PASS` only when the QNX message-passing round trip succeeds.

It is intentionally not a portable POSIX-only hello-world. The source references QNX headers and APIs (`sys/neutrino.h`, `ChannelCreate`, `ConnectAttach`, `MsgSendPulse`, `MsgReceive`) so the repository itself contains QNX 8.0-specific evidence in addition to tool output.

## Build with qcc

After sourcing a real QNX 8.0 SDP environment:

```sh
source /path/to/qnxsdp-env.sh
mkdir -p build

qbw build --out ../../evidence \
  --artifact 'build/qnx_pulse_test' \
  -- qcc -Vgcc_ntox86_64 -o build/qnx_pulse_test qnx_pulse_test.c
```

## Build with CMake

```sh
cmake -S . -B build-cmake \
  -DCMAKE_TOOLCHAIN_FILE=../../cmake/qnx8-x86_64.toolchain.cmake
qbw build --out ../../evidence \
  --artifact 'build-cmake/qnx_pulse_test' \
  -- cmake --build build-cmake
```

QBW recognizes `cmake` builds as QNX builds only when a QNX environment is detected. To avoid ambiguity, prefer the direct `qcc` command when generating competition evidence.

## Run on the QNX 8.0 target/QEMU session

```sh
qbw target-test --out ../../evidence \
  -- ssh <qnx-target> '/tmp/qnx_pulse_test'
```

The target test is recorded as `pass` only if the command exits 0. A boot marker or a shell prompt is never treated as a test result.

This example has not been compiled in the public repository without a licensed QNX SDP. Real compilation and target execution must be performed by the entrant on a QNX 8.0 host; synthetic self-test output is not evidence.
