#!/usr/bin/env python3
"""Metadados nativos: declarados pelo host, sem scheduler ou inferencia."""
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_delegation import native  # noqa: E402
from thinker_delegation.runtime import DelegationStore  # noqa: E402


class NativeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="delegation-native-")
        root = Path(self.temp.name)
        self.vault, self.state = root / "vault", root / "state"
        self.vault.mkdir()
        self.store = DelegationStore(self.vault, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_report_is_metadata_not_a_job_or_scheduler(self):
        native.report(self.store, "host-a", "agent-1", "gpt-native", "running", "small task")
        data = native.snapshot(self.store, "host-a")
        self.assertEqual((1, 1, 0), (data["reported"], data["running"], data["failed"]))
        self.assertFalse((self.state / "jobs").exists())

    def test_old_running_is_unknown_not_failed(self):
        native.report(self.store, "host-a", "agent-1", "gpt-native", "running", "small task")
        path = self.state / "native.json"
        text = path.read_text(encoding="utf-8")
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)).isoformat()
        path.write_text(text.replace('"updated_at": "' + dt.datetime.now(dt.timezone.utc).isoformat() + '"',
                                     '"updated_at": "' + old + '"'), encoding="utf-8")
        # O timestamp exato pode variar entre report e chamada; atualize o dado
        # pelo objeto para manter o caso sintético determinístico.
        import json
        value = json.loads(path.read_text(encoding="utf-8"))
        next(iter(value["reports"].values()))["updated_at"] = old
        path.write_text(json.dumps(value), encoding="utf-8")
        data = native.snapshot(self.store, "host-a")
        self.assertEqual((0, 0, 1), (data["running"], data["failed"], data["unknown"]))

    def test_reports_are_scoped_or_all_sessions_explicitly(self):
        native.report(self.store, "host-a", "a", "one", "completed", "one")
        native.report(self.store, "host-b", "b", "two", "failed", "two")
        self.assertEqual(1, native.snapshot(self.store, "host-a")["reported"])
        self.assertEqual((2, 1), (native.snapshot(self.store, None, all_sessions=True)["reported"],
                                  native.snapshot(self.store, None, all_sessions=True)["failed"]))


if __name__ == "__main__":
    unittest.main()
