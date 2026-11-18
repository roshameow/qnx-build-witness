"""Redaction and environment allowlist tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from qbw.redact import redact_argv, redact_command, redact_text, whitelist_environment


class RedactionTests(unittest.TestCase):
    def test_secrets_and_paths_are_masked(self) -> None:
        home = Path.home()
        private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEsecretmaterial\n"
            "-----END PRIVATE KEY-----"
        )
        text = "\n".join(
            [
                f"license_key=QNX-1234-ABCD-5678 at {home}/qnx800",
                "token: abcdef0123456789",
                "--password=hunter2",
                "contact dev@example.com",
                private_key,
            ]
        )
        redacted = redact_text(text)

        self.assertNotIn("QNX-1234-ABCD-5678", redacted)
        self.assertNotIn("abcdef0123456789", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("dev@example.com", redacted)
        self.assertNotIn(str(home), redacted)
        self.assertNotIn("MIIEsecretmaterial", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)
        self.assertIn("~/qnx800", redacted)

    def test_environment_allowlist_excludes_path_and_secrets(self) -> None:
        env = {
            "PATH": "/usr/bin:/bin",
            "QNX_BASE": str(Path.home() / "qnx800"),
            "QNX_TARGET": "/qnx800/target/qnx7/x86_64/usr",
            "QEMU_IMAGE": "~/images/qnx.img",
            "QEMU_PASSWORD": "do-not-store-me",
            "AWS_SECRET_ACCESS_KEY": "also-secret",
        }
        allowed = whitelist_environment(env)

        self.assertNotIn("PATH", allowed)
        self.assertNotIn("QEMU_PASSWORD", allowed)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", allowed)
        self.assertEqual(allowed["QNX_BASE"], "~/qnx800")
        self.assertIn("QNX_TARGET", allowed)
        self.assertIn("QEMU_IMAGE", allowed)

    def test_argv_and_command_redaction(self) -> None:
        argv = ["ssh", "user@example.com", "--token=abcd123456"]
        self.assertNotIn("user@example.com", " ".join(redact_argv(argv)))
        command = redact_command(argv)
        self.assertNotIn("abcd123456", command)
        self.assertIn("[REDACTED]", command)


if __name__ == "__main__":
    unittest.main()
