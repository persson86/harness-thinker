import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload/harness/scripts"))
from thinker_delegation import adapters as a


class AdapterTests(unittest.TestCase):
    def test_git_default_and_explicit_override_are_independent(self):
        default = a.resolve_profile("git")
        self.assertEqual((default["provider"], default["model"], default["effort"]),
                         ("codex", "gpt-5.6-luna", "low"))
        explicit = a.resolve_profile("git", explicit="sonnet", session_profile="opus")
        self.assertEqual((explicit["provider"], explicit["model_source"]), ("claude", "explicit"))
        self.assertEqual(a.resolve_profile("git")["model"], "gpt-5.6-luna")

    def test_astra_and_fable_profiles_are_explicit_subscription_routes(self):
        astra = a.resolve_profile(explicit="astra")
        fable = a.resolve_profile(explicit="fable")
        self.assertEqual((astra["provider"], astra["model"], astra["effort"]),
                         ("codex", "gpt-6-astra", "high"))
        self.assertEqual((fable["provider"], fable["model"], fable["effort"]),
                         ("claude", "fable", "high"))
        self.assertEqual("subscription", fable["auth"])

    def test_session_precedence_and_unknown_model_no_fallback(self):
        self.assertEqual(a.resolve_profile("git", session_profile="sonnet")["model"], "sonnet")
        with self.assertRaises(a.AdapterError):
            a.resolve_profile("git", explicit="unavailable")
        self.assertEqual(a.resolve_profile(explicit="new-model", provider="codex")["model"], "new-model")
        with self.assertRaises(a.AdapterError):
            a.resolve_profile(explicit="sonnet", provider="grok")

    def test_model_strings_cannot_inject_options(self):
        for name in ("", " ", "--bypass", "model\n--bypass", "model; touch /tmp/pwn"):
            with self.assertRaises(a.AdapterError):
                a.resolve_profile(explicit=name, provider="codex")

    def test_subscription_environment_does_not_inherit_api_or_tool_secrets(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret", "OPENAI_API_KEY": "secret",
                                    "XAI_API_KEY": "secret", "GH_TOKEN": "secret", "PYTHONPATH": "evil"}):
            env = a.safe_env(a.resolve_profile(explicit="sonnet"))
            for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GH_TOKEN", "PYTHONPATH"):
                self.assertNotIn(key, env)
            self.assertEqual(env["THINKER_DELEGATION_CHILD"], "1")
            self.assertEqual(env.get("HOME"), os.environ.get("HOME"))

    def test_api_is_forbidden_even_when_a_key_and_budget_exist(self):
        for name in ("luna", "sonnet", "grok"):
            with self.assertRaises(a.AdapterError):
                a.resolve_profile(explicit=name, auth="api")
            profile = a.resolve_profile(explicit=name)
            profile.update(auth="api", api_budget_usd=1)
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"}), self.assertRaises(a.AdapterError):
                a.safe_env(profile)

    def test_commands_disable_tools_and_never_interpolate_task_in_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "fake cli"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            prompt = Path(tmp) / "prompt.txt"
            prompt.write_text("$(touch forbidden) `echo bad` ; do not run")
            for name in ("luna", "sonnet", "grok"):
                profile = a.resolve_profile(explicit=name)
                profile["binary"] = str(executable)
                with patch.object(a, "_prepare_grok", return_value={"qualification": "fixture"}):
                    command = a.build_command(profile, tmp, prompt)
                self.assertNotIn(prompt.read_text(), command)
                self.assertNotIn("--dangerously-skip-permissions", command)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
                if name == "luna":
                    self.assertIn("read-only", command)
                    self.assertIn("shell_tool", command)
                    self.assertEqual(command[-1], "-")
                else:
                    self.assertEqual(command[command.index("--tools") + 1], "")
                if name == "sonnet":
                    self.assertNotIn("--json-schema", command)
                    self.assertEqual(command[command.index("--output-format") + 1], "json")
                    settings = json.loads(command[command.index("--settings") + 1])
                    self.assertEqual(settings["forceLoginMethod"], "claudeai")

    def test_codex_requires_completed_turn_and_final_message(self):
        p = {"provider": "codex"}
        message = {"type": "item.completed", "item": {"type": "agent_message", "text": "Proposta"}}
        with self.assertRaises(a.AdapterError):
            a.parse_result(p, json.dumps(message), "", 0)
        output = "\n".join(map(json.dumps, [message, {"type": "turn.completed", "usage": {"input_tokens": 10}}]))
        result = a.parse_result(p, output, "", 0)
        self.assertEqual(result["text"], "Proposta")
        self.assertIsNone(result["model_reported"])
        with self.assertRaises(a.AdapterError):
            a.parse_result(p, output + '\n{"type":"error"}', "", 0)

    def test_claude_structured_field_and_error(self):
        p = {"provider": "claude"}
        payload = {"subtype": "success", "structured_output": {"text": "Resumo", "limitations": ["Atribuição incerta"]},
                   "modelUsage": {"claude-sonnet-fixture": {}}, "session_id": "test-session"}
        result = a.parse_result(p, json.dumps(payload), "", 0)
        self.assertEqual(result["text"], "Resumo")
        self.assertEqual(result["model_reported"], "claude-sonnet-fixture")
        payload["is_error"] = True
        with self.assertRaises(a.AdapterError):
            a.parse_result(p, json.dumps(payload), "", 0)

    def test_subscription_probe_refuses_saved_api_credentials_without_exposing_details(self):
        from subprocess import CompletedProcess
        for name, login in (("luna", "Logged in using an API key: private-value"),
                            ("sonnet", '{"loggedIn":true,"authMethod":"api_key","email":"private-value"}')):
            with tempfile.TemporaryDirectory() as tmp:
                binary = Path(tmp) / "fake"
                binary.write_text("#!/bin/sh\nexit 0\n")
                binary.chmod(0o700)
                profile = dict(a.resolve_profile(explicit=name), binary=str(binary))
                outputs = ["--ignore-user-config --ignore-rules --json --sandbox --safe-mode --restricted --tools --output-format", "fixture", login]
                calls = [CompletedProcess([], 0, out, "") for out in outputs]
                with patch.object(a.subprocess, "run", side_effect=calls), self.assertRaises(a.AdapterError) as caught:
                    a.probe(profile, tmp)
                self.assertNotIn("private-value", str(caught.exception))

    def test_empty_malformed_or_failed_never_succeeds(self):
        cases = [("claude", '{"subtype":"success","result":""}'),
                 ("grok", '{"response":""}'), ("grok", '{"error":"denied"}'),
                 ("codex", '{"type":"turn.completed"}')]
        for provider, output in cases:
            with self.subTest(provider=provider, output=output), self.assertRaises(a.AdapterError):
                a.parse_result({"provider": provider}, output, "private diagnostic", 0)
        with self.assertRaises(a.AdapterError):
            a.parse_result({"provider": "claude"}, "{truncated", "", 0)
        with self.assertRaises(a.AdapterError):
            a.parse_result({"provider": "grok"}, '{"response":"text"}', "", 1)

    def test_failure_diagnostic_is_actionable_and_never_echoes_logs(self):
        cases = [("Rate limit reached: TOKEN-SECRET", "provider_limit"),
                 ("error_max_structured_output_retries PRIVATE-PROMPT", "structured_output_failed"),
                 ("ENOTFOUND host PRIVATE-ENDPOINT", "connection_failed"),
                 ("model unavailable-model does not exist PRIVATE-CONTEXT", "model_unavailable"),
                 ("Something unknown PRIVATE-CONTEXT", "provider_failed")]
        for log, code in cases:
            result = a.diagnose_failure({"provider": "claude"}, log, "credential=PRIVATE-VALUE", 1)
            self.assertEqual(result["code"], code)
            self.assertNotIn("PRIVATE", json.dumps(result))
            self.assertNotIn("TOKEN-SECRET", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
