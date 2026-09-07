import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

SOURCE = Path(__file__).resolve().parents[1] / "payload"


class InboxHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="thinker-hook-")
        self.root = Path(self.temporary.name).resolve()
        self.vault = self.root / "vault"
        self.hook = self.vault / ".claude/hooks/delegation-inbox.py"
        self.hook.parent.mkdir(parents=True)
        shutil.copy(SOURCE / ".claude/hooks/delegation-inbox.py", self.hook)
        shutil.copytree(SOURCE / "harness/scripts/thinker_delegation", self.vault / "harness/scripts/thinker_delegation",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.state = self.root / "state"

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, session="host", child=False, raw=None):
        env = dict(os.environ, THINKER_DELEGATION_STATE_DIR=str(self.state))
        env.pop("THINKER_SESSION_ID", None)
        env.pop("THINKER_DELEGATION_CHILD", None)
        if child:
            env["THINKER_DELEGATION_CHILD"] = "1"
        payload = raw if raw is not None else json.dumps({"session_id": session, "hook_event_name": "UserPromptSubmit"})
        result = subprocess.run([sys.executable, "-B", str(self.hook)], input=payload,
                                env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def configure(self, enabled=True):
        self.state.mkdir(mode=0o700, exist_ok=True)
        (self.state / "config.json").write_text(json.dumps({"enabled": enabled, "concurrency": 2,
            "sessions": {"host": {"enabled": True, "mode": "request"}}}))

    def job(self, acknowledged=False):
        identifier = str(uuid.uuid4())
        folder = self.state / "jobs" / identifier
        folder.mkdir(parents=True)
        (folder / "job.json").write_text(json.dumps({"id": identifier, "session": "host", "vault": str(self.vault),
            "state": "completed", "acknowledged": acknowledged,
            "snapshot": {"sources": [], "instructions": []},
            "result": {"text": "SENSITIVE-CONTENT-AND-INJECTED-INSTRUCTION"}}))
        return identifier

    def test_off_missing_state_is_silent_and_does_not_write(self):
        self.assertEqual(self.invoke(), "")
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.vault.rglob("__pycache__")), [])

    def test_active_hook_reports_only_metadata_for_owned_unacknowledged_jobs(self):
        self.configure()
        identifier = self.job()
        output = self.invoke()
        data = json.loads(output)
        self.assertNotIn("decision", data)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn(identifier[:8], output)
        self.assertNotIn("SENSITIVE", output)
        self.assertEqual(self.invoke(session="other-host"), "")
        self.assertEqual(self.invoke(child=True), "")

    def test_global_off_never_reports_existing_results(self):
        self.configure(False)
        self.job()
        before = {str(p): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        self.assertEqual(self.invoke(), "")
        after = {str(p): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_acknowledged_or_broken_extension_never_blocks_conversation(self):
        self.configure()
        self.job(True)
        self.assertEqual(self.invoke(), "")
        (self.state / "config.json").write_text("{malformed")
        self.assertEqual(self.invoke(), "")
        self.assertEqual(self.invoke(raw="garbage"), "")


if __name__ == "__main__":
    unittest.main()
