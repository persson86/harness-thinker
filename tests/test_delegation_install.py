#!/usr/bin/env python3
"""Installer migration for generated Codex skill ignore rules."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("thinker-delegate", "thinker-model-eval", "thinker-one-page", "thinker-product-view", "thinker-rea", "thinker-advisor", "thinker-reviewer", "thinker-release", "thinker-visual", "thinker-checkin")
AGENTS = ("thinker-blind-reader.md",)
RULES = tuple(f"/.agents/skills/{skill}/" for skill in SKILLS) + tuple(f"/.claude/agents/{agent}" for agent in AGENTS) + ("/output/",)


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
            for agent in AGENTS:
                path = f".claude/agents/{agent}"
                self.assertTrue((target / path).is_file())
                ignored = subprocess.run(
                    ["git", "check-ignore", "-q", "--", path],
                    cwd=target, timeout=15,
                )
                self.assertEqual(0, ignored.returncode)

            second = self.run_install(target)
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(expected, (target / ".gitignore").read_text(encoding="utf-8"))

    def test_update_keeps_vault_agents_and_refuses_tracked_generated_agent(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            own = target / ".claude/agents/vault-scout.md"
            own.parent.mkdir(parents=True)
            own.write_text("---\nname: vault-scout\n---\nlocal\n", encoding="utf-8")
            (target / ".gitignore").write_text("# custom\n", encoding="utf-8")
            self.run_git(target, "init")
            self.run_git(target, "add", ".gitignore", ".claude/agents/vault-scout.md")
            first = self.run_install(target)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertEqual("---\nname: vault-scout\n---\nlocal\n", own.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            generated = target / ".claude/agents/thinker-blind-reader.md"
            generated.parent.mkdir(parents=True)
            generated.write_text("versionado pelo usuario\n", encoding="utf-8")
            (target / ".gitignore").write_text("# custom\n", encoding="utf-8")
            self.run_git(target, "init")
            self.run_git(target, "add", ".gitignore", ".claude/agents/thinker-blind-reader.md")
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("agente gerado já está rastreado", result.stderr)
            self.assertEqual("versionado pelo usuario\n", generated.read_text(encoding="utf-8"))
            self.assertEqual("# custom\n", (target / ".gitignore").read_text(encoding="utf-8"))

    def _vault(self, directory, gitignore="# custom\n"):
        target = Path(directory) / "vault"
        target.mkdir()
        (target / ".gitignore").write_text(gitignore, encoding="utf-8")
        self.run_git(target, "init")
        return target

    def test_update_refuses_untracked_agent_without_harness_provenance(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            agent = target / ".claude/agents/thinker-blind-reader.md"
            agent.parent.mkdir(parents=True)
            agent.write_text("meu agente\n", encoding="utf-8")
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("não é a cópia instalada pelo harness", result.stderr)
            self.assertEqual("meu agente\n", agent.read_text(encoding="utf-8"))
            self.assertFalse((target / "harness/.version").exists())

    def test_update_refuses_locally_edited_generated_agent(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            first = self.run_install(target)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            agent = target / ".claude/agents/thinker-blind-reader.md"
            agent.write_text(agent.read_text(encoding="utf-8") + "ajuste local\n", encoding="utf-8")
            second = self.run_install(target)
            self.assertNotEqual(0, second.returncode)
            self.assertIn("alterada localmente", second.stderr)
            self.assertTrue(agent.read_text(encoding="utf-8").endswith("ajuste local\n"))

    def test_update_refuses_symlinked_agents_dir(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "thinker-blind-reader.md").write_text("externo\n", encoding="utf-8")
            (target / ".claude").mkdir()
            (target / ".claude/agents").symlink_to(outside)
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("symlink", result.stderr)
            self.assertEqual("externo\n", (outside / "thinker-blind-reader.md").read_text(encoding="utf-8"))

    def test_update_refuses_directory_at_agent_path_before_installing(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            (target / ".claude/agents/thinker-blind-reader.md").mkdir(parents=True)
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("não é arquivo regular", result.stderr)
            self.assertFalse((target / "harness/.version").exists())

    def test_update_refuses_directory_at_any_payload_path(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            (target / "harness/contract.md").mkdir(parents=True)
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("como diretório", result.stderr)
            self.assertFalse((target / "harness/.version").exists())

    def test_update_refuses_rule_negated_elsewhere(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = self._vault(directory)
            (target / ".claude/agents").mkdir(parents=True)
            (target / ".claude/agents/.gitignore").write_text("!thinker-blind-reader.md\n", encoding="utf-8")
            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("continua visível ao Git", result.stderr)
            self.assertFalse((target / ".claude/agents/thinker-blind-reader.md").exists())

    def test_blind_reader_agent_is_read_only_and_omits_claude_md(self):
        text = (ROOT / "payload/.claude/agents/thinker-blind-reader.md").read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        fields = dict(line.split(":", 1) for line in front.strip().splitlines())
        self.assertEqual("thinker-blind-reader", fields["name"].strip())
        self.assertEqual("true", fields["omitClaudeMd"].strip())
        self.assertEqual({"Read", "Grep", "Glob"}, {t.strip() for t in fields["tools"].split(",")})
        self.assertNotIn("model", fields)

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

    def test_update_refuses_tracked_product_view_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-product-view")

    def test_update_refuses_tracked_rea_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-rea")

    def test_update_refuses_tracked_visual_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-visual")

    def test_update_refuses_tracked_checkin_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-checkin")

    def test_update_refuses_tracked_advisor_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-advisor")

    def test_update_refuses_tracked_reviewer_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-reviewer")

    def test_update_refuses_tracked_release_skill_before_replacing_it(self):
        self.check_tracked_skill_preserved("thinker-release")

    def test_reinstall_preserves_autonomy_off_and_does_not_start_consultations(self):
        with tempfile.TemporaryDirectory(prefix="consultation-install-") as directory:
            root = Path(directory)
            target, state = root / "vault", root / "private-state"
            target.mkdir()
            result = self.run_install(target)
            self.assertEqual(0, result.returncode, result.stderr)
            cli = ["python3", "-B", str(target / "harness/scripts/delegate.py"),
                   "--vault", str(target), "--state-dir", str(state),
                   "--session", "install-fixture", "--json"]
            disabled = subprocess.run(cli + ["autonomy", "off", "--all"],
                                      capture_output=True, text=True, check=True, timeout=15)
            self.assertFalse(json.loads(disabled.stdout)["default_enabled"])
            before = (state / "consultations.json").read_bytes()
            result = self.run_install(target)
            self.assertEqual(0, result.returncode, result.stderr)
            status = subprocess.run(cli + ["autonomy", "status"],
                                    capture_output=True, text=True, check=True, timeout=15)
            value = json.loads(status.stdout)
            self.assertFalse(value["enabled"])
            self.assertEqual([], value["calls"])
            self.assertEqual(before, (state / "consultations.json").read_bytes())
            self.assertFalse((state / "jobs").exists())

    def check_tracked_skill_preserved(self, name):
        with tempfile.TemporaryDirectory(prefix="skill-install-") as directory:
            target = Path(directory) / "vault"
            relative = f".agents/skills/{name}/SKILL.md"
            skill = target / relative
            skill.parent.mkdir(parents=True)
            skill.write_text("user-owned product view\n", encoding="utf-8")
            (target / ".gitignore").write_text("# custom\n", encoding="utf-8")
            self.run_git(target, "init")
            self.run_git(target, "config", "user.name", "Installer Fixture")
            self.run_git(target, "config", "user.email", "installer@example.invalid")
            self.run_git(target, "add", ".gitignore", relative)
            self.run_git(target, "commit", "-m", "fixture")

            result = self.run_install(target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn(name, result.stderr)
            self.assertEqual("user-owned product view\n", skill.read_text(encoding="utf-8"))
            self.assertFalse((target / f".claude/commands/{name}.md").exists())
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

    def test_fresh_install_sets_compaction_window_and_post_compact_hook(self):
        with tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
            target = Path(directory) / "vault"
            target.mkdir()
            result = self.run_install(target)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            settings = json.loads((target / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(500000, settings["autoCompactWindow"])
            [grupo] = settings["hooks"]["SessionStart"]
            self.assertEqual("compact", grupo["matcher"])
            self.assertIn("post-compact.sh", grupo["hooks"][0]["command"])
            self.assertTrue(os.access(target / ".claude/hooks/post-compact.sh", os.X_OK))

    def test_update_preserves_local_compaction_window_and_does_not_duplicate_hook(self):
        for local in (400000, "auto"):
            with self.subTest(local=local), tempfile.TemporaryDirectory(prefix="delegation-install-") as directory:
                target = Path(directory) / "vault"
                settings = target / ".claude/settings.json"
                settings.parent.mkdir(parents=True)
                settings.write_text(json.dumps({"autoCompactWindow": local}), encoding="utf-8")
                for _ in range(2):
                    result = self.run_install(target)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                merged = json.loads(settings.read_text(encoding="utf-8"))
                self.assertEqual(local, merged["autoCompactWindow"])
                comandos = [h["command"] for g in merged["hooks"]["SessionStart"] for h in g["hooks"]]
                self.assertEqual(1, sum("post-compact.sh" in c for c in comandos))

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
