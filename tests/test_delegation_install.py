#!/usr/bin/env python3
"""Installer migration for the generated delegation skill ignore rule."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RULE = "/.agents/skills/thinker-delegate/"


class DelegationInstallTests(unittest.TestCase):
    def run_install(self, target):
        return subprocess.run(
            ["bash", str(ROOT / "install.sh"), str(target), "--update"],
            cwd=ROOT, capture_output=True, text=True, timeout=45,
        )

    def run_git(self, target, *args):
        return subprocess.run(["git", *args], cwd=target, capture_output=True,
                              text=True, timeout=15, check=True)

    def test_update_preserves_existing_gitignore_and_appends_exact_rule_once(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            target.mkdir()
            original = "# Regras locais\nprivate/\n!private/keep.md\n"
            (target / ".gitignore").write_text(original, encoding="utf-8")
            self.run_git(target, "init")

            first = self.run_install(target)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            expected = original + RULE + "\n"
            self.assertEqual(expected, (target / ".gitignore").read_text(encoding="utf-8"))
            self.assertTrue((target / ".agents/skills/thinker-delegate/SKILL.md").is_file())
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", "--", ".agents/skills/thinker-delegate/SKILL.md"],
                cwd=target, timeout=15,
            )
            self.assertEqual(0, ignored.returncode)

            second = self.run_install(target)
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(expected, (target / ".gitignore").read_text(encoding="utf-8"))

    def test_update_refuses_gitignore_symlink_before_installing_skill(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            root = Path(directory)
            target = root / "vault"
            target.mkdir()
            outside = root / "outside-gitignore"
            outside.write_text("# externa\n", encoding="utf-8")
            (target / ".gitignore").symlink_to(outside)

            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn(".gitignore do target não pode ser symlink", result.stderr)
            self.assertEqual("# externa\n", outside.read_text(encoding="utf-8"))
            self.assertFalse((target / ".agents").exists())

    def test_update_refuses_preexisting_tracked_generated_skill(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            skill = target / ".agents/skills/thinker-delegate/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("user-owned collision\n", encoding="utf-8")
            (target / ".gitignore").write_text("# custom\n", encoding="utf-8")
            self.run_git(target, "init")
            self.run_git(target, "config", "user.name", "Installer Fixture")
            self.run_git(target, "config", "user.email", "installer@example.invalid")
            self.run_git(target, "add", ".gitignore", ".agents/skills/thinker-delegate/SKILL.md")
            self.run_git(target, "commit", "-m", "fixture")

            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("skill gerado já está rastreado", result.stderr)
            self.assertEqual("user-owned collision\n", skill.read_text(encoding="utf-8"))
            self.assertEqual("# custom\n", (target / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
