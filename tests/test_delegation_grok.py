import json
import os
from pathlib import Path
import stat
from subprocess import CompletedProcess
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload/harness/scripts"))
from thinker_delegation import grok_isolation as g


def safe_env(home):
    env = {
        "HOME": str(home),
        "GROK_DISABLE_API_KEY_AUTH": "1",
        "GROK_DISABLE_AUTOUPDATER": "1",
        "GROK_MEMORY": "0",
        "GROK_SUBAGENTS": "0",
        "GROK_WRITE_FILE": "0",
        "GROK_TOOL_SEARCH": "0",
        "GROK_LSP_TOOLS": "0",
        "GROK_WEB_FETCH": "0",
    }
    for product in ("CURSOR", "CLAUDE", "CODEX"):
        for kind in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"):
            env["GROK_" + product + "_" + kind + "_ENABLED"] = "0"
    return env


class Fixture:
    def __init__(self, root, config_text=None):
        self.root = Path(root)
        self.home = self.root / "home"
        self.grok_home = self.home / ".grok"
        self.workspace = self.root / "job"
        self.home.mkdir(mode=0o700)
        self.grok_home.mkdir(mode=0o700)
        self.workspace.mkdir(mode=0o700)
        self.binary = self.root / "grok"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.binary.chmod(0o700)
        self.auth = self.grok_home / "auth.json"
        self.auth.write_text(json.dumps({
            "https://auth.x.ai::fixture": {
                "auth_mode": "oidc",
                "oidc_issuer": "https://auth.x.ai",
                "key": "private-access-token",
                "refresh_token": "private-refresh-token",
            },
        }), encoding="utf-8")
        self.auth.chmod(0o600)
        self.user_config = self.grok_home / "config.toml"
        if config_text is not None:
            self.user_config.write_text(config_text, encoding="utf-8")
            self.user_config.chmod(0o644)
        self.env = safe_env(self.home)
        self.profile = {"provider": "grok", "auth": "subscription",
                        "binary": str(self.binary)}

    def report(self, second=False, *, plugins=None, warnings=None,
               extra_layers=None, hooks=None):
        layers = []
        if self.user_config.exists():
            layers.append({"role": "user", "path": str(self.user_config)})
        layers.extend(extra_layers or [])
        if second:
            layers.append({"role": "project",
                           "path": str(self.workspace / ".grok/config.toml")})
        return {
            "grokVersion": g.PINNED_VERSION,
            "loginPolicy": {"apiKeyAuthDisabled": True, "disableApiKeyAuth": True},
            "configWarnings": warnings or [],
            "mcpConfigProblems": [],
            "configSources": {"layers": layers},
            "projectRoot": None,
            "plugins": plugins or [],
            "hooks": hooks or [],
            "mcpServers": [],
            "lspServers": [],
        }

    def calls(self, first, second, on_second=None):
        inspect_count = 0

        def invoke(argv, **kwargs):
            nonlocal inspect_count
            if argv[-1] == "--version":
                return CompletedProcess(argv, 0, g.PINNED_FINGERPRINT + "\n", "")
            self.assert_inspect(argv)
            inspect_count += 1
            if inspect_count == 2 and on_second:
                on_second()
            report = first if inspect_count == 1 else second
            return CompletedProcess(argv, 0, json.dumps(report), "")

        return invoke

    @staticmethod
    def assert_inspect(argv):
        if argv[-2:] != ["inspect", "--json"]:
            raise AssertionError("unexpected command: " + repr(argv))


