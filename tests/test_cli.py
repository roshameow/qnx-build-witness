"""CLI parsing regression tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_build_delimiter_is_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence"
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "qbw",
                    "build",
                    "--out",
                    str(out),
                    "--",
                    "/bin/sh",
                    "-c",
                    "printf host-only-smoke",
                ],
                cwd=str(PROJECT_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            event = json.loads((out / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(event["type"], "build")
            self.assertEqual(event["payload"]["argv"][0], "/bin/sh")
            self.assertNotIn("--", event["payload"]["argv"][:1])

            logs = "\n".join(
                path.read_text(encoding="utf-8") for path in (out / "logs").glob("build-stdout*.log")
            )
            self.assertIn("host-only-smoke", logs)


if __name__ == "__main__":
    unittest.main()
