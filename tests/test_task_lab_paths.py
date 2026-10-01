"""Exercise physical path aliases using only disposable temporary directories."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


lab = module("setup_lab_paths_review", "setup-lab.py")
pilot = module("setup_pilot_paths_review", "setup-pilot.py")
paths = module("lab_paths_review", "lab_paths.py")


class PhysicalPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.protected = self.root / "protected"
        self.protected.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def alias(self):
        alias = self.root / "PROTECTED"
        if not alias.exists() or not alias.samefile(self.protected):
            self.skipTest("Temporary filesystem has no case-insensitive path alias")
        return alias

    def test_sibling_roots_are_disjoint_despite_common_ancestors(self):
        sibling = self.root / "lab"
        sibling.mkdir()
        self.assertFalse(paths.overlap(sibling, self.protected))

    def test_nonexistent_lab_under_case_alias_refused_before_mutation(self):
        target = self.alias() / "lab"
        self.assertTrue(paths.overlap(paths.canonical(target), paths.canonical(self.protected)))
        with patch.object(lab.subprocess, "check_output") as git:
            with self.assertRaises(ValueError):
                lab.prepare(target, [self.protected], "v7.22.1")
            git.assert_not_called()
        self.assertFalse(target.exists())

    def test_lab_ancestor_of_case_aliased_protected_root_refused(self):
        nested = self.protected / "nested"
        nested.mkdir()
        self.assertTrue(paths.overlap(self.alias(), nested))

    def test_pilot_rejects_overlap_before_lock_or_record_write(self):
        alias = self.alias()
        target = self.protected / "lab"
        target.mkdir()
        (target / lab.MARKER).write_text(json.dumps({
            "schema": 1, "root": str(target), "protected_roots": [str(alias)]
        }))
        argv = ["setup-pilot.py", "--lab", str(target), "start", "--pair", "one",
                "--condition", "baseline", "--session", "one", "--actor", "human"]
        with patch.object(pilot.sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pilot.main(), 2)
        self.assertFalse((target / ".pilot.lock").exists())
        self.assertFalse((target / "human-pilot.json").exists())

    def test_missing_or_empty_protected_roots_refused(self):
        for roots in ([], [self.root / "missing"], [self.protected / "file"]):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                paths.protected_paths(roots)

    def test_marker_without_protected_roots_refused(self):
        target = self.root / "lab"
        target.mkdir()
        (target / lab.MARKER).write_text(json.dumps({"schema": 1, "root": str(target)}))
        with self.assertRaises(ValueError):
            paths.load_lab(target)


if __name__ == "__main__":
    unittest.main()
