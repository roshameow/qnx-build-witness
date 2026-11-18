"""End-to-end selftest behavior tests (synthetic only)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SelftestTests(unittest.TestCase):
    def test_selftest_output_is_explicitly_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "qbw-selftest"
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable, "-m", "qbw", "selftest", "--out", str(out)],
                cwd=str(PROJECT_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertIn("SYNTHETIC SELFTEST", completed.stdout)
            self.assertIn("NOT QNX EVIDENCE", completed.stdout)
            self.assertIn("SELFTEST RESULT: PASS", completed.stdout)

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["overall"]["status"], "not_ready")
            self.assertTrue(manifest["overall"]["individual"]["synthetic_evidence"])
            self.assertTrue(manifest["chain"]["valid"])
            html_text = (out / "report.html").read_text(encoding="utf-8")
            self.assertIn("not QNX 8.0 evidence", html_text)


if __name__ == "__main__":
    unittest.main()
