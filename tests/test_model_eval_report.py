"""Adversarial reporting tests using synthetic observations, never model calls."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "model_eval_report", ROOT / "payload/harness/scripts/thinker_model_eval/report.py")
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def fixture(case_count=3, repeats=1, profile_ids=("alpha", "beta"), families=("analysis",)):
    cases = [{"id": f"{family}-{index}", "family": family, "split": "development", "max_words": 450}
             for family in families for index in range(case_count)]
    manifest = {"id": "synthetic", "created_at": "2026-01-01T00:00:00Z",
                "mode": "candidate", "repeats": repeats, "quality_floor": 3,
                "minimum_trials": 3,
                "comparison_policy": {"quality_margin": 0, "execution_seconds_margin": 2},
                "profiles": [{"id": pid, "model": f"requested-{pid}", "provider": "synthetic", "effort": "high"}
                             for pid in profile_ids], "cases": cases}
    trials, grades, audits = [], [], []
    for profile in manifest["profiles"]:
        for case in cases:
            for repeat in range(1, repeats + 1):
                trial_id = f"{profile['id']}.{case['id']}.{repeat}"
                trials.append({"id": trial_id, "blind_id": f"blind-{len(trials)}",
                               "case_id": case["id"], "family": case["family"],
                               "profile_id": profile["id"], "repeat": repeat,
                               "status": "completed", "response": "Synthetic response",
                               "execution_seconds": 10, "queue_seconds": 0,
                               "cost_estimate": None, "model_reported": None,
                               "checks": {"nonempty": True, "word_limit": True},
                               "trajectory": {"status": "unknown", "violations": []}})
                grades.append({"trial_id": trial_id, "evaluator": "synthetic-reviewer",
                               "quality": 3, "critical_failures": [],
                               "notes": "Fixture only", "evidence": ["Synthetic response"]})
                audits.append({"trial_id": trial_id, "evaluator": "audit-reviewer",
                               "status": "pass", "violations": [], "notes": "Fixture only"})
    return manifest, trials, grades, [], audits


class ModelEvalReportTests(unittest.TestCase):
    def report(self, data):
        return REPORT.build_report(*data)

    def family(self, report, index=0, family_index=0):
        return report["profiles"][index]["families"][family_index]

    def test_complete_ties_preserved_with_no_global_winner(self):
        report = self.report(fixture())
        self.assertEqual("provisional", self.family(report)["status"])
        self.assertEqual("observed_pass", self.family(report)["technical_status"])
        self.assertTrue(self.family(report)["quality"]["zero_critical_failures_confirmed"])
        comparison = report["family_comparisons"][0]
        self.assertEqual("descriptive", comparison["status"])
        self.assertEqual(["alpha", "beta"], comparison["pareto"]["profile_ids"])
        self.assertEqual([["alpha", "beta"]], comparison["pareto"]["ties"])
        self.assertIsNone(report["recommendation"]["general_winner"])
        self.assertFalse(report["recommendation"]["defaults_changed"])
        json.dumps(report, allow_nan=False)

    def test_planned_denominator_does_not_shrink_for_missing_trials(self):
        data = fixture()
        missing = data[1].pop()
        data[2][:] = [g for g in data[2] if g["trial_id"] != missing["id"]]
        data[4][:] = [a for a in data[4] if a["trial_id"] != missing["id"]]
        report = self.report(data)
        family = self.family(report, 1)
        self.assertEqual({"planned": 3, "recorded": 2, "completed": 2, "graded": 2,
                          "missing": 1, "pending": 0, "errors": 0}, family["counts"])
        self.assertEqual(2 / 3, family["coverage"]["completion"]["fraction"])
        self.assertEqual(6, report["counts"]["planned"])
        self.assertEqual("inconclusive", family["status"])
        self.assertTrue(report["family_comparisons"][0]["complete_compared_coverage"])
        self.assertFalse(report["family_comparisons"][0]["complete_inventory_coverage"])
        self.assertEqual([], report["family_comparisons"][0]["pareto"]["profile_ids"])

    def test_two_cases_many_repeats_remain_provisional(self):
        report = self.report(fixture(case_count=2, repeats=5))
        family = self.family(report)
        self.assertEqual(10, family["counts"]["planned"])
        self.assertEqual(2, family["independent_cases"])
        self.assertEqual("provisional", family["status"])
        self.assertEqual("candidate_for_human_validation", family["guidance"]["action"])
        self.assertFalse(family["qualification"]["case_count_alone_qualifies"])
        self.assertEqual(["alpha", "beta"], report["family_comparisons"][0]["pareto"]["profile_ids"])

    def test_missing_grades_do_not_confirm_zero_critical_failures(self):
        data = fixture()
        data[2].pop(0)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertEqual(1, family["quality"]["critical_unknown_trials"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])
        self.assertEqual(2, family["counts"]["graded"])

    def test_critical_failure_blocks_despite_high_quality_and_other_evaluator(self):
        data = fixture()
        data[2][0]["critical_failures"] = ["Unsupported source claim"]
        data[2][0]["quality"] = 4
        alternative = copy.deepcopy(data[2][0])
        alternative.update(evaluator="other", critical_failures=[])
        data[2].append(alternative)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertIn("adjudication_required", family["unknown"])
        self.assertEqual(0, family["quality"]["critical_failed_trials"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])
        self.assertEqual(3, family["counts"]["graded"])

    def test_disagreeing_quality_requires_adjudication_not_minimum(self):
        data = fixture()
        alternative = copy.deepcopy(data[2][0])
        alternative.update(evaluator="other", quality=2)
        data[2].append(alternative)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertEqual({"3": 2}, family["quality"]["distribution"])
        self.assertEqual(0, family["quality"]["below_floor_trials"])
        self.assertEqual(1, family["quality"]["disagreement_trials"])

    def test_no_independent_audit_remains_unknown_even_embedded_pass(self):
        data = fixture()
        for trial in data[1]:
            trial["trajectory"]["status"] = "pass"
        data = (*data[:4], None)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertEqual({"pass": 0, "fail": 0, "unknown": 3,
                          "independent_audit_required": True}, family["trajectory"])

    def test_any_failed_or_violating_trajectory_blocks(self):
        for embedded in (False, True):
            with self.subTest(embedded=embedded):
                data = fixture()
                target = data[1][0]["trajectory"] if embedded else data[4][0]
                target.update(status="pass", violations=["Unapproved action"])
                family = self.family(self.report(data))
                self.assertEqual("blocked", family["status"])
                self.assertIn("failed_trajectory", family["blockers"])

    def test_disagreeing_auditors_do_not_become_majority_pass(self):
        data = fixture()
        alternative = copy.deepcopy(data[4][0])
        alternative.update(evaluator="other", status="fail")
        data[4].append(alternative)
        self.assertEqual("inconclusive", self.family(self.report(data))["status"])

    def test_failed_check_blocks_only_a_completed_response(self):
        data = fixture()
        data[0]["cases"][0]["word_limit_hard"] = True
        data[1][0]["checks"]["word_limit"] = False
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertEqual(1, family["checks"]["failed_trials"])
        data[1][0]["status"] = "planned"
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertNotIn("failed_checks", family["blockers"])
        self.assertEqual(1, family["counts"]["pending"])

    def test_persisted_pass_checks_cannot_hide_missing_or_blank_response(self):
        for response in (None, "", "  \n\t", 42):
            with self.subTest(response=response):
                data = fixture()
                data[1][0]["response"] = response
                family = self.family(self.report(data))
                self.assertEqual("blocked", family["status"])
                self.assertIn("empty_output", family["blockers"])
                self.assertFalse(family["trials"][0]["response_checks"]["nonempty"])

    def test_word_limit_recomputed_from_frozen_case(self):
        data = fixture()
        data[0]["cases"][0]["max_words"] = 1
        data[0]["cases"][0]["word_limit_hard"] = True
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertFalse(family["trials"][0]["response_checks"]["word_limit"])

    def test_unresolved_transport_error_is_unknown_not_semantic_failure_or_success(self):
        for error_kind in ("collection_error", "submission_error"):
            with self.subTest(error_kind=error_kind):
                data = fixture()
                data[1][0][error_kind] = "Malformed transport result"
                data[1][0]["response"] = None
                data[2][0]["quality"] = 1
                data[2][0]["critical_failures"] = ["Untrusted old grade"]
                report = self.report(data)
                family = self.family(report)
                self.assertEqual("inconclusive", family["status"])
                self.assertIn("unresolved_transport_errors", family["unknown"])
                self.assertEqual([], family["blockers"])
                self.assertEqual(2, family["counts"]["completed"])
                self.assertEqual(2, family["counts"]["graded"])
                self.assertEqual(0, family["counts"]["errors"])
                self.assertEqual(1, family["counts"]["pending"])
                self.assertEqual(0, family["quality"]["critical_failed_trials"])
                self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])
                self.assertEqual(1, family["trajectory"]["unknown"])
                self.assertIn("excluídas das métricas", REPORT.render_markdown(report))

    def test_terminal_failure_remains_execution_error_separate_from_semantic_quality(self):
        data = fixture()
        data[1][0].update(status="failed", collection_error="Unresolved result", response=None)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertEqual(1, family["counts"]["errors"])
        self.assertEqual([], family["blockers"])
        self.assertFalse(family["operational"]["capacity_inferred_from_operational_failure"])

    def test_error_count_and_incomplete_family_block_general_recommendation(self):
        data = fixture(families=("analysis", "code"))
        data[1][0]["status"] = "timed_out"
        report = self.report(data)
        self.assertEqual(1, report["counts"]["errors"])
        self.assertEqual("inconclusive", self.family(report)["status"])
        self.assertEqual("provisional", self.family(report, family_index=1)["status"])
        self.assertEqual("provisional_observed_evidence", report["recommendation"]["status"])

    def test_missing_checks_inconclusive(self):
        data = fixture()
        data[1][0]["checks"].pop("word_limit")
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertIn("unknown_checks", family["unknown"])

    def test_absent_human_feedback_and_cost_not_inferred(self):
        report = self.report(fixture())
        family = self.family(report)
        self.assertEqual("unknown", family["human_feedback"]["status"])
        self.assertEqual({}, family["human_feedback"]["preferences"])
        self.assertIsNone(family["human_feedback"]["review_minutes"]["median"])
        self.assertEqual([], family["efficiency"]["cost_estimates"]["groups"])
        self.assertFalse(family["efficiency"]["tokens_aggregated"])
        self.assertEqual("not inferred from requested profile", report["profiles"][0]["confirmed_model_identity"])

    def test_human_feedback_separate_from_grades_and_preferences(self):
        data = fixture()
        data[3].append({"trial_id": data[1][0]["id"], "reviewer": "human",
                        "preference": "reject", "review_minutes": None,
                        "corrections": None, "notes": "Fixture only"})
        family = self.family(self.report(data))
        self.assertEqual("provisional", family["status"])
        self.assertEqual("review", family["guidance"]["action"])
        self.assertEqual({"reject": 1}, family["human_feedback"]["preferences"])
        self.assertEqual(1 / 3, family["human_feedback"]["coverage"]["fraction"])
        self.assertIsNone(family["human_feedback"]["corrections"]["median"])

    def test_cost_groups_require_complete_provenance_and_preserve_provider_currency(self):
        data = fixture()
        for trial in data[1]:
            trial["cost_estimate"] = {"provider": "synthetic", "currency": "USD",
                                      "provenance": "manual estimate", "amount": 0.2}
        data[1][0]["cost_estimate"].update(provider="other", currency="EUR")
        family = self.family(self.report(data))
        groups = family["efficiency"]["cost_estimates"]["groups"]
        self.assertEqual(2, len(groups))
        self.assertEqual({("other", "EUR"), ("synthetic", "USD")},
                         {(g["provider"], g["currency"]) for g in groups})
        self.assertEqual([0.2, 0.4], sorted(g["total"] for g in groups))
        data[1][0]["cost_estimate"].pop("provenance")
        costs = self.family(self.report(data))["efficiency"]["cost_estimates"]
        self.assertFalse(costs["coverage"]["complete"])
        self.assertEqual([], costs["groups"])

    def test_unknown_or_invalid_execution_timing_blocks_pareto_only(self):
        for invalid in (None, True, float("nan"), float("inf"), -1, 10 ** 1000):
            with self.subTest(invalid=invalid):
                data = fixture()
                data[1][0]["execution_seconds"] = invalid
                report = self.report(data)
                family = self.family(report)
                self.assertEqual("provisional", family["status"])
                self.assertEqual([], report["family_comparisons"][0]["pareto"]["profile_ids"])
                json.dumps(report, allow_nan=False)

    def test_finite_large_metrics_never_emit_infinity(self):
        data = fixture(case_count=4)
        for trial in data[1]:
            trial["execution_seconds"] = 1e308
            trial["cost_estimate"] = {"provider": "synthetic", "currency": "USD",
                                      "provenance": "synthetic stress test", "amount": 1e308}
        report = self.report(data)
        family = self.family(report)
        self.assertEqual(1e308, family["efficiency"]["execution_seconds"]["median"])
        self.assertIsNone(family["efficiency"]["cost_estimates"]["groups"][0]["total"])
        json.dumps(report, allow_nan=False)
        self.assertNotIn("infinity", REPORT.render_markdown(report))

    def test_pareto_preserves_tradeoff_and_dominates_only_strictly(self):
        data = fixture(profile_ids=("alpha", "beta", "gamma"))
        for trial in data[1]:
            trial["execution_seconds"] = {"alpha": 5, "beta": 10, "gamma": 20}[trial["profile_id"]]
        for grade in data[2]:
            if grade["trial_id"].startswith("beta."):
                grade["quality"] = 4
        front = self.report(data)["family_comparisons"][0]["pareto"]["profile_ids"]
        self.assertEqual(["alpha", "beta"], front)

    def test_minimum_cannot_be_lowered_by_repeat_threshold(self):
        data = fixture(case_count=2)
        data[0]["minimum_trials"] = 1
        self.assertEqual("provisional", self.family(self.report(data))["status"])

    def test_no_observations_still_show_whole_plan(self):
        manifest = fixture()[0]
        report = REPORT.build_report(manifest, [], [], [])
        self.assertEqual(6, report["counts"]["planned"])
        self.assertEqual(6, report["counts"]["missing"])
        family = self.family(report)
        self.assertIsNone(family["quality"]["median"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])
        self.assertEqual("inconclusive", family["guidance"]["action"])

    def test_identity_errors_rejected_instead_of_double_counted(self):
        for mutation in ("duplicate_trial", "unknown_case", "duplicate_grade", "unknown_grade", "wrong_family", "zero_repeat"):
            with self.subTest(mutation=mutation):
                data = fixture()
                if mutation == "duplicate_trial":
                    data[1].append(copy.deepcopy(data[1][0]))
                elif mutation == "unknown_case":
                    data[1][0]["case_id"] = "not-planned"
                elif mutation == "duplicate_grade":
                    data[2].append(copy.deepcopy(data[2][0]))
                elif mutation == "unknown_grade":
                    data[2][0]["trial_id"] = "not-recorded"
                elif mutation == "wrong_family":
                    data[1][0]["family"] = "other"
                else:
                    data[1][0]["repeat"] = 0
                with self.assertRaises(ValueError):
                    self.report(data)

    def test_inputs_not_mutated_and_markdown_discloses_limits(self):
        data = fixture(case_count=2)
        original = copy.deepcopy(data)
        report = self.report(data)
        self.assertEqual(original, data)
        text = REPORT.render_markdown(report)
        for phrase in ("provisória", "Nenhuma contagem", "Retorno humano: desconhecido", "Estimativas de custo: desconhecidas ou parciais",
                       "Agregação geral indisponível", "Dados necessários", "Padrões alterados: não"):
            self.assertIn(phrase, text)
        self.assertIn("Evidências: Synthetic response", text)

    def test_reported_model_labels_preserved_without_requested_identity_inference(self):
        data = fixture()
        data[1][0]["model_reported"] = "served-alpha"
        data[1][1]["model_reported"] = "served-other"
        report = self.report(data)
        reported = report["profiles"][0]["model_reported"]
        self.assertEqual(["served-alpha", "served-other"], reported["labels"])
        self.assertEqual(2 / 3, reported["coverage"]["fraction"])
        self.assertEqual("unknown", report["profiles"][1]["model_reported"]["status"])
        text = REPORT.render_markdown(report)
        self.assertIn("modelo requested-alpha; provedor synthetic; esforço high", text)
        self.assertIn("served-alpha, served-other", text)
        self.assertIn("sem verificação independente", text)

    def test_failed_trajectory_is_fully_observed_but_ineligible(self):
        data = fixture()
        data[4][0]["status"] = "fail"
        comparison = self.report(data)["family_comparisons"][0]
        self.assertTrue(comparison["complete_inventory_coverage"])
        self.assertEqual("inconclusive_or_provisional", comparison["status"])
        self.assertEqual([], comparison["pareto"]["profile_ids"])

    def test_semantic_rationale_survives_json_and_markdown(self):
        data = fixture()
        data[2][0].update(notes="The case requires evidence separation", evidence=["fixed-source line 2"],
                          critical_failures=["Invented causal claim"])
        report = self.report(data)
        actual = self.family(report)["trials"][0]["grades"][0]
        self.assertEqual(data[2][0], {key: value for key, value in actual.items() if key != "id"})
        text = REPORT.render_markdown(report)
        for phrase in ("The case requires evidence separation", "fixed-source line 2", "Invented causal claim", "synthetic-reviewer"):
            self.assertIn(phrase, text)

    def test_markdown_escapes_table_cells(self):
        data = fixture()
        old_id = data[0]["profiles"][0]["id"]
        data[0]["profiles"][0]["id"] = "alpha|injected\nrow"
        for trial in data[1]:
            if trial["profile_id"] == old_id:
                trial["profile_id"] = "alpha|injected\nrow"
        text = REPORT.render_markdown(self.report(data))
        self.assertIn("alpha\\|injected row", text)

    def test_unavailable_inventory_member_does_not_stop_observed_pair(self):
        data = fixture(profile_ids=("alpha", "beta", "unavailable"))
        for trial in data[1]:
            if trial["profile_id"] == "unavailable":
                trial.update(status="unavailable", failure_kind="unavailable", response=None,
                             execution_seconds=None, checks={"nonempty": False, "word_limit": False})
        report = self.report(data)
        comparison = report["family_comparisons"][0]
        self.assertEqual(["alpha", "beta"], comparison["eligible_profile_ids"])
        self.assertEqual(["alpha", "beta"], comparison["pareto"]["profile_ids"])
        self.assertEqual("unavailable", comparison["exclusions"][0]["profile_id"])
        self.assertFalse(comparison["complete_inventory_coverage"])
        unavailable = self.family(report, 2)
        self.assertEqual("inconclusive", unavailable["status"])
        self.assertIsNone(unavailable["quality"]["median"])
        self.assertEqual({"unavailable": 3}, unavailable["operational"]["failure_types"])

    def test_no_predeclared_margins_means_no_pareto_dominance(self):
        data = fixture()
        data[0].pop("comparison_policy")
        data[1][0]["execution_seconds"] = 1
        comparison = self.report(data)["family_comparisons"][0]
        self.assertEqual("descriptive", comparison["status"])
        self.assertEqual([], comparison["pareto"]["profile_ids"])
        self.assertIsNone(comparison["pairs"][0]["descriptive_dominant_profile"])
        self.assertFalse(comparison["practical_margins"]["predeclared"])

    def test_tiny_timing_difference_is_practical_tie(self):
        data = fixture()
        for trial in data[1]:
            if trial["profile_id"] == "alpha":
                trial["execution_seconds"] = 9
        comparison = self.report(data)["family_comparisons"][0]
        self.assertEqual(["alpha", "beta"], comparison["pareto"]["profile_ids"])
        self.assertEqual([["alpha", "beta"]], comparison["pareto"]["ties"])

    def test_one_case_even_many_repeats_never_yields_pareto_dominance(self):
        data = fixture(case_count=1, repeats=8)
        for trial in data[1]:
            if trial["profile_id"] == "alpha":
                trial["execution_seconds"] = 1
        comparison = self.report(data)["family_comparisons"][0]
        self.assertEqual(1, comparison["pairs"][0]["independent_paired_cases"])
        self.assertIsNone(comparison["pairs"][0]["descriptive_dominant_profile"])
        self.assertEqual([], comparison["pareto"]["profile_ids"])

    def test_case_tradeoff_not_hidden_by_faster_global_median(self):
        data = fixture()
        for trial in data[1]:
            if trial["profile_id"] == "alpha":
                trial["execution_seconds"] = 1 if trial["case_id"] != "analysis-2" else 30
        comparison = self.report(data)["family_comparisons"][0]
        self.assertEqual(["alpha", "beta"], comparison["pareto"]["profile_ids"])
        pair = comparison["pairs"][0]
        self.assertEqual([9, 9, -20], [case["execution_seconds_advantage_a"]["median"] for case in pair["cases"]])
        self.assertIsNone(pair["descriptive_dominant_profile"])

    def test_explicit_deadline_blocks_operational_fit_without_capability_zero(self):
        data = fixture()
        data[0].update(deadline_seconds=15, timeout=20)
        data[1][0].update(status="timed_out", response=None, execution_seconds=20)
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertEqual(["deadline_unmet"], family["blockers"])
        self.assertEqual({"3": 2}, family["quality"]["distribution"])
        self.assertEqual(0, family["quality"]["below_floor_trials"])

    def test_timeout_before_declared_deadline_does_not_prove_deadline_failure(self):
        data = fixture()
        data[0].update(deadline_seconds=60, timeout=20)
        data[1][0].update(status="timed_out", response=None, execution_seconds=20)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertNotIn("deadline_unmet", family["blockers"])

    def test_revised_assessment_replaces_old_grade_preserving_history(self):
        data = fixture()
        original = data[2][0]
        original.update(quality=1, critical_failures=["Old disputed failure"])
        revision = copy.deepcopy(original)
        revision.update(id="revision-one", supersedes=REPORT.legacy_grade_id(original["trial_id"], original["evaluator"]),
                        quality=3, critical_failures=[], notes="Explicit correction")
        data[2].append(revision)
        report = self.report(data)
        family = self.family(report)
        self.assertEqual("observed_pass", family["technical_status"])
        self.assertEqual({"3": 3}, family["quality"]["distribution"])
        judgment = family["trials"][0]["judgment"]
        self.assertEqual(["revision-one"], judgment["active_ids"])
        self.assertEqual([revision["supersedes"]], judgment["superseded_ids"])
        self.assertEqual(2, len(family["trials"][0]["grades"]))
        text = REPORT.render_markdown(report)
        self.assertIn("substituída", text)
        self.assertIn("Explicit correction", text)

    def test_revision_cannot_change_evaluator_or_replace_stale_revision(self):
        for bad in ("evaluator", "stale", "unknown"):
            with self.subTest(bad=bad):
                data = fixture()
                original = data[2][0]
                revision = copy.deepcopy(original)
                revision.update(id="revision-one", supersedes=REPORT.legacy_grade_id(original["trial_id"], original["evaluator"]))
                if bad == "evaluator":
                    revision["evaluator"] = "pretend-new-judge"
                elif bad == "unknown":
                    revision["supersedes"] = "missing"
                else:
                    data[2].append(revision)
                    revision = copy.deepcopy(revision)
                    revision["id"] = "revision-two"
                data[2].append(revision)
                with self.assertRaises(ValueError):
                    self.report(data)

    def test_criteria_disagreement_remains_unknown_not_verified_critical_failure(self):
        data = fixture()
        data[0]["cases"][0]["criteria_metadata"] = [{"id": "c1", "critical": True, "severity": "critical", "dimension": "factual"}]
        original = data[2][0]
        original["criteria"] = [{"id": "c1", "status": "pass", "evidence": ["Synthetic response"]}]
        second = copy.deepcopy(original)
        second.update(evaluator="second-judge")
        second["criteria"][0]["status"] = "fail"
        data[2].append(second)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertEqual(0, family["quality"]["critical_failed_trials"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])

    def test_missing_literal_criterion_evidence_does_not_pass(self):
        for evidence in ([], ["invented quotation"]):
            with self.subTest(evidence=evidence):
                data = fixture()
                data[0]["cases"][0]["criteria_metadata"] = [{"id": "c1", "critical": True, "severity": "critical"}]
                data[2][0]["criteria"] = [{"id": "c1", "status": "pass", "evidence": evidence}]
                family = self.family(self.report(data))
                self.assertEqual("inconclusive", family["status"])
                self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])

    def test_unanimous_critical_criterion_failure_blocks_despite_score_disagreement(self):
        data = fixture()
        data[0]["cases"][0]["criteria_metadata"] = [{"id": "c1", "critical": True, "severity": "critical"}]
        data[2][0]["criteria"] = [{"id": "c1", "status": "fail", "evidence": ["Synthetic response"]}]
        second = copy.deepcopy(data[2][0])
        second.update(evaluator="second-judge", quality=4)
        data[2].append(second)
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertEqual(1, family["quality"]["critical_failed_trials"])

    def test_minor_word_overrun_is_format_warning_not_critical_failure(self):
        data = fixture()
        data[0]["cases"][0]["max_words"] = 1
        family = self.family(self.report(data))
        self.assertEqual("provisional", family["status"])
        self.assertIn("format_limit_exceeded", family["warnings"])
        self.assertEqual(0, family["quality"]["critical_failed_trials"])
        self.assertEqual("review", family["guidance"]["action"])

    def test_preference_use_is_not_acceptance_or_total_effort(self):
        data = fixture()
        for trial in data[1]:
            data[3].append({"trial_id": trial["id"], "reviewer": "human", "preference": "use",
                            "review_minutes": 2, "corrections": 0, "notes": "Fixture only"})
        family = self.family(self.report(data))
        self.assertEqual("candidate_for_human_validation", family["guidance"]["action"])
        self.assertEqual("unknown", family["human_feedback"]["personal_recommendation_status"])
        self.assertIsNone(family["human_feedback"]["total_minutes"]["median"])
        self.assertEqual(0, family["human_feedback"]["accepted_coverage"]["observed"])

    def test_explicit_accepted_total_effort_supports_only_observed_personal_scope(self):
        data = fixture()
        for trial in data[1]:
            data[3].append({"trial_id": trial["id"], "reviewer": "human", "preference": "use",
                            "acceptance": "accepted", "review_minutes": 2, "preparation_minutes": 1,
                            "integration_minutes": 3, "accepted_delivery_minutes": 12,
                            "total_minutes": 9, "corrections": 0, "notes": "Fixture only"})
        report = self.report(data)
        family = self.family(report)
        self.assertEqual("use_observed_scope", family["guidance"]["action"])
        self.assertEqual("provisional", family["status"])
        self.assertEqual(9, family["human_feedback"]["total_minutes"]["median"])
        self.assertEqual(12, family["human_feedback"]["accepted_delivery_minutes"]["median"])
        self.assertIsNone(report["recommendation"]["general_winner"])

    def test_reliability_counts_attempts_and_cases_without_inventing_significance(self):
        data = fixture(repeats=2)
        data[2][0]["quality"] = 1
        report = self.report(data)
        reliability = self.family(report)["reliability"]
        self.assertEqual((5, 1, 0), (reliability["successes"], reliability["failures"], reliability["unknown"]))
        first_case = reliability["cases"][0]
        self.assertEqual(2, first_case["planned_attempts"])
        self.assertEqual(0.5, first_case["success_fraction_of_planned"])
        self.assertEqual(1, first_case["variability"]["quality"]["minimum"])
        self.assertEqual(3, first_case["variability"]["quality"]["maximum"])
        self.assertIn("no statistical significance", first_case["variability"]["quality"]["uncertainty"])

    def test_pairwise_human_preference_kept_separate_from_pareto(self):
        data = fixture()
        pairwise = [{"id": "pair-one", "reviewer": "human", "case_id": "analysis-0",
                     "profile_a": "alpha", "profile_b": "beta", "preference": "profile_b",
                     "notes": "Human fixture", "review_minutes": 3}]
        report = REPORT.build_report(*data, pairwise_feedback=pairwise)
        pair = report["family_comparisons"][0]["pairs"][0]
        self.assertEqual(pairwise, pair["human_pairwise_feedback"])
        self.assertEqual(["alpha", "beta"], report["family_comparisons"][0]["pareto"]["profile_ids"])
        self.assertEqual("unknown", self.family(report)["human_feedback"]["status"])

    def test_workflow_final_state_without_text_has_unknown_semantics_not_empty_failure(self):
        data = fixture()
        data[0]["cases"][0].update(execution_mode="host-managed", workflow="workflows/fixture.json")
        data[1][0].update(host_result=True, response=None,
                           artifacts=[{"path": "outputs/fixture.txt", "sha256": "a" * 64, "bytes": 5}],
                           final_state_checks={"status": "pass", "checks": [{"id": "file", "status": "pass"}]})
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertNotIn("empty_output", family["blockers"])
        self.assertEqual("pass", family["trials"][0]["workflow_final_state"]["status"])
        data[1][0]["final_state_checks"]["status"] = "fail"
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertIn("observed_workflow_failure", family["blockers"])

    def workflow_with_literal_artifact(self):
        data = fixture()
        text = "Delivered artifact contains the observed result."
        content = text.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        data[0]["cases"][0].update(execution_mode="host-managed", workflow="workflows/fixture.json",
                                   criteria_metadata=[{"id": "c1", "critical": True, "severity": "critical"}])
        data[1][0].update(host_result=True, response=None,
                          artifacts=[{"path": "workflow-artifacts/fixture/output.txt", "sha256": digest, "bytes": len(content)}],
                          artifact_texts=[{"name": "output.txt", "text": text, "sha256": digest, "limitations": []}],
                          final_state_checks={"status": "pass", "checks": [{"id": "file", "status": "pass"}]})
        data[2][0]["criteria"] = [{"id": "c1", "status": "pass", "evidence": ["observed result"]}]
        return data

    def test_literal_artifact_grading_passes_without_fake_response(self):
        report = self.report(self.workflow_with_literal_artifact())
        family = self.family(report)
        self.assertEqual("observed_pass", family["technical_status"])
        self.assertEqual("provisional", family["status"])
        self.assertTrue(family["trials"][0]["artifact_text_sources"][0]["literal_text_observed"])
        self.assertNotIn("empty_output", family["blockers"])
        self.assertIn("observed result", REPORT.render_markdown(report))

    def test_mismatching_artifact_text_hash_cannot_justify_criteria(self):
        data = self.workflow_with_literal_artifact()
        data[1][0]["artifact_texts"][0]["text"] += " changed"
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertFalse(family["trials"][0]["artifact_text_sources"][0]["literal_text_observed"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])

    def test_literal_quote_cannot_cross_artifact_boundaries(self):
        data = self.workflow_with_literal_artifact()
        data[1][0]["artifact_texts"], data[1][0]["artifacts"] = [], []
        for index, text in enumerate(("first", "second")):
            digest = hashlib.sha256(text.encode()).hexdigest()
            data[1][0]["artifact_texts"].append({"name": str(index), "text": text, "sha256": digest, "limitations": []})
            data[1][0]["artifacts"].append({"path": str(index), "bytes": len(text.encode()), "sha256": digest})
        data[2][0]["criteria"][0]["evidence"] = ["firstsecond"]
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])

    def weighted_personal_fixture(self):
        data = fixture(families=("analysis", "code"))
        data[0]["action_weights"] = {"analysis": 3, "code": 1}
        data[0]["comparison_policy"]["personal_time_margin_minutes"] = 1
        for trial in data[1]:
            time = {("alpha", "analysis"): 4, ("alpha", "code"): 20,
                    ("beta", "analysis"): 10, ("beta", "code"): 4}[(trial["profile_id"], trial["family"])]
            data[3].append({"trial_id": trial["id"], "reviewer": "human", "preference": "use",
                            "acceptance": "accepted", "total_minutes": time,
                            "review_minutes": None, "corrections": None, "notes": "Fixture only"})
        return data

    def test_weighted_personal_projection_uses_only_complete_total_human_effort(self):
        data = self.weighted_personal_fixture()
        data[0]["comparison_policy"]["personal_time_margin_minutes"] = .1
        data[1][0]["execution_seconds"] = 1000000  # Model latency is a separate dimension.
        report = self.report(data)
        aggregate = report["recommendation"]
        self.assertEqual("provisional_contextual_recommendation", aggregate["aggregate_status"])
        self.assertEqual("alpha", aggregate["general_winner"])
        self.assertEqual({"analysis": .75, "code": .25}, aggregate["normalized_action_weights"])
        self.assertEqual({"alpha": 8, "beta": 8.5},
                         {c["profile_id"]: c["weighted_mean_total_human_minutes"] for c in aggregate["candidates"]})

    def test_zero_action_weights_do_not_create_general_recommendation(self):
        data = self.weighted_personal_fixture()
        data[0]["action_weights"] = {"analysis": 0, "code": 0}
        aggregate = self.report(data)["recommendation"]
        self.assertIsNone(aggregate["general_winner"])
        self.assertEqual("unavailable_missing_action_weights", aggregate["aggregate_status"])

    def test_missing_personal_data_blocks_general_projection_without_imputation(self):
        data = self.weighted_personal_fixture()
        data[3][0].pop("total_minutes")
        aggregate = self.report(data)["recommendation"]
        self.assertIsNone(aggregate["general_winner"])
        self.assertEqual("unavailable_insufficient_comparable_personal_feedback", aggregate["aggregate_status"])
        self.assertEqual("alpha", aggregate["exclusions"][0]["profile_id"])

    def test_weighted_difference_within_personal_margin_remains_tie(self):
        data = self.weighted_personal_fixture()
        aggregate = self.report(data)["recommendation"]
        self.assertEqual("provisional_projection_practical_tie", aggregate["aggregate_status"])
        self.assertEqual(["alpha", "beta"], aggregate["practical_tie_profile_ids"])
        self.assertIsNone(aggregate["general_winner"])
        self.assertIn("empate prático", REPORT.render_markdown(self.report(data)))

    def test_all_active_authorship_conflicts_require_independent_review(self):
        data = fixture()
        for grade in data[2]:
            grade["conflict_of_authorship"] = True
        report = self.report(data)
        family = self.family(report)
        self.assertEqual("inconclusive", family["status"])
        self.assertIn("independent_review_required", family["unknown"])
        self.assertIsNone(family["quality"]["median"])
        self.assertFalse(family["quality"]["zero_critical_failures_confirmed"])
        self.assertIn("Revisão independente necessária", REPORT.render_markdown(report))

    def test_conflicted_and_declared_nonconflicted_agreement_keeps_history(self):
        data = fixture()
        data[2][0]["conflict_of_authorship"] = True
        second = copy.deepcopy(data[2][0])
        second.update(evaluator="independent-human", conflict_of_authorship=False,
                      evaluator_config={"kind": "human"})
        data[2].append(second)
        report = self.report(data)
        family = self.family(report)
        self.assertEqual("observed_pass", family["technical_status"])
        decision = family["trials"][0]["judgment"]
        self.assertEqual(2, len(decision["active_ids"]))
        self.assertFalse(decision["independence"]["independent_review_required"])
        self.assertEqual(1, len(decision["independence"]["declared_conflict_ids"]))

    def test_conflicted_and_nonconflicted_disagreement_remains_unresolved(self):
        data = fixture()
        data[2][0]["conflict_of_authorship"] = True
        second = copy.deepcopy(data[2][0])
        second.update(evaluator="independent-human", conflict_of_authorship=False, quality=4)
        data[2].append(second)
        family = self.family(self.report(data))
        self.assertEqual("inconclusive", family["status"])
        self.assertIn("adjudication_required", family["unknown"])

    def test_exact_requested_model_self_judge_flags_risk_not_confirmed_identity(self):
        data = fixture()
        data[2][0].update(conflict_of_authorship=False,
                          evaluator_config={"kind": "model", "model": "requested-alpha", "provider": "synthetic", "effort": "high"})
        report = self.report(data)
        family = self.family(report)
        self.assertEqual("inconclusive", family["status"])
        independence = family["trials"][0]["judgment"]["independence"]
        risk = independence["potential_self_judges"][0]
        self.assertEqual("requested_configuration", risk["source"])
        self.assertFalse(risk["served_identity_confirmed"])
        self.assertEqual(1, len(independence["declared_nonconflicted_ids"]))
        self.assertEqual([], independence["review_without_detected_conflict_ids"])

    def test_same_provider_different_model_is_not_self_judge(self):
        data = fixture()
        data[2][0].update(conflict_of_authorship=False,
                          evaluator_config={"kind": "model", "model": "different-model", "provider": "synthetic", "effort": "high"})
        family = self.family(self.report(data))
        self.assertEqual("observed_pass", family["technical_status"])
        self.assertEqual([], family["trials"][0]["judgment"]["independence"]["potential_self_judges"])

    def test_reported_model_overlap_records_emitted_label_provenance(self):
        data = fixture()
        data[1][0]["model_reported"] = "served-model"
        data[2][0].update(conflict_of_authorship=False,
                          evaluator_config={"kind": "model", "model": "served-model", "provider": "alias-provider", "effort": "high"})
        family = self.family(self.report(data))
        risk = family["trials"][0]["judgment"]["independence"]["potential_self_judges"][0]
        self.assertEqual("execution_reported_label", risk["source"])
        self.assertEqual("unknown_or_different_labels", risk["provider_relation"])
        self.assertFalse(risk["served_identity_confirmed"])

    def test_superseded_authorship_conflict_does_not_block_current_independent_review(self):
        data = fixture()
        data[2][0]["conflict_of_authorship"] = True
        revised = copy.deepcopy(data[2][0])
        revised.update(id="corrected-conflict", conflict_of_authorship=False,
                       supersedes=REPORT.legacy_grade_id(revised["trial_id"], revised["evaluator"]))
        data[2].append(revised)
        family = self.family(self.report(data))
        self.assertEqual("observed_pass", family["technical_status"])
        self.assertEqual([], family["trials"][0]["judgment"]["independence"]["declared_conflict_ids"])

    def test_one_character_literal_quote_is_not_arbitrarily_vetoed_or_called_proof(self):
        data = fixture()
        data[0]["cases"][0]["criteria_metadata"] = [{"id": "c1", "critical": True, "severity": "critical"}]
        data[2][0]["criteria"] = [{"id": "c1", "status": "pass", "evidence": ["S"]}]
        report = self.report(data)
        decision = self.family(report)["trials"][0]["judgment"]
        self.assertEqual("pass", decision["status"])
        self.assertTrue(decision["criteria"][0]["literal_anchoring_observed"])
        self.assertIsNone(decision["evidence_limits"]["minimum_quote_length"])
        self.assertIn("not established", decision["evidence_limits"]["semantic_entailment"])
        self.assertIn("Sozinha não comprova", REPORT.render_markdown(report))

    def test_failed_host_semantic_final_state_is_observed_not_infrastructure(self):
        data = fixture()
        data[0]["cases"][0].update(execution_mode="host-managed", workflow="workflows/fixture.json")
        data[1][0].update(host_result=True, status="failed", failure_kind="semantic", response=None,
                          final_state_checks={"status": "fail", "checks": [{"id": "expected-file", "status": "fail"}]})
        family = self.family(self.report(data))
        self.assertEqual("blocked", family["status"])
        self.assertIn("observed_workflow_failure", family["blockers"])
        self.assertNotIn("operational_failure", family["unknown"])
        self.assertNotIn("operational_outcome_unknown", family["unknown"])
        self.assertEqual("fail", family["trials"][0]["outcome"])
        self.assertEqual(1, family["reliability"]["failures"])


if __name__ == "__main__":
    unittest.main()
