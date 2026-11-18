"""SHA-256 chain tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qbw.chain import EventStore, canonical_json, verify_chain


class HashChainTests(unittest.TestCase):
    def test_append_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.jsonl")
            first = store.append("build", {"result": "qcc_ok"})
            second = store.append("qemu_boot", {"result": "boot_ok"})

            self.assertEqual(first["seq"], 1)
            self.assertEqual(second["seq"], 2)
            self.assertEqual(second["prev_hash"], first["hash"])

            result = verify_chain(path=store.path)
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["event_count"], 2)

    def test_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.jsonl")
            store.append("build", {"result": "qcc_ok"})
            store.append("target_test", {"result": "pass"})

            lines = [json.loads(line) for line in store.path.read_text(encoding="utf-8").splitlines()]
            lines[0]["payload"]["result"] = "host_only"
            store.path.write_text(
                "\n".join(canonical_json(line) for line in lines) + "\n", encoding="utf-8"
            )

            result = verify_chain(path=store.path)
            self.assertFalse(result["valid"])
            self.assertTrue(any("hash mismatch" in error for error in result["errors"]))

    def test_broken_link_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.jsonl")
            store.append("build", {"result": "qcc_ok"})
            store.append("verification", {"result": "pass"})

            lines = [json.loads(line) for line in store.path.read_text(encoding="utf-8").splitlines()]
            lines[1]["prev_hash"] = "0" * 64
            store.path.write_text(
                "\n".join(canonical_json(line) for line in lines) + "\n", encoding="utf-8"
            )

            result = verify_chain(path=store.path)
            self.assertFalse(result["valid"])
            self.assertTrue(any("prev_hash" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
