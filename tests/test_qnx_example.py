import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class QnxExampleTests(unittest.TestCase):
    def test_example_uses_qnx_specific_apis(self):
        source = (REPO_ROOT / "examples" / "qnx8-qemu" / "qnx_pulse_test.c").read_text()
        for token in (
            "sys/neutrino.h",
            "ChannelCreate",
            "ConnectAttach",
            "MsgSendPulse",
            "MsgReceive",
            "QBW_QNX_TARGET_TEST_PASS",
        ):
            self.assertIn(token, source)

    def test_qnx_toolchain_file_exists(self):
        toolchain = REPO_ROOT / "cmake" / "qnx8-x86_64.toolchain.cmake"
        self.assertTrue(toolchain.is_file())
        text = toolchain.read_text()
        self.assertIn("set(CMAKE_SYSTEM_NAME QNX)", text)
        self.assertIn("qcc", text)
        self.assertIn("gcc_ntox86_64", text)


if __name__ == "__main__":
    unittest.main()
