import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from intelscan import agent_coordinator


class AgentCoordinatorCommandResolutionTests(unittest.TestCase):
    def test_strip_wrapping_quotes_removes_matching_quotes(self):
        self.assertEqual("C:/tools/codex.exe", agent_coordinator.strip_wrapping_quotes('"C:/tools/codex.exe"'))
        self.assertEqual("plain", agent_coordinator.strip_wrapping_quotes("plain"))

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    @mock.patch("intelscan.agent_coordinator.shutil.which", return_value=r"C:\tools\codex.exe")
    def test_resolve_agent_command_uses_direct_executable_on_windows(self, which_mock):
        cmd, use_shell = agent_coordinator.resolve_agent_command("codex --version")

        self.assertEqual([r"C:\tools\codex.exe", "--version"], cmd)
        self.assertFalse(use_shell)
        which_mock.assert_called_once_with("codex")

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    @mock.patch("intelscan.agent_coordinator.shutil.which", return_value=None)
    def test_resolve_agent_command_accepts_quoted_absolute_path(self, which_mock):
        with mock.patch("intelscan.agent_coordinator.Path.exists", return_value=True):
            cmd, use_shell = agent_coordinator.resolve_agent_command('"C:\\tools\\codex.exe" --version')

        self.assertEqual([r"C:\tools\codex.exe", "--version"], cmd)
        self.assertFalse(use_shell)
        which_mock.assert_called_once_with(r"C:\tools\codex.exe")

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    def test_resolve_agent_command_falls_back_to_shell_for_shell_features(self):
        cmd, use_shell = agent_coordinator.resolve_agent_command("echo hi | more")

        self.assertEqual("echo hi | more", cmd)
        self.assertTrue(use_shell)


if __name__ == "__main__":
    unittest.main()
