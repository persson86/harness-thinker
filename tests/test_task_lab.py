import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

PATH = Path(__file__).resolve().parents[1] / "scripts/setup-lab.py"
SPEC = importlib.util.spec_from_file_location("setup_lab", PATH)
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


class LabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.protected = self.root / "protected"
        self.protected.mkdir()
        (self.protected / "data.md").write_text("preserve")

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_roots_refused_before_mutation(self):
        path = self.protected / "lab"
        with self.assertRaises(ValueError):
            lab.prepare(path, [self.protected], "v7.22.1")
        self.assertFalse(path.exists())
        with self.assertRaises(ValueError):
            lab.prepare(self.root, [self.protected], "v7.22.1")

    def test_symlink_root_refused(self):
        link = self.root / "alias"
        link.symlink_to(self.protected, target_is_directory=True)
        with self.assertRaises(ValueError):
            lab.prepare(link / "lab", [self.protected], "v7.22.1")

    def test_environment_has_separate_empty_accounts(self):
        area = self.root / "lab"
        area.mkdir()
        env = lab.environment(area)
        for key in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "GROK_HOME", "XDG_STATE_HOME"):
            self.assertTrue(Path(env[key]).is_relative_to(area))
            self.assertEqual(list(Path(env[key]).iterdir()), [])

    @unittest.skipUnless(sys.platform == "darwin", "macOS prevention boundary")
    def test_guard_denies_write_and_audit_detects_external_changes(self):
        area = self.root / "lab"
        area.mkdir()
        (area / "sentinel").mkdir()
        (area / lab.MARKER).write_text(json.dumps({"schema": 1, "root": str(area), "protected_roots": [str(self.protected)]}))
        (area / "protected-before.json").write_text(json.dumps({str(self.protected): lab.inventory(self.protected)}))
        control = lab.execute(area, ["/usr/bin/touch", str(area / "allowed")])
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertTrue((area / "allowed").exists())
        result = lab.execute(area, ["/usr/bin/touch", str(self.protected / "denied")])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.protected / "denied").exists())
        self.assertTrue(lab.audit(area)["protected_unchanged"])
        (self.protected / "data.md").write_text("external change")
        self.assertFalse(lab.audit(area)["protected_unchanged"])


if __name__ == "__main__":
    unittest.main()