class GrokIsolationTests(unittest.TestCase):
    CURRENT_STYLE_CONFIG = """
[cli]
installer = "local"

[marketplace]
default_skills_installs_purged = true
official_marketplace_auto_installed = true
sources = {}

[ui]
compact_mode = true
fork_secondary_model = false
max_thoughts_width = 120
permission_mode = "default"
yolo = false

[privacy]
privacy_banner_acked = true
"""
    PRIVACY_WARNING = {
        "target": "configKey", "path": "privacy", "kind": "unknown-field",
        "reason": "unrecognized config key",
    }

    def test_vendored_tomli_imports_in_package_and_detached_worker_modes(self):
        if sys.version_info < (3, 11):
            self.assertEqual(g._toml.__version__, "2.0.1")
        module_dir = Path(g.__file__).resolve().parent
        code = ("import sys; sys.path.insert(0, " + repr(str(module_dir)) + "); "
                "import grok_isolation; print(grok_isolation._toml.__name__)")
        result = subprocess.run([sys.executable, "-c", code], text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = "_vendor.tomli" if sys.version_info < (3, 11) else "tomllib"
        self.assertEqual(result.stdout.strip(), expected)

    def test_accepts_benign_user_config_and_disables_duplicate_plugin_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp, self.CURRENT_STYLE_CONFIG)
            original = fx.user_config.read_bytes()
            plugins = [
                {"name": "shared", "scope": "claude", "path": "/plugins/claude",
                 "provides": {"hooks": ["one"]}},
                {"name": "shared", "scope": "codex", "path": "/plugins/codex",
                 "provides": {"hooks": ["two"]}},
            ]
            plugin_hook = {"source": {"type": "plugin", "plugin_name": "shared"}}
            first = fx.report(plugins=plugins, warnings=[self.PRIVACY_WARNING],
                              hooks=[plugin_hook])
            second = fx.report(second=True, plugins=plugins,
                               warnings=[self.PRIVACY_WARNING], hooks=[plugin_hook])
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run",
                                 side_effect=fx.calls(first, second)) as run:
                result = g.prepare(fx.profile, fx.workspace, fx.env)

            self.assertEqual(result["disabled_plugins"], ["shared"])
            self.assertEqual(run.call_count, 4)
            private = fx.workspace / ".grok/config.toml"
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(private.parent.stat().st_mode), 0o700)
            self.assertEqual(private.read_text().count('"shared"'), 1)
            self.assertEqual(fx.user_config.read_bytes(), original)
            serialized = json.dumps(result)
            self.assertNotIn("private-access-token", serialized)
            self.assertNotIn("private-refresh-token", serialized)
            self.assertIn("ambient_config_parsed_and_stable", result["assertions"])

    def test_absent_debug_layer_is_not_treated_as_an_existing_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            absent = {"role": "requirements", "path": str(fx.root / "requirements.toml"),
                      "note": "not found (optional)"}
            first = fx.report(extra_layers=[absent])
            second = fx.report(second=True, extra_layers=[absent])
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run", side_effect=fx.calls(first, second)):
                result = g.prepare(fx.profile, fx.workspace, fx.env)
            self.assertEqual(result["disabled_plugins"], [])

    def test_accepts_inspected_empty_managed_and_requirements_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            layers = []
            for role, name in (("managed", "managed_config.toml"),
                               ("requirements", "requirements.toml")):
                path = fx.grok_home / name
                path.write_text("", encoding="utf-8")
                path.chmod(0o644)
                layers.append({"role": role, "path": str(path), "note": "empty"})
            first = fx.report(extra_layers=layers)
            second = fx.report(second=True, extra_layers=layers)
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run", side_effect=fx.calls(first, second)):
                result = g.prepare(fx.profile, fx.workspace, fx.env)
            self.assertIn("ambient_config_parsed_and_stable", result["assertions"])

    def test_rejects_byok_endpoint_auth_helpers_and_model_selection_without_values(self):
        forbidden = {
            "custom model": '[model.custom]\nbase_url="https://private.invalid"\napi_key="SECRET"\n',
            "endpoint": '[endpoints]\nmodels_base_url="https://private.invalid"\n',
            "provider helper": '[network]\nenv_http_headers={Authorization="SECRET_ENV"}\n',
            "selected model": '[models]\ndefault="private-model"\n',
            "auth": '[authentication]\ntoken="SECRET"\n',
            "nested table array": 'entries=[{name="safe", env_key="SECRET"}]\n',
        }
        for label, content in forbidden.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "config.toml"
                path.write_text(content, encoding="utf-8")
                path.chmod(0o600)
                with self.assertRaises(g.GrokIsolationError) as caught:
                    g._read_config(path)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("private.invalid", str(caught.exception))
                self.assertNotIn("private-model", str(caught.exception))

    def test_rejects_malformed_or_mutating_user_config_and_unknown_real_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            malformed = Path(tmp) / "bad.toml"
            malformed.write_text('[ui]\nvalue="PRIVATE\n', encoding="utf-8")
            with self.assertRaises(g.GrokIsolationError) as caught:
                g._read_config(malformed)
            self.assertNotIn("PRIVATE", str(caught.exception))

        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp, "[ui]\ncompact_mode=true\n")
            first, second = fx.report(), fx.report(second=True)

            def mutate():
                fx.user_config.write_text("[ui]\ncompact_mode=false\n", encoding="utf-8")

            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run",
                                 side_effect=fx.calls(first, second, mutate)), \
                    self.assertRaises(g.GrokIsolationError):
                g.prepare(fx.profile, fx.workspace, fx.env)

        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            policy = fx.root / "unknown.toml"
            policy.write_text("[ui]\ncompact_mode=true\n", encoding="utf-8")
            actual = {"role": "future-policy", "path": str(policy)}
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run",
                                 side_effect=fx.calls(fx.report(extra_layers=[actual]),
                                                      fx.report(second=True))), \
                    self.assertRaises(g.GrokIsolationError):
                g.prepare(fx.profile, fx.workspace, fx.env)

    def test_rejects_unqualified_warning_direct_executable_and_api_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            warning = {"target": "configKey", "path": "models", "kind": "unknown-field",
                       "reason": "unrecognized config key"}
            first = fx.report(warnings=[warning])
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run", side_effect=fx.calls(first, first)), \
                    self.assertRaises(g.GrokIsolationError):
                g.prepare(fx.profile, fx.workspace, fx.env)

        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            direct = [{"source": {"type": "config", "path": "PRIVATE"}}]
            first = fx.report(hooks=direct)
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    patch.object(g.subprocess, "run", side_effect=fx.calls(first, first)), \
                    self.assertRaises(g.GrokIsolationError) as caught:
                g.prepare(fx.profile, fx.workspace, fx.env)
            self.assertNotIn("PRIVATE", str(caught.exception))

        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.env["XAI_API_KEY"] = "PRIVATE"
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    self.assertRaises(g.GrokIsolationError) as caught:
                g.prepare(fx.profile, fx.workspace, fx.env)
            self.assertNotIn("PRIVATE", str(caught.exception))

        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.env["GROK_CONFIG"] = '{"plugins":{"disabled":[]}}'
            with patch.dict(os.environ, {"HOME": str(fx.home)}, clear=True), \
                    self.assertRaises(g.GrokIsolationError):
                g.prepare(fx.profile, fx.workspace, fx.env)


if __name__ == "__main__":
    unittest.main()
