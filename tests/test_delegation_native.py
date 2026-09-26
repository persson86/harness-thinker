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

    def test_effort_is_declared_optional_and_validated(self):
        native.report(self.store, "host-a", "a", "fable", "running", "review", effort="high")
        native.report(self.store, "host-a", "b", "haiku", "running", "count")
        reports = {r["id"]: r for r in native.snapshot(self.store, "host-a")["reports"]}
        self.assertEqual(("high", "unknown"), (reports["a"]["effort"], reports["b"]["effort"]))
        with self.assertRaises(native.DelegationError):
            native.report(self.store, "host-a", "c", "x", "running", "t", effort="turbo")

    def test_records_before_722_without_effort_or_created_at_still_read(self):
        import json
        native.report(self.store, "host-a", "old", "opus", "completed", "legacy")
        path = self.state / "native.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        record = next(iter(value["reports"].values()))
        del record["effort"], record["created_at"]
        path.write_text(json.dumps(value), encoding="utf-8")
        report = native.snapshot(self.store, "host-a")["reports"][0]
        self.assertEqual(("unknown", None), (report["effort"], report["created_at"]))

    def test_reused_id_after_terminal_reopens_in_place_and_repeated_terminal_keeps_time(self):
        import json
        path = self.state / "native.json"
        native.report(self.store, "host-a", "a", "fable", "running", "t")
        native.report(self.store, "host-a", "a", "fable", "completed", "t")
        value = json.loads(path.read_text(encoding="utf-8"))
        record = next(iter(value["reports"].values()))
        record["created_at"] = record["updated_at"] = "2026-01-01T00:00:00+00:00"
        path.write_text(json.dumps(value), encoding="utf-8")
        native.report(self.store, "host-a", "a", "fable", "completed", "t")
        again = native.snapshot(self.store, "host-a")["reports"][0]
        self.assertEqual("2026-01-01T00:00:00+00:00", again["updated_at"])
        native.report(self.store, "host-a", "a", "fable", "running", "t")
        data = native.snapshot(self.store, "host-a")
        self.assertEqual(1, data["reported"])
        self.assertNotEqual("2026-01-01T00:00:00+00:00", data["reports"][0]["created_at"])
        self.assertEqual("running", data["reports"][0]["state"])


if __name__ == "__main__":
    unittest.main()
