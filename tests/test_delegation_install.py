#!/usr/bin/env python3
"""Installer migration for generated Codex skill ignore rules."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("thinker-delegate", "thinker-model-eval")
RULES = tuple(f"/.agents/skills/{skill}/" for skill in SKILLS)


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
            expected = original + "".join(rule + "\n" for rule in RULES)
            self.assertEqual(expected, (target / ".gitignore").read_text(encoding="utf-8"))
            for skill in SKILLS:
                path = f".agents/skills/{skill}/SKILL.md"
                self.assertTrue((target / path).is_file())
                ignored = subprocess.run(
                    ["git", "check-ignore", "-q", "--", path],
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

    def test_update_refuses_tracked_model_eval_skill(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            skill = target / ".agents/skills/thinker-model-eval/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("user-owned collision\n", encoding="utf-8")
            (target / ".gitignore").write_text("# custom\n", encoding="utf-8")
            self.run_git(target, "init")
            self.run_git(target, "config", "user.name", "Installer Fixture")
            self.run_git(target, "config", "user.email", "installer@example.invalid")
            self.run_git(target, "add", ".gitignore", ".agents/skills/thinker-model-eval/SKILL.md")
            self.run_git(target, "commit", "-m", "fixture")

            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("thinker-model-eval", result.stderr)
            self.assertEqual("user-owned collision\n", skill.read_text(encoding="utf-8"))
            self.assertEqual("# custom\n", (target / ".gitignore").read_text(encoding="utf-8"))

    def test_settings_merge_preserves_custom_statusline_permissions_and_hooks_twice(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            settings = target / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            original = {"statusLine": {"type": "command", "command": "local-status", "refreshInterval": 17},
                        "env": {"LOCAL": "kept"}, "permissions": {"allow": ["Bash(git status)"]},
                        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "local-stop"}]}]}}
            settings.write_text(json.dumps(original), encoding="utf-8")
            for _ in range(2):
                result = self.run_install(target)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            merged = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(original["statusLine"], merged["statusLine"])
            self.assertEqual(original["env"], merged["env"])
            self.assertIn("Bash(git status)", merged["permissions"]["allow"])
            self.assertEqual(1, sum(h["command"] == "local-stop" for group in merged["hooks"]["Stop"]
                                    for h in group["hooks"]))

    def test_fresh_install_gets_harness_statusline_at_five_seconds(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            target.mkdir()
            result = self.run_install(target)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            settings = json.loads((target / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(5, settings["statusLine"]["refreshInterval"])
            self.assertIn("delegation-indicator.py", settings["statusLine"]["command"])

    def test_update_refuses_malformed_or_symlink_settings_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            root, target = Path(directory), Path(directory) / "vault"
            settings = target / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{bad json", encoding="utf-8")
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("{bad json", settings.read_text(encoding="utf-8"))

            settings.unlink()
            outside = root / "outside-settings.json"
            outside.write_text('{"env":{"OUTSIDE":"kept"}}', encoding="utf-8")
            settings.symlink_to(outside)
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual('{"env":{"OUTSIDE":"kept"}}', outside.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
