"""Failure classification tests."""

from __future__ import annotations

import unittest
from typing import Any

from qbw.classification import REQUIRED_CHECKLIST, classify_events


def event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "payload": payload}


def passing_events(synthetic: bool = False) -> list[dict[str, Any]]:
    return [
        event("build", {"result": "qcc_ok", "synthetic": synthetic}),
        event(
            "qemu_boot",
            {"result": "boot_ok", "marker_found": True, "synthetic": synthetic},
        ),
        event("target_test", {"result": "pass", "synthetic": synthetic}),
        event(
            "verification",
            {
                "result": "pass",
                "all_true": True,
                "checks": {key: "true" for key in REQUIRED_CHECKLIST},
                "synthetic": synthetic,
            },
        ),
    ]


class ClassificationTests(unittest.TestCase):
    def test_all_real_evidence_is_ready(self) -> None:
        result = classify_events(passing_events(), chain_valid=True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["classification"], "ok")
        self.assertEqual(result["missing_items"], [])

    def test_build_failure(self) -> None:
        events = passing_events()
        events[0]["payload"]["result"] = "build_failed"
        result = classify_events(events)
        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["classification"], "build_failed")
        self.assertFalse(result["criteria"]["build_qcc_ok"])

    def test_boot_timeout(self) -> None:
        events = passing_events()
        events[1]["payload"].update({"result": "boot_timeout", "marker_found": False})
        result = classify_events(events)
        self.assertEqual(result["classification"], "boot_timeout")

    def test_boot_without_marker_is_not_ok(self) -> None:
        events = passing_events()
        events[1]["payload"].update({"result": "boot_ok", "marker_found": False})
        result = classify_events(events)
        self.assertEqual(result["status"], "not_ready")
        self.assertFalse(result["criteria"]["boot_marker_found"])

    def test_test_failure(self) -> None:
        events = passing_events()
        events[2]["payload"]["result"] = "fail"
        result = classify_events(events)
        self.assertEqual(result["classification"], "test_failed")

    def test_manual_review_missing(self) -> None:
        result = classify_events(passing_events()[:-1])
        self.assertEqual(result["classification"], "manual_review_missing")
        self.assertFalse(result["criteria"]["manual_verify_pass"])

    def test_host_only(self) -> None:
        events = passing_events()
        events[0]["payload"]["result"] = "host_only"
        result = classify_events(events)
        self.assertEqual(result["classification"], "host_only")

    def test_invalid_chain_blocks_ready(self) -> None:
        result = classify_events(passing_events(), chain_valid=False)
        self.assertEqual(result["status"], "not_ready")
        self.assertFalse(result["criteria"]["chain_valid"])

    def test_synthetic_evidence_blocks_ready(self) -> None:
        result = classify_events(passing_events(synthetic=True), chain_valid=True)
        self.assertEqual(result["status"], "not_ready")
        self.assertFalse(result["criteria"]["no_synthetic_evidence"])
        self.assertIn("synthetic", " ".join(result["reasons"]))

    def test_multiple_failures_are_mixed(self) -> None:
        events = passing_events()
        events[0]["payload"]["result"] = "build_failed"
        events[1]["payload"].update({"result": "boot_timeout", "marker_found": False})
        result = classify_events(events)
        self.assertEqual(result["classification"], "mixed_failure")


if __name__ == "__main__":
    unittest.main()
