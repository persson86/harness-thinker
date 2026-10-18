import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload/harness/scripts"))
from thinker_delegation import adapters, quota_observe, routing

NOW = 1_792_260_000.0


def iso(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def event(measured, primary=10.0, secondary=5.0, primary_reset=NOW + 3600, secondary_reset=NOW + 86400):
    return {"timestamp": iso(measured), "type": "event_msg",
            "payload": {"type": "token_count", "info": None, "rate_limits": {
                "limit_id": "codex", "limit_name": None,
                "primary": {"used_percent": primary, "window_minutes": 300, "resets_at": primary_reset},
                "secondary": {"used_percent": secondary, "window_minutes": 10080, "resets_at": secondary_reset},
                "credits": {"has_credits": False}, "plan_type": "plus", "rate_limit_reached_type": None}}}


def observation(measured, primary=10.0, secondary=5.0, primary_reset=NOW + 3600, secondary_reset=NOW + 86400):
    return {"measured_at": measured, "windows": [
        {"minutes": 300, "used_percent": primary, "resets_at": primary_reset},
        {"minutes": 10080, "used_percent": secondary, "resets_at": secondary_reset}]}


class ReadCodexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="quota-observe-")
        self.home = Path(self.temporary.name)
        self.day = self.home / "sessions/2026/10/17"
        self.day.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def rollout(self, name, records, mtime=None, tail=b""):
        path = self.day / name
        body = b"".join(json.dumps(r).encode() + b"\n" for r in records) + tail
        path.write_bytes(body)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_event_time_decides_between_rollouts_not_mtime(self):
        meta = {"timestamp": iso(NOW), "type": "session_meta", "payload": {"originator": "codex-tui"}}
        self.rollout("rollout-a.jsonl", [meta, event(NOW - 600, primary=40.0)], mtime=NOW - 10)
        self.rollout("rollout-b.jsonl", [meta, event(NOW - 60, primary=70.0)], mtime=NOW - 500)
        self.rollout("rollout-c.jsonl", [meta], mtime=NOW)
        found = quota_observe.read_codex(self.home)
        self.assertEqual(NOW - 60, found["measured_at"])
        self.assertEqual(70.0, found["windows"][0]["used_percent"])
        self.assertEqual({"provider", "source", "measured_at", "windows", "limit_id", "plan_type"}, set(found))

    def test_truncated_last_line_and_foreign_records_are_ignored(self):
        self.rollout("rollout-a.jsonl", [event(NOW - 120, primary=33.0), {"type": "response_item"}],
                     tail=b'{"timestamp":"x","type":"event_msg","payload":{"type":"token_count","rate_limits":{')
        self.assertEqual(33.0, quota_observe.read_codex(self.home)["windows"][0]["used_percent"])

    def test_incompatible_format_is_absence_not_zero(self):
        broken = event(NOW - 60)
        broken["payload"]["rate_limits"]["primary"]["used_percent"] = "76%"
        broken["payload"]["rate_limits"]["secondary"] = None
        self.rollout("rollout-a.jsonl", [broken, {"type": "event_msg", "payload": {"type": "token_count",
                                                                                      "rate_limits": None}}])
        self.assertIsNone(quota_observe.read_codex(self.home))
        self.assertIsNone(quota_observe.read_codex(self.home / "missing"))

    def test_only_tail_is_read(self):
        old = json.dumps(event(NOW - 60, primary=99.0)).encode() + b"\n"
        filler = b'{"type":"response_item","payload":"' + b"x" * (quota_observe.TAIL_BYTES + 10) + b'"}\n'
        (self.day / "rollout-big.jsonl").write_bytes(old + filler)
        self.assertIsNone(quota_observe.read_codex(self.home))


class ClassifyTests(unittest.TestCase):
    def test_fresh_reading_below_threshold_is_available_until_ttl(self):
        result = quota_observe.classify(observation(NOW - 60), NOW)
        self.assertEqual("available", result["availability"])
        self.assertEqual(NOW - 60 + quota_observe.FRESH_SECONDS, result["expires_at"])
        self.assertEqual(quota_observe.EVIDENCE, result["evidence"])

    def test_stale_reading_never_vouches_for_capacity(self):
        self.assertIsNone(quota_observe.classify(observation(NOW - 86400 + 3600 * 20), NOW))

    def test_stale_restriction_holds_until_its_own_window_resets(self):
        stale = observation(NOW - 7200, secondary=92.0)
        result = quota_observe.classify(stale, NOW)
        self.assertEqual("constrained", result["availability"])
        self.assertEqual(NOW + 86400, result["expires_at"])
        self.assertIsNone(quota_observe.classify(stale, NOW + 86400))

    def test_windows_expire_independently(self):
        reading = observation(NOW - 60, primary=100.0, secondary=95.0,
                              primary_reset=NOW + 600, secondary_reset=NOW + 86400)
        self.assertEqual("blocked", quota_observe.classify(reading, NOW)["availability"])
        self.assertEqual(NOW + 600, quota_observe.classify(reading, NOW)["expires_at"])
        after = quota_observe.classify(reading, NOW + 601)
        self.assertEqual("constrained", after["availability"])

    def test_high_usage_is_only_constrained_and_pacing_is_informative(self):
        reading = observation(NOW - 60, primary=97.0, primary_reset=NOW + 3 * 3600)
        self.assertEqual("constrained", quota_observe.classify(reading, NOW)["availability"])
        rows = quota_observe.pacing(reading, NOW)
        self.assertEqual(40.0, rows[0]["elapsed_percent"])
        self.assertEqual(57.0, rows[0]["delta_points"])
        ahead = observation(NOW - 60, primary=76.0, primary_reset=NOW + 6480)
        self.assertEqual("available", quota_observe.classify(ahead, NOW)["availability"])

    def test_malformed_or_future_observation_is_none(self):
        for value in (None, {}, {"measured_at": NOW, "windows": "x"}, observation(NOW + 3600),
                      {"measured_at": NOW, "windows": [{"used_percent": float("nan"), "resets_at": NOW + 5}]}):
            self.assertIsNone(quota_observe.classify(value, NOW))

    def test_routing_records_observed_evidence(self):
        profile = adapters.resolve_profile(explicit="sol")
        quota = quota_observe.classify(observation(NOW - 60, secondary=93.0), NOW)
        decision = routing.decide(profile, "draft", benefit="draft", independent=True, quota=quota, now=NOW)
        self.assertEqual("local", decision["action"])
        self.assertEqual("preserve_constrained_provider_quota", decision["reason"])
        self.assertEqual(quota_observe.EVIDENCE, decision["quota_evidence"])
        decision = routing.decide(profile, "review", benefit="critique", critical=True, quota=quota, now=NOW)
        self.assertEqual("delegate", decision["action"])


if __name__ == "__main__":
    unittest.main()
