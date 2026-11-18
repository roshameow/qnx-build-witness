#!/usr/bin/env bash
# Reproducible software-only demonstration. This is NOT QNX evidence.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-/tmp/qbw-demo-evidence}"

cd "$REPO_ROOT"

echo "=== QNX Build Witness software demo (SYNTHETIC, NOT QNX EVIDENCE) ==="
echo
echo "--- qbw doctor (read-only environment check) ---"
python3 -m qbw doctor || true
echo
echo "--- qbw selftest (simulated build/boot/test) ---"
python3 -m qbw selftest --out "$OUT"
echo
echo "--- qbw verify-chain ---"
python3 -m qbw verify-chain --out "$OUT"
echo
echo "--- qbw report ---"
python3 -m qbw report --out "$OUT"
echo
echo "--- report summary ---"
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
m = json.loads((out / "manifest.json").read_text())
print("manifest:", out / "manifest.json")
print("overall_status:", m["overall"]["status"])
print("classification:", m["overall"]["classification"])
print("hash_chain_valid:", m["chain"]["valid"])
print("reason:", m["overall"]["reasons"][0])
print("events:", len((out / "events.jsonl").read_text().splitlines()))
PY
echo
echo "NOTE: This demonstration uses simulated commands. It validates the witness"
echo "pipeline only. Real QNX 8.0 evidence requires qcc/QSTI/QEMU on a licensed host."
