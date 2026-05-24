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
    def test_candidate_executable_names_adds_windows_suffixes(self):
        self.assertEqual(
            ["codex", "codex.exe", "codex.cmd", "codex.bat", "codex.ps1"],
            agent_coordinator.candidate_executable_names("codex"),
        )

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
        with (
            mock.patch("intelscan.agent_coordinator.find_windows_extension_executable", return_value=""),
            mock.patch("intelscan.agent_coordinator.Path.exists", return_value=True),
        ):
            cmd, use_shell = agent_coordinator.resolve_agent_command('"C:\\tools\\codex.exe" --version')

        self.assertEqual([r"C:\tools\codex.exe", "--version"], cmd)
        self.assertFalse(use_shell)
        which_mock.assert_called_once_with(r"C:\tools\codex.exe")

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    @mock.patch("intelscan.agent_coordinator.shutil.which", return_value=None)
    @mock.patch(
        "intelscan.agent_coordinator.find_windows_extension_executable",
        return_value=r"C:\Users\me\.vscode\extensions\vendor.agent-1.2.3\bin\windows-x86_64\myagent.exe",
    )
    def test_resolve_agent_command_finds_extension_bundled_agent(self, finder_mock, which_mock):
        cmd, use_shell = agent_coordinator.resolve_agent_command("myagent --version")

        self.assertEqual(
            [r"C:\Users\me\.vscode\extensions\vendor.agent-1.2.3\bin\windows-x86_64\myagent.exe", "--version"],
            cmd,
        )
        self.assertFalse(use_shell)
        which_mock.assert_called_once_with("myagent")
        finder_mock.assert_called_once_with("myagent")

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    @mock.patch("intelscan.agent_coordinator.shutil.which", return_value=None)
    @mock.patch("intelscan.agent_coordinator.find_windows_extension_executable", return_value="")
    @mock.patch("intelscan.agent_coordinator.find_executable_in_directories", return_value=r"D:\tools\agent.exe")
    def test_resolve_agent_command_uses_extra_search_directories(self, finder_mock, extension_mock, which_mock):
        cmd, use_shell = agent_coordinator.resolve_agent_command(
            "agent --help",
            extra_search_dirs=[r"D:\tools", r"D:\backup"],
        )

        self.assertEqual([r"D:\tools\agent.exe", "--help"], cmd)
        self.assertFalse(use_shell)
        which_mock.assert_called_once_with("agent")
        finder_mock.assert_called_once_with("agent", [r"D:\tools", r"D:\backup"])
        extension_mock.assert_not_called()

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    def test_resolve_agent_command_falls_back_to_shell_for_shell_features(self):
        cmd, use_shell = agent_coordinator.resolve_agent_command("echo hi | more")

        self.assertEqual("echo hi | more", cmd)
        self.assertTrue(use_shell)

    @mock.patch("intelscan.agent_coordinator.Path.home", return_value=Path(r"C:\Users\me"))
    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    def test_find_windows_extension_executable_prefers_newest_match(self, home_mock):
        first = Path(r"C:\Users\me\.vscode\extensions\vendor.agent-1.0.0\bin\windows-x86_64\agent.exe")
        second = Path(r"C:\Users\me\.vscode-insiders\extensions\vendor.agent-2.0.0\bin\windows-x86_64\agent.exe")

        with mock.patch("pathlib.Path.glob") as glob_mock, mock.patch("pathlib.Path.stat") as stat_mock:
            glob_results = iter([[first], [], [], [], [], [second], [], [], [], []])
            glob_mock.side_effect = lambda pattern: next(glob_results)
            stat_mock.side_effect = [
                mock.Mock(st_mtime_ns=10),
                mock.Mock(st_mtime_ns=20),
            ]

            resolved = agent_coordinator.find_windows_extension_executable("agent")

        self.assertEqual(str(second), resolved)
        self.assertEqual(10, glob_mock.call_count)
        home_mock.assert_called_once()

    @mock.patch("intelscan.agent_coordinator.os.name", "nt")
    def test_find_executable_in_directories_checks_candidates(self):
        search_root = Path(r"D:\tools")
        expected = search_root / "agent.cmd"

        def is_file_side_effect(self):
            return self == expected

        with mock.patch("pathlib.Path.is_file", autospec=True, side_effect=is_file_side_effect):
            resolved = agent_coordinator.find_executable_in_directories("agent", [str(search_root)])

        self.assertEqual(str(expected), resolved)


if __name__ == "__main__":
    unittest.main()
