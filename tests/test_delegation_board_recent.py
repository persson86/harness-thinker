#!/usr/bin/env python3
"""Regressões do quadro recente: a limpeza é visual, nunca perda de estado."""
import copy
import datetime as dt
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_delegation import board  # noqa: E402


NOW = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)


def iso(seconds=0):
    return (NOW - dt.timedelta(seconds=seconds)).isoformat()


def external(identifier, *, state="completed", finished_at=iso(1), session="host-a", **extra):
    value = {
        "id": identifier,
        "session": session,
        "state": state,
        "validation": "valid",
        "acceptance": "pending",
        "feedback": "unknown",
        "acknowledged": False,
        "transport_success": True,
        "timeout": 300,
        "task_type": "review",
        "reason": "fixture",
        "created_at": iso(600),
        "started_at": iso(599),
        "finished_at": finished_at,
        "profile": {"provider": "codex", "model": "gpt-5.6-luna",
                    "effort": "low", "requested_profile": "luna"},
    }
    value.update(extra)
    return value


def native_report(identifier, *, state="completed", updated_at=iso(1), session="host-a",
                  model="native-model", task="native fixture"):
    return {"id": identifier, "session": session, "model": model, "task": task,
            "state": state, "reported": True, "updated_at": updated_at}


def native_snapshot(reports):
    return {"reported": len(reports),
            **{state: sum(item["state"] == state for item in reports)
               for state in ("running", "completed", "failed", "cancelled", "unknown")},
            "reports": reports}


class Store:
    def __init__(self, jobs):
        self.jobs = jobs

    def list_jobs(self):
        return list(self.jobs)

    def status(self, session):
        return {"enabled": True, "global_enabled": True, "mode": "request",
                "concurrency": 2, "session": session}


class RecentExternalTests(unittest.TestCase):
    def payload(self, jobs, **kwargs):
        return board.payload(Store(jobs), "host-a", now=NOW, **kwargs)

    def test_completed_recency_bounds_and_history(self):
        jobs = [external("inside", finished_at=iso(299)),
                external("edge", finished_at=iso(300)),
                external("outside", finished_at=iso(301))]
        current = self.payload(jobs, recent_seconds=300)
        self.assertEqual(["inside", "edge"], [item["id"] for item in current["jobs"]])
        historical = self.payload(jobs, recent_seconds=300, history=True)
        self.assertEqual(["inside", "edge", "outside"],
                         [item["id"] for item in historical["jobs"]])

    def test_active_jobs_ignore_limit_and_recency(self):
        jobs = [external("queued", state="queued", finished_at=None),
                external("running", state="running", finished_at=None),
                external("done", finished_at=iso(1))]
        data = self.payload(jobs, limit=0)
        self.assertEqual({"queued", "running"}, {item["id"] for item in data["jobs"]})
        self.assertEqual(1, data["board"]["hidden"])

    def test_missing_malformed_and_future_finished_times_are_hidden_until_history(self):
        jobs = [external("missing", finished_at=None),
                external("malformed", finished_at="not-a-date"),
                external("future", finished_at=(NOW + dt.timedelta(seconds=1)).isoformat())]
        self.assertEqual([], self.payload(jobs)["jobs"])
        self.assertEqual({"missing", "malformed", "future"},
                         {item["id"] for item in self.payload(jobs, history=True)["jobs"]})

    def test_hidden_old_inbox_and_unacknowledged_failure_stay_explicit(self):
        jobs = [external("inbox", finished_at=iso(301)),
                external("failure", state="failed", validation="unavailable", finished_at=iso(301)),
                external("acknowledged-failure", state="failed", validation="unavailable",
                         acknowledged=True, finished_at=iso(301))]
        data = self.payload(jobs)
        self.assertEqual([], data["jobs"])
        self.assertEqual((1, 1), (data["board"]["hidden_pending"], data["board"]["hidden_failures"]))
        rendered = board.render(data, width=100)
        self.assertIn("1 na inbox, 1 falhas sem ack", rendered)
        self.assertNotIn("0 esperando você", rendered)

    def test_payload_is_read_only_for_external_and_native_inputs(self):
        jobs = [external("old", finished_at=iso(301))]
        reports = native_snapshot([native_report("n", updated_at=iso(301))])
        before_jobs, before_reports = copy.deepcopy(jobs), copy.deepcopy(reports)
        self.payload(jobs, native_reports=reports)
        self.assertEqual(before_jobs, jobs)
        self.assertEqual(before_reports, reports)


class RecentNativeTests(unittest.TestCase):
    def payload(self, reports, **kwargs):
        return board.payload(Store([]), "host-a", now=NOW,
                             native_reports=native_snapshot(reports), **kwargs)

    def test_native_only_board_has_separate_recent_table_and_history(self):
        reports = [native_report("current", state="running", updated_at=iso(10), model="native-active"),
                   native_report("recent", updated_at=iso(300), model="native-recent"),
                   native_report("old", updated_at=iso(301), model="native-old")]
        data = self.payload(reports)
        self.assertEqual(["current", "recent"], [item["id"] for item in data["native"]["visible_reports"]])
        text = board.render(data, width=100)
        self.assertIn("Nenhum job externo ativo ou recente", text)
        self.assertIn("NATIVOS · estado reportado pelo host", text)
        self.assertIn("native-active", text)
        self.assertIn("native-recent", text)
        self.assertNotIn("native-old", text)
        historical = self.payload(reports, history=True)
        self.assertEqual({"current", "recent", "old"},
                         {item["id"] for item in historical["native"]["visible_reports"]})

    def test_old_unknown_native_is_not_running_or_failed_but_remains_alerted(self):
        reports = [native_report("lost", state="unknown", updated_at=iso(16 * 60), model="native-lost")]
        data = self.payload(reports)
        self.assertEqual([], data["native"]["visible_reports"])
        self.assertEqual((0, 0, 1), (data["native"]["running"], data["native"]["failed"],
                                     data["native"]["unknown"]))
        text = board.render(data, width=100)
        self.assertIn("1 nativo(s) sem estado atual", text)
        self.assertNotIn("native-lost", text)

    def test_all_sessions_long_unicode_native_rows_fit_at_supported_widths(self):
        jobs = [external("external", session="host-b")]
        reports = native_snapshot([native_report("native", session="host-b", state="running",
                                                 model="模型modelo-longo",
                                                 task="漢字 e texto muito comprido para testar limites")])
        data = board.payload(Store(jobs), None, all_sessions=True, now=NOW, native_reports=reports)
        for width in (80, 100, 120):
            for line in board.render(data, width=width).splitlines():
                self.assertLessEqual(board.visible_len(line), width, (width, line))


class IndicatorHistoryTests(unittest.TestCase):
    def test_indicator_keeps_full_pending_and_failure_counts_when_rows_are_hidden(self):
        jobs = [external("pending", finished_at=iso(301)),
                external("failure", state="failed", validation="unavailable", finished_at=iso(301))]
        data = board.payload(Store(jobs), "host-a", now=NOW)
        self.assertEqual([], data["jobs"])
        self.assertEqual("delegacao externa: q0 r0 p1 f1 · nativa reportada: r0 c0 f0 u0",
                         board.render_indicator(data))


if __name__ == "__main__":
    unittest.main()
