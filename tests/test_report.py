"""Report generation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qbw.chain import EventStore
from qbw.classification import REQUIRED_CHECKLIST
from qbw.report import generate_report


class ReportGenerationTests(unittest.TestCase):
    def _seed(self, root: Path) -> None:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "build-stdout.log").write_text(
            "synthetic compile complete\n", encoding="utf-8"
        )
        store = EventStore(root / "events.jsonl")
        store.append(
            "build",
            {
                "command": "/opt/qnx800/host/bin/qcc -o hello hello.c",
                "result": "qcc_ok",
                "target_arch": "x86-64",
                "sdp_path": "~/qnx800",
                "compiler_versions": {
                    "qcc": {
                        "detected": True,
                        "version": "QNX C/C++ Compiler (Version 8.0.0)",
                        "arch": "x86-64",
                        "path": "~/qnx800/host/bin/qcc",
                    },
                    "q++": {"detected": False, "version": None, "arch": None, "path": None},
                },
                "qnx_context": {"classification": "qcc_direct"},
                "synthetic": False,
            },
        )
        store.append(
            "qemu_boot",
            {
                "result": "boot_ok",
                "boot_ok": True,
                "marker_found": True,
                "boot_marker": "QNX_BOOT_READY",
                "serial_logs": [{"requested": "~/serial.log", "present": True}],
                "synthetic": False,
            },
        )
        store.append(
            "target_test",
            {
                "result": "pass",
                "command": "ssh target /usr/bin/qnx_test",
                "synthetic": False,
            },
        )
        store.append(
            "verification",
            {
                "result": "pass",
                "all_true": True,
                "reviewer": "Reviewer A",
                "checks": {key: "true" for key in REQUIRED_CHECKLIST},
                "synthetic": False,
            },
        )

    def test_report_files_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            manifest, paths = generate_report(root)

            self.assertEqual(manifest["overall"]["status"], "ready")
            self.assertEqual(manifest["overall"]["classification"], "ok")
            self.assertTrue(manifest["chain"]["valid"])
            self.assertIn("x86-64", manifest["qnx_evidence"]["target_arch"])
            self.assertEqual(manifest["qnx_evidence"]["reviewer"], "Reviewer A")
            self.assertTrue(any(item["path"].endswith(".log") for item in manifest["raw_logs"]))

            for path in paths.values():
                self.assertTrue(Path(path).is_file(), path)

            markdown = Path(paths["report_md"]).read_text(encoding="utf-8")
            self.assertIn("# QNX Build Witness Report", markdown)
            self.assertIn("QNX evidence details", markdown)
            self.assertIn("QNX_BOOT_READY", markdown)
            self.assertIn("Reviewer A", markdown)

            html_text = Path(paths["report_html"]).read_text(encoding="utf-8")
            self.assertIn("<style>", html_text)
            self.assertNotIn("<link", html_text)
            self.assertNotIn("<script", html_text)
            self.assertNotIn("href=", html_text)
            self.assertIn("READY", html_text)

    def test_report_reflects_invalid_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            events_file = root / "events.jsonl"
            text = events_file.read_text(encoding="utf-8")
            text = text.replace('"result":"qcc_ok"', '"result":"host_only"', 1)
            events_file.write_text(text, encoding="utf-8")

            manifest, _ = generate_report(root)
            self.assertFalse(manifest["chain"]["valid"])
            self.assertEqual(manifest["overall"]["status"], "not_ready")


if __name__ == "__main__":
    unittest.main()
