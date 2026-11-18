# Fixtures

The fixtures and demonstrations in this repository are **synthetic**. They exist to exercise QBW's software path on a host without QNX SDP installed.

They do not contain:

- a real QNX 8.0 compiler invocation;
- a real QNX target binary;
- a real QSTI/QEMU boot;
- a real target-side test result.

`python3 -m qbw selftest --out DIR` creates temporary shell scripts that imitate qcc, QEMU, and a target test. Every event it writes is marked `synthetic: true`, its report status is always `not_ready`, and its output is explicitly labeled **NOT QNX EVIDENCE**.

Never submit, quote, or present these fixtures as QNX 8.0 build, boot, or test evidence. Real evidence must be generated on a host with a genuine QNX 8.0 SDP toolchain and a real QEMU/QSTI or target session.
