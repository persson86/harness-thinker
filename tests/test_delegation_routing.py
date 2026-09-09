import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload/harness/scripts"))
from thinker_delegation import adapters, routing


class RoutingTests(unittest.TestCase):
    def test_local_is_baseline_even_with_explicit_model(self):
        for task in adapters.DEFAULT_ROUTES:
            selected = adapters.resolve_profile(task)
            self.assertEqual("local", routing.decide(selected, task)["action"])

    def test_same_model_is_not_a_reason_to_spawn(self):
        profile = adapters.resolve_profile(explicit="sol")
        host = routing.principal("codex", "sol", "high")
        decision = routing.decide(profile, "review", host=host, benefit="repeat reading")
        self.assertTrue(decision["same_model"])
        self.assertEqual("local", decision["action"])
        decision = routing.decide(profile, "review", host=host, benefit="audit distinct files", independent=True)
        self.assertEqual("delegate", decision["action"])
        self.assertEqual("declared_not_verified", decision["principal_identity"])

    def test_quota_is_explicit_provider_snapshot_and_expires(self):
        profile = adapters.resolve_profile(explicit="opus")
        args = dict(benefit="independent critique", critical=True, now=100)
        for availability, action in (("blocked", "blocked"), ("constrained", "delegate")):
            quota = dict(availability=availability, expires_at=101)
            decision = routing.decide(profile, "review", quota=quota, **args)
            self.assertEqual(action, decision["action"])
            quota["expires_at"] = 99
            self.assertEqual("unknown", routing.decide(profile, "review", quota=quota, **args)["quota"])

    def test_missing_identity_stays_unknown_and_partial_is_refused(self):
        self.assertIsNone(routing.principal(None, None, None))
        with self.assertRaises(adapters.AdapterError):
            routing.principal("codex", None, "high")

    def test_constrained_quota_preserved_for_noncritical_work(self):
        profile = adapters.resolve_profile(explicit="sonnet")
        result = routing.decide(profile, "draft", benefit="independent draft", independent=True,
                                quota=dict(availability="constrained", expires_at=101), now=100)
        self.assertEqual("local", result["action"])


if __name__ == "__main__":
    unittest.main()
