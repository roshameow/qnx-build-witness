"""Failure classification and the strict definition of ``ready``."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

FAILURE_CLASSES = (
    "ok",
    "build_failed",
    "boot_failed",
    "boot_timeout",
    "test_failed",
    "evidence_missing",
    "manual_review_missing",
    "host_only",
    "mixed_failure",
)

EVENT_BUILD = "build"
EVENT_BOOT = "qemu_boot"
EVENT_TEST = "target_test"
EVENT_VERIFICATION = "verification"

REQUIRED_CHECKLIST = ("build", "boot", "test", "logs")


def latest_payload(events: Sequence[Mapping[str, Any]], event_type: str) -> Optional[dict[str, Any]]:
    """Return the payload of the newest event of ``event_type``."""
    for event in reversed(events):
        if event.get("type") == event_type:
            payload = event.get("payload", {})
            return dict(payload) if isinstance(payload, Mapping) else {}
    return None


def _is_true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def classify_events(
    events: Sequence[Mapping[str, Any]], chain_valid: bool = True
) -> dict[str, Any]:
    """Classify evidence without ever promoting incomplete evidence to ready."""
    build = latest_payload(events, EVENT_BUILD)
    boot = latest_payload(events, EVENT_BOOT)
    test = latest_payload(events, EVENT_TEST)
    verification = latest_payload(events, EVENT_VERIFICATION)

    synthetic = any(
        bool(event.get("payload", {}).get("synthetic")) for event in events if isinstance(event, Mapping)
    )

    if build is None:
        build_status = "evidence_missing"
    else:
        build_status = str(build.get("result", "evidence_missing"))
        if build_status not in {"qcc_ok", "build_failed", "host_only", "evidence_missing"}:
            build_status = "evidence_missing"

    if boot is None:
        boot_status = "evidence_missing"
    else:
        boot_status = str(boot.get("result", "evidence_missing"))
        if boot_status not in {"boot_ok", "boot_failed", "boot_timeout", "evidence_missing"}:
            boot_status = "evidence_missing"

    if test is None:
        test_status = "evidence_missing"
    else:
        test_status = "pass" if str(test.get("result")) == "pass" else "test_failed"

    checks_value = verification.get("checks", {}) if verification else {}
    checks = checks_value if isinstance(checks_value, Mapping) else {}
    manual_ok = bool(
        verification
        and verification.get("result") == "pass"
        and verification.get("all_true") is True
        and all(_is_true(checks.get(key)) for key in REQUIRED_CHECKLIST)
    )
    manual_status = "pass" if manual_ok else "manual_review_missing"

    marker_found = bool(boot and boot.get("marker_found") is True)
    boot_ok = boot_status == "boot_ok" and marker_found

    criteria = {
        "build_qcc_ok": build_status == "qcc_ok" and not bool(build and build.get("synthetic")),
        "boot_marker_found": boot_ok and not bool(boot and boot.get("synthetic")),
        "target_test_pass": test_status == "pass" and not bool(test and test.get("synthetic")),
        "manual_verify_pass": manual_ok and not bool(verification and verification.get("synthetic")),
        "chain_valid": chain_valid,
        "no_synthetic_evidence": not synthetic,
    }
    ready = all(criteria.values())

    reasons: list[str] = []
    failure_classes: list[str] = []

    if build is None:
        reasons.append("No build event was recorded.")
        failure_classes.append("evidence_missing")
    elif build_status == "qcc_ok":
        pass
    elif build_status == "build_failed":
        reasons.append("The recorded build command failed.")
        failure_classes.append("build_failed")
    elif build_status == "host_only":
        reasons.append("The build was classified as host_only; no QNX toolchain was evidenced.")
        failure_classes.append("host_only")
    else:
        reasons.append("The build event does not establish a qcc toolchain result.")
        failure_classes.append("evidence_missing")

    if boot is None:
        reasons.append("No QEMU/QSTI boot event was recorded.")
        failure_classes.append("evidence_missing")
    elif boot_status == "boot_timeout":
        reasons.append("The QEMU/QSTI command timed out.")
        failure_classes.append("boot_timeout")
    elif boot_status == "boot_failed":
        reasons.append("The QEMU/QSTI command failed or the boot marker was absent.")
        failure_classes.append("boot_failed")
    elif boot_status == "evidence_missing":
        reasons.append("The boot event lacks sufficient evidence.")
        failure_classes.append("evidence_missing")

    if test is None:
        reasons.append("No target-test event was recorded.")
        failure_classes.append("evidence_missing")
    elif test_status != "pass":
        reasons.append("The target test did not exit successfully.")
        failure_classes.append("test_failed")

    if not manual_ok:
        reasons.append("Manual verification is absent or has incomplete/true checklist values.")
        failure_classes.append("manual_review_missing")

    if not chain_valid:
        reasons.append("The SHA-256 hash chain is invalid.")
        failure_classes.append("evidence_missing")

    if synthetic:
        reasons.append("The package contains synthetic selftest evidence; it is not QNX evidence.")
        failure_classes.append("host_only")

    unique_classes = list(dict.fromkeys(failure_classes))
    if ready:
        classification = "ok"
    elif unique_classes == ["evidence_missing", "manual_review_missing"]:
        # Nothing automated was recorded; manual review is not the primary fault.
        classification = "evidence_missing"
    elif len(unique_classes) == 1:
        classification = unique_classes[0]
    elif unique_classes:
        classification = "mixed_failure"
    else:
        classification = "evidence_missing"
        reasons.append("No classification reason was produced.")

    return {
        "status": "ready" if ready else "not_ready",
        "classification": classification,
        "criteria": criteria,
        "missing_items": [name for name, passed in criteria.items() if not passed],
        "reasons": reasons,
        "individual": {
            "build": build_status,
            "boot": boot_status,
            "target_test": test_status,
            "manual_review": manual_status,
            "chain": "valid" if chain_valid else "invalid",
            "synthetic_evidence": synthetic,
        },
    }
