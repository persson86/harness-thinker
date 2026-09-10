#!/usr/bin/env python3
"""Board reads stay light and recover visibly from private-state failures."""
import datetime as dt
import fcntl
import io
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_delegation import board  # noqa: E402
from thinker_delegation.runtime import DelegationError, DelegationStore, _atomic, _digest  # noqa: E402


def job(identifier, vault, *, state="completed", source_hash="", **extra):
    now = dt.datetime.now(dt.timezone.utc)
    value = {"id": identifier, "vault": str(vault), "session": "host-a", "state": state,
             "created_epoch": time.time() - 30, "created_at": (now - dt.timedelta(minutes=2)).isoformat(),
             "started_at": (now - dt.timedelta(minutes=1)).isoformat(), "finished_at": now.isoformat(),
             "profile": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "low"},
             "requested_profile": "luna", "task_type": "review", "reason": "fixture",
             "snapshot": {"sources": [{"path": "source.md", "sha256": source_hash}], "instructions": []},
             "validation": "valid", "acceptance": "pending", "feedback": "unknown",
             "acknowledged": False, "transport_success": True,
             "result": {"text": "Reviewable proposal", "model_reported": "gpt-5.6-luna"}}
    value.update(extra)
    return value


class FlakyStore:
    def __init__(self):
        self.calls = 0

    def status(self, session):
        return {"enabled": True, "global_enabled": True, "mode": "request", "concurrency": 2}

    def board_jobs(self):
        self.calls += 1
        if self.calls == 2:
            raise OSError("/private/state/contains-sensitive-detail")
        return [job(str(uuid.uuid4()), Path("/vault"),
                    finished_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat())]


class BoardResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="delegation-board-resilience-")
        self.root = Path(self.temp.name).resolve()
        self.vault, self.state = self.root / "vault", self.root / "state"
        self.vault.mkdir()
        (self.vault / "source.md").write_text("source v1\n", encoding="utf-8")
        self.store = DelegationStore(self.vault, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        directory = self.state / "jobs" / value["id"]
        directory.mkdir(parents=True)
        self.state.chmod(0o700)
        _atomic(directory / "job.json", value)

    def test_watch_marks_one_bad_frame_unavailable_then_recovers_without_raw_error(self):
        stream = io.StringIO()
        sleeps = 0

        def pause(_):
            nonlocal sleeps
            sleeps += 1
            if sleeps == 3:
                raise KeyboardInterrupt

        with mock.patch.object(board.time, "sleep", side_effect=pause):
            self.assertEqual(0, board.watch(FlakyStore(), "host-a", False, 10, 1, False, False, stream=stream))
        frames = stream.getvalue().split("=" * 60)
        self.assertIn("luna", frames[1])
        self.assertIn("estado indisponível", frames[2])
        self.assertIn("Última leitura válida", frames[2])
        self.assertNotIn("private/state", stream.getvalue())
        self.assertIn("luna", frames[3])

    def test_watch_keeps_invalid_cli_values_as_errors(self):
        with self.assertRaises(ValueError):
            board.watch(FlakyStore(), "host-a", False, 10, 1, False, False,
                        stream=io.StringIO(), recent_seconds=-1)

    def test_corrupt_or_incomplete_job_is_unavailable_not_a_zero_snapshot(self):
        identifier = str(uuid.uuid4())
        self.write({"id": identifier, "vault": str(self.vault), "session": "host-a"})
        with self.assertRaises(DelegationError):
            board.payload(self.store, "host-a")
        stream = io.StringIO()
        with mock.patch.object(board.time, "sleep", side_effect=KeyboardInterrupt):
            board.watch(self.store, "host-a", False, 10, 1, False, False, stream=stream)
        self.assertIn("estado indisponível", stream.getvalue())
        self.assertNotIn("q0 r0 p0 f0", stream.getvalue())

    def test_board_avoids_hashes_but_get_and_accept_keep_stale_checks(self):
        source_hash = _digest((self.vault / "source.md").read_bytes())
        value = job(str(uuid.uuid4()), self.vault, source_hash=source_hash)
        self.write(value)
        with mock.patch.object(self.store, "_stale", wraps=self.store._stale) as stale:
            data = board.payload(self.store, "host-a")
            self.assertEqual(1, data["board"]["pending"])
            stale.assert_not_called()
            self.store.get(value["id"])
            self.assertEqual(1, stale.call_count)
        (self.vault / "source.md").write_text("source v2\n", encoding="utf-8")
        self.assertTrue(self.store.accept(value["id"])["accepted_stale"])

    def test_board_recovers_an_orphaned_active_job_instead_of_leaving_it_running(self):
        value = job(str(uuid.uuid4()), self.vault, state="running", finished_at=None,
                    validation="pending", transport_success=None)
        self.write(value)
        data = board.payload(self.store, "host-a", history=True)
        self.assertEqual("interrupted", data["jobs"][0]["state"])
        self.assertEqual((0, 1), (data["board"]["running"], data["board"]["needs_attention"]))

    def test_board_lock_is_nonblocking_without_changing_other_lock_callers(self):
        self.write(job(str(uuid.uuid4()), self.vault))
        self.state.mkdir(exist_ok=True)
        fd = open(self.state / ".lock", "a+")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            started = time.monotonic()
            with self.assertRaises(DelegationError):
                self.store.board_jobs()
            self.assertLess(time.monotonic() - started, 0.2)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    def test_malformed_render_fields_are_state_errors_not_renderer_crashes(self):
        for extra in ({"profile": ["bad"]}, {"profile": {"model": 42}}, {"state": []},
                      {"timeout": "bad"}, {"feedback": []}, {"task_type": 9}, {"role": 8}):
            with self.subTest(extra=extra):
                self.assertRaises(DelegationError, self.store._board_job_locked,
                                  job(str(uuid.uuid4()), self.vault, **extra))

    def test_unavailable_frame_fits_terminal_and_never_becomes_zero_indicator(self):
        data = board.unavailable("host-a", last_success_at="12:00:00")
        self.assertIn("desconhecido", board.render_indicator(data))
        for line in board.render(data, width=80).splitlines():
            self.assertLessEqual(board.visible_len(line), 80)

    def test_corrupt_native_state_is_unavailable_without_renderer_crash(self):
        self.state.mkdir(mode=0o700)
        _atomic(self.state / "native.json", {"schema": 1, "reports": {"bad": {
            "id": "native", "session": "host-a", "model": "luna", "task": "fixture",
            "state": [], "reported": True, "updated_at": "2026-09-09T00:00:00+00:00"}}})
        with self.assertRaises(DelegationError):
            board.payload(self.store, "host-a")


if __name__ == "__main__":
    unittest.main()
