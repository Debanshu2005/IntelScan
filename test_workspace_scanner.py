import os
import tempfile
import unittest
from pathlib import Path

import workspace_scanner as scanner


class WorkspaceScannerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace_dir.name)

    def tearDown(self):
        self.workspace_dir.cleanup()

    def test_validate_config_rejects_path_escape(self):
        cfg = scanner.Config(output_json="../outside.json")

        with self.assertRaises(ValueError):
            scanner.validate_config(self.root, cfg, watch_interval=1)

    def test_validate_config_rejects_duplicate_outputs(self):
        cfg = scanner.Config(output_json="shared.json", output_md="shared.json")

        with self.assertRaises(ValueError):
            scanner.validate_config(self.root, cfg, watch_interval=1)

    def test_validate_config_requires_positive_watch_interval(self):
        cfg = scanner.Config()

        with self.assertRaises(ValueError):
            scanner.validate_config(self.root, cfg, watch_interval=0)

    def test_collect_files_skips_symlinked_files(self):
        (self.root / "safe.txt").write_text("safe", encoding="utf-8")

        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        outside_file = Path(outside_dir.name) / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")

        symlink_path = self.root / "linked.txt"
        try:
            os.symlink(outside_file, symlink_path)
        except (AttributeError, NotImplementedError, OSError):
            self.skipTest("Symlinks are not available in this environment.")

        scan = scanner.collect_files(self.root, scanner.Config())

        self.assertEqual(["safe.txt"], [item["path"] for item in scan["fileInventory"]])

    def test_normalize_output_path_rejects_symlink_escape(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        outside_file = Path(outside_dir.name) / "outside.json"
        outside_file.write_text("{}", encoding="utf-8")

        symlink_path = self.root / "workspace.json"
        try:
            os.symlink(outside_file, symlink_path)
        except (AttributeError, NotImplementedError, OSError):
            self.skipTest("Symlinks are not available in this environment.")

        with self.assertRaises(ValueError):
            scanner.normalize_output_path(self.root, "workspace.json", "--output-json")

    def test_build_markdown_sanitizes_multiline_git_values(self):
        (self.root / "safe.txt").write_text("safe", encoding="utf-8")
        cfg = scanner.Config()
        scan = scanner.collect_files(self.root, cfg)
        manifest = scanner.build_manifest(self.root, scan, cfg)
        manifest["git"] = {
            "available": True,
            "branch": "main\n## forged heading",
            "headSummary": "abc123\n<script>alert(1)</script>",
            "changedFileCount": 1,
            "statusSummary": "",
            "statusLines": [],
            "error": "",
        }

        markdown = scanner.build_markdown(manifest, cfg)

        self.assertIn("- Branch: `main ## forged heading`", markdown)
        self.assertNotIn("\n## forged heading", markdown)
        self.assertIn("- Head summary: `abc123 <script>alert(1)</script>`", markdown)

    def test_write_output_creates_only_root_manifest_files(self):
        cfg = scanner.Config()
        scanner.validate_config(self.root, cfg, watch_interval=1)
        scan = scanner.collect_files(self.root, cfg)
        manifest = scanner.build_manifest(self.root, scan, cfg)

        scanner.write_output(self.root, manifest, cfg)

        self.assertTrue((self.root / "workspace.json").is_file())
        self.assertTrue((self.root / "workspacememory.md").is_file())
        self.assertFalse((self.root / "graphify-out").exists())

    def test_write_agents_guide_creates_project_agent_file(self):
        cfg = scanner.Config()

        created = scanner.write_agents_guide(self.root, cfg)

        self.assertTrue(created)
        content = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("intelscan --root .", content)
        self.assertIn("workspace.json", content)
        self.assertIn("workspacememory.md", content)

    def test_write_agents_guide_does_not_overwrite_existing_file(self):
        agents_path = self.root / "AGENTS.md"
        agents_path.write_text("custom instructions", encoding="utf-8")

        created = scanner.write_agents_guide(self.root, scanner.Config())

        self.assertFalse(created)
        self.assertEqual("custom instructions", agents_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
