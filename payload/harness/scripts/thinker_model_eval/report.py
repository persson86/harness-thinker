"""Evidence-bounded reports for frozen personal model evaluations.

This module performs no filesystem or provider operations. Repeated outputs are
observations of one case, never additional independent cases. Qualification is
for the declared bounded text workload only, never for an end-to-end workflow.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    low, high = ordered[middle - 1], ordered[middle]
    # All metric values are nonnegative. Avoid overflowing (low + high) / 2.
    return low / 2 + high / 2 if low < 0 < high else low + (high - low) / 2


def _sum(values):
    result = sum(values)
    return result if _number(result) else None


_SUCCESS = {"completed"}
_ERROR = {"failed", "cancelled", "timed_out", "interrupted"}


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _coverage(observed, planned):
    return {"observed": observed, "planned": planned,
            "fraction": observed / planned if planned else None,
            "complete": bool(planned) and observed == planned}


def _metric(values, planned):
    return {"median": _median(values) if values else None,
            "coverage": _coverage(len(values), planned)}


def legacy_grade_id(trial_id, evaluator):
    """Stable identity for a pre-v2 assessment; shared with core validation."""
    value = json.dumps([trial_id, evaluator], ensure_ascii=False, separators=(",", ":"))
    return "legacy-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _assessment_map(records, known, identity, revisions=False):
    result = defaultdict(list)
    seen = set()
    ids, latest = {}, {}
    for record in records or []:
        trial_id = record.get("trial_id")
        if trial_id not in known:
            raise ValueError("assessment references an unknown trial")
        key = (trial_id, record.get(identity))
        copied = dict(record)
        if revisions:
            copied["id"] = record.get("id") or legacy_grade_id(trial_id, record.get(identity))
            if copied["id"] in ids:
                raise ValueError("duplicate assessment id")
            previous = record.get("supersedes")
            if previous is not None:
                if previous not in ids or latest.get(key) != previous:
                    raise ValueError("revision must replace the latest assessment")
                target = ids[previous]
                if (target.get("trial_id"), target.get(identity)) != key:
                    raise ValueError("revision must preserve trial and evaluator")
            elif key in seen:
                raise ValueError("repeat evaluator needs explicit supersedes")
            ids[copied["id"]] = copied
            latest[key] = copied["id"]
        elif key in seen:
            raise ValueError("duplicate trial assessment identity")
        seen.add(key)
        result[trial_id].append(copied)
    return result


def _judge_independence(active, profile, trial):
    """Flag declared authorship and exact model-label overlap without attestation.

    A common provider alone is not self-judging. Exact labels can establish a
    risk of self-judging, not the identity actually served by either endpoint.
    """
    candidate_labels = [(profile.get("model"), "requested_configuration")]
    if isinstance(trial.get("model_reported"), str) and trial["model_reported"].strip():
        candidate_labels.insert(0, (trial["model_reported"], "execution_reported_label"))
    conflicts, potential, unknown, independent, declared_nonconflicted = [], [], [], [], []
    for grade in active:
        grade_id = grade["id"]
        declared = grade.get("conflict_of_authorship")
        config = grade.get("evaluator_config") or {}
        if not isinstance(config, dict):
            config = {}
        overlap = next(((label, source) for label, source in candidate_labels
                        if isinstance(label, str) and label and config.get("kind") == "model"
                        and config.get("model") == label), None)
        if declared is True:
            conflicts.append(grade_id)
        elif declared is False:
            declared_nonconflicted.append(grade_id)
        if overlap:
            potential.append({"assessment_id": grade_id, "model_label": overlap[0], "source": overlap[1],
                              "candidate_provider_requested": profile.get("provider"),
                              "evaluator_provider_requested": config.get("provider"),
                              "provider_relation": "exact_requested_label_match" if profile.get("provider") == config.get("provider") else "unknown_or_different_labels",
                              "independence": "unverified", "served_identity_confirmed": False})
        elif declared is False:
            independent.append(grade_id)
        elif declared is None:
            unknown.append(grade_id)
    required = bool(active) and not independent and bool(conflicts or potential)
    return {"declared_conflict_ids": conflicts, "potential_self_judges": potential,
            "declared_nonconflicted_ids": declared_nonconflicted,
            "review_without_detected_conflict_ids": independent, "unknown_ids": unknown,
            "independent_review_required": required,
            "status": "unresolved" if required else "declared_nonconflicted_review_present" if independent else "unknown_legacy",
            "identity_attestation": "none; configuration and emitted labels only"}


def _grade_decision(history, case, floor, observable, evidence_sources=None, profile=None, trial=None):
    superseded = {grade.get("supersedes") for grade in history if grade.get("supersedes")}
    active = [grade for grade in history if grade["id"] not in superseded]
    result = {"active_ids": [grade["id"] for grade in active], "superseded_ids": sorted(superseded),
              "status": "unknown", "quality": None, "critical": "unknown",
              "criteria": [], "disagreement": False, "reasons": [],
              "independence": _judge_independence(active, profile or {}, trial or {}),
              "evidence_limits": {"literal_anchoring": "not checked for absent or legacy aggregate criteria",
                                  "semantic_entailment": "not established by substring matching",
                                  "granularity": "requires rubric-specific reviewer judgment",
                                  "minimum_quote_length": None}}
    if not observable or not active:
        result["reasons"].append("unobserved_result" if not observable else "missing_grades")
        return result
    if result["independence"]["independent_review_required"]:
        result["reasons"].append("independent_review_required")
        return result
    scores = [grade.get("quality") for grade in active]
    if any(not _number(score) or score > 4 for score in scores):
        result["reasons"].append("invalid_quality")
        return result
    critical_sets = [tuple(sorted(grade["critical_failures"])) if isinstance(grade.get("critical_failures"), list)
                     and all(isinstance(item, str) and item.strip() for item in grade["critical_failures"]) else None for grade in active]
    if len(set(scores)) != 1 or len(set(critical_sets)) != 1:
        result.update(disagreement=True)
        result["reasons"].append("adjudication_required")
    if len(set(scores)) == 1:
        result["quality"] = scores[0]
    if len(set(critical_sets)) == 1:
        result["critical"] = "unknown" if critical_sets[0] is None else "fail" if critical_sets[0] else "pass"
    metadata = case.get("criteria_metadata", [])
    criterion_ids = {item["id"] for item in metadata}
    criterion_ids.update(item["id"] for grade in active for item in grade.get("criteria", []))
    severity = {item["id"]: item for item in metadata}
    for criterion_id in sorted(criterion_ids):
        result["evidence_limits"]["literal_anchoring"] = "reported per criterion against intact supplied sources"
        entries = [next((item for item in grade.get("criteria", []) if item["id"] == criterion_id), None) for grade in active]
        statuses = [item.get("status", "unknown") if item else "unknown" for item in entries]
        literal_evidence = all(item and isinstance(item.get("evidence"), list) and item["evidence"]
                               and all(isinstance(value, str) and value.strip()
                                       and any(value in source for source in evidence_sources or [] if isinstance(source, str))
                                       for value in item["evidence"]) for item in entries)
        state = statuses[0] if len(set(statuses)) == 1 and literal_evidence and statuses[0] in {"pass", "partial", "fail", "unknown"} else "unknown"
        info = severity.get(criterion_id, {})
        result["criteria"].append({"id": criterion_id, "status": state,
                                   "critical": info.get("critical"), "severity": info.get("severity", "unknown"),
                                   "dimension": info.get("dimension", "unknown"),
                                   "evidence": [item.get("evidence", []) if item else [] for item in entries],
                                   "literal_anchoring_observed": bool(literal_evidence),
                                   "semantic_entailment": "reviewer judgment; not mechanically proved"})
        if len(set(statuses)) != 1:
            result["disagreement"] = True
            result["reasons"].append("criterion_disagreement")
        if state == "unknown" or (info.get("critical") and state == "partial"):
            result["reasons"].append("unknown_criterion")
            if info.get("critical"):
                result["critical"] = "unknown"
        elif state == "fail" and (info.get("critical") or info.get("severity") in {"critical", "material"}):
            result["reasons"].append("failed_material_criterion")
            if info.get("critical") or info.get("severity") == "critical":
                result["critical"] = "fail"
        elif state == "fail" and info.get("severity", "unknown") == "unknown":
            result["reasons"].append("unknown_criterion_severity")
    if result["disagreement"]:
        result["quality"] = None
    if result["critical"] == "fail" or "failed_material_criterion" in result["reasons"]:
        result["status"] = "fail"
    elif result["disagreement"] or result["critical"] == "unknown" or result["reasons"]:
        result["status"] = "unknown"
    elif result["quality"] < floor:
        result["status"] = "fail"
        result["reasons"].append("quality_below_floor")
    else:
        result["status"] = "pass"
    result["reasons"] = sorted(set(result["reasons"]))
    return result


def _cost(value):
    if not isinstance(value, dict) or not _number(value.get("amount")):
        return None
    keys = ("provider", "currency", "provenance")
    if not all(isinstance(value.get(key), str) and value[key].strip() for key in keys):
        return None
    return tuple(value[key] for key in keys) + (value["amount"],)


def _artifact_sources(trial):
    """Consume intact texts supplied by core; never open delivery files here."""
    receipts = {item.get("sha256"): item for item in trial.get("artifacts", []) if isinstance(item, dict)}
    sources, metadata = [], []
    for item in trial.get("artifact_texts", []):
        if not isinstance(item, dict):
            continue
        text, digest = item.get("text"), item.get("sha256")
        receipt = receipts.get(digest)
        verified = False
        if isinstance(text, str) and receipt:
            content = text.encode("utf-8")
            verified = len(content) == receipt.get("bytes") and hashlib.sha256(content).hexdigest() == digest
            if verified:
                sources.append(text)
        metadata.append({"name": item.get("name"), "sha256": digest, "literal_text_observed": verified,
                         "limitations": list(item.get("limitations", []))})
    return sources, metadata


def _family(profile, cases, repeats, trials, grades, feedback, audits, floor, minimum, manifest):
    """Observe each planned attempt; semantic and operational evidence stay apart."""
    planned = len(cases) * repeats
    counts = Counter(planned=planned, recorded=0, completed=0, graded=0,
                     missing=0, pending=0, errors=0)
    scores, assessment_scores, execution, queue, cost_values = [], [], [], [], []
    trajectory_counts = Counter(pass_=0, fail=0, unknown=0)
    critical_failed = critical_unknown = disagreements = 0
    failed_checks = unknown_checks = below_floor = 0
    blockers, unknown, warnings, limitations = set(), set(), set(), set()
    failure_types, human_preferences, acceptances = Counter(), Counter(), Counter()
    human_values = {name: [] for name in ("review_minutes", "corrections", "preparation_minutes",
                                         "integration_minutes", "accepted_delivery_minutes", "total_minutes")}
    human_trials, accepted_trials, total_time_trials, preference_use_trials = set(), set(), set(), set()
    personal_effort = []
    trial_summaries, case_summaries = [], []
    for case in cases:
        case_rows = []
        for repeat in range(1, repeats + 1):
            trial = trials.get((profile["id"], case["id"], repeat))
            summary = {"case_id": case["id"], "repeat": repeat,
                       "trial_id": trial.get("id") if trial else None,
                       "status": trial.get("status") if trial else "missing",
                       "quality": None, "outcome": "unknown",
                       "grades": [], "result_observable": False, "trajectory": "unknown"}
            trial_summaries.append(summary)
            case_rows.append(summary)
            if trial is None:
                counts["missing"] += 1
                critical_unknown += 1
                unknown_checks += 1
                trajectory_counts["unknown"] += 1
                unknown.update(("incomplete_execution", "missing_grades", "unknown_critical_failures", "unknown_checks", "unknown_trajectory"))
                continue
            counts["recorded"] += 1
            trial_id = trial["id"]
            limitations.update(str(item) for item in trial.get("limitations", []))
            unresolved_transport = bool(trial.get("collection_error") or trial.get("submission_error"))
            observable = trial.get("status") == "completed" and not unresolved_transport
            summary["result_observable"] = observable
            summary["transport_errors"] = {key: trial[key] for key in ("collection_error", "submission_error") if trial.get(key)}
            state = trial.get("status")
            host_semantic_failure = (trial.get("host_result") is True and state == "failed"
                                     and trial.get("failure_kind") == "semantic"
                                     and (trial.get("final_state_checks") or {}).get("status") == "fail"
                                     and not unresolved_transport)
            if observable:
                counts["completed"] += 1
                for key, target in (("execution_seconds", execution), ("queue_seconds", queue)):
                    if _number(trial.get(key)):
                        target.append(trial[key])
                        summary[key] = trial[key]
                value = _cost(trial.get("cost_estimate"))
                if value is not None:
                    cost_values.append(value)
            elif state in _ERROR or state == "unavailable":
                counts["errors"] += 1
            else:
                counts["pending"] += 1
            failure_kind = trial.get("failure_kind")
            if unresolved_transport:
                failure_kind = "infrastructure"
                unknown.add("unresolved_transport_errors")
            elif state == "timed_out":
                failure_kind = "timeout"
            elif state == "unavailable":
                failure_kind = "unavailable"
            elif state in _ERROR and failure_kind not in {"infrastructure", "operational", "semantic", "timeout", "unavailable"}:
                failure_kind = "operational_unknown"
            if failure_kind:
                failure_types[failure_kind] += 1
            summary["failure_kind"] = failure_kind
            deadline = case.get("deadline_seconds", manifest.get("deadline_seconds"))
            seconds = trial.get("execution_seconds")
            timeout_budget = manifest.get("timeout")
            deadline_missed = (_number(deadline) and deadline > 0
                               and ((_number(seconds) and seconds > deadline)
                                    or (state == "timed_out" and _number(timeout_budget) and timeout_budget >= deadline)))
            summary["deadline_missed"] = deadline_missed
            if deadline_missed:
                blockers.add("deadline_unmet")
            if not observable and not host_semantic_failure:
                unknown.add("operational_outcome_unknown")
            if (state in _ERROR or state == "unavailable") and not host_semantic_failure:
                unknown.add("operational_failure")
            history = grades.get(trial_id, [])
            summary["grades"] = history
            workflow = case.get("execution_mode") == "host-managed" or bool(case.get("workflow"))
            workflow_checks = trial.get("final_state_checks") or {}
            workflow_state = workflow_checks.get("status", "unknown") if workflow and (observable or host_semantic_failure) else "unknown"
            summary["workflow_final_state"] = {"status": workflow_state, "checks": workflow_checks.get("checks", [])}
            if workflow_state == "fail":
                blockers.add("observed_workflow_failure")
            elif workflow and workflow_state != "pass":
                unknown.add("unknown_workflow_final_state")
            textual_result = isinstance(trial.get("response"), str) and bool(trial["response"].strip())
            artifact_sources, artifact_metadata = _artifact_sources(trial)
            summary["artifact_text_sources"] = artifact_metadata
            evidence_sources = ([trial["response"]] if textual_result else []) + artifact_sources
            decision = _grade_decision(history, case, floor, observable and (not workflow or bool(evidence_sources)), evidence_sources, profile, trial)
            summary["judgment"] = decision
            summary["quality"] = decision["quality"]
            if history and observable:
                counts["graded"] += 1
                assessment_scores.extend(g["quality"] for g in history
                                         if g["id"] in decision["active_ids"] and _number(g.get("quality")) and g["quality"] <= 4)
            if decision["quality"] is not None:
                scores.append(decision["quality"])
            if decision["critical"] == "fail":
                critical_failed += 1
                blockers.add("critical_failures")
            elif decision["critical"] == "unknown":
                critical_unknown += 1
                unknown.add("unknown_critical_failures")
            if decision["disagreement"]:
                disagreements += 1
                unknown.add("adjudication_required")
            if "independent_review_required" in decision["reasons"]:
                unknown.add("independent_review_required")
            if decision["status"] == "fail":
                blockers.add("semantic_failure")
                if "quality_below_floor" in decision["reasons"]:
                    below_floor += 1
                    blockers.add("quality_below_floor")
            elif decision["status"] == "unknown":
                unknown.add("missing_or_unresolved_grades")
            response = trial.get("response")
            checks = trial.get("checks") or {}
            nonempty = isinstance(response, str) and bool(response.strip())
            limit = case.get("max_words", 450)
            word_limit = len(response.split()) <= limit if nonempty and type(limit) is int and limit > 0 else False if not nonempty else None
            summary["response_checks"] = {"nonempty": nonempty, "word_limit": word_limit}
            check_failure = observable and (not nonempty or checks.get("nonempty") is False)
            if workflow:
                artifacts = trial.get("artifacts", [])
                artifacts_observed = bool(artifacts) and all(isinstance(item, dict) and _number(item.get("bytes"))
                                                           and item["bytes"] > 0 and isinstance(item.get("sha256"), str)
                                                           and len(item["sha256"]) == 64 for item in artifacts)
                summary["artifacts"] = artifacts
                summary["artifact_receipts_observed"] = artifacts_observed
                check_failure = False
                if not artifacts_observed:
                    unknown.add("unknown_workflow_artifacts")
            if check_failure:
                blockers.add("empty_output")
            format_failure = not workflow and observable and (word_limit is False or checks.get("word_limit") is False)
            if format_failure:
                warnings.add("format_limit_exceeded")
                if case.get("word_limit_hard") is True:
                    blockers.add("hard_format_limit")
            hard_format_failure = format_failure and case.get("word_limit_hard") is True
            if check_failure or format_failure:
                failed_checks += 1
            checks_unknown = not observable or any(value is not True for value in (checks.get("nonempty"), checks.get("word_limit"))) and not (check_failure or format_failure)
            if workflow:
                checks_unknown = not observable or not artifacts_observed or workflow_state != "pass"
            if checks_unknown:
                unknown_checks += 1
                unknown.add("unknown_checks")
            embedded = trial.get("trajectory") or {}
            observations = audits.get(trial_id, [])
            summary["trajectory_audits"] = observations
            audit_states = {"fail" if a.get("violations") else a.get("status", "unknown") for a in observations}
            if not observable:
                trajectory_state = "unknown"
            elif embedded.get("status") == "fail" or embedded.get("violations"):
                trajectory_state = "fail"
            elif audit_states == {"fail"}:
                trajectory_state = "fail"
            elif audit_states == {"pass"}:
                trajectory_state = "pass"
            else:
                trajectory_state = "unknown"
                if len(audit_states) > 1:
                    unknown.add("trajectory_adjudication_required")
            summary["trajectory"] = trajectory_state
            trajectory_counts["pass_" if trajectory_state == "pass" else trajectory_state] += 1
            if trajectory_state == "fail":
                blockers.add("failed_trajectory")
            elif trajectory_state == "unknown":
                unknown.add("unknown_trajectory")
            if (observable and decision["status"] == "fail") or check_failure or hard_format_failure or trajectory_state == "fail" or deadline_missed or workflow_state == "fail":
                summary["outcome"] = "fail"
            elif observable and decision["status"] == "pass" and trajectory_state == "pass" and not checks_unknown:
                summary["outcome"] = "pass"
            summary["feedback"] = feedback.get(trial_id, [])
            for item in summary["feedback"]:
                preference = item.get("preference")
                if preference in {"use", "revise", "reject"}:
                    human_trials.add(trial_id)
                    human_preferences[preference] += 1
                    if preference == "use":
                        preference_use_trials.add(trial_id)
                acceptance = item.get("acceptance", "unknown")
                if acceptance in {"accepted", "revise", "rejected", "unknown"}:
                    acceptances[acceptance] += 1
                    if acceptance == "accepted":
                        accepted_trials.add(trial_id)
                for key, values in human_values.items():
                    if _number(item.get(key)):
                        values.append(item[key])
                        if key == "total_minutes":
                            total_time_trials.add(trial_id)
            coherent = [item for item in summary["feedback"] if item.get("preference") == "use"
                        and item.get("acceptance") == "accepted" and _number(item.get("total_minutes"))]
            if coherent and len({item["total_minutes"] for item in coherent}) == 1:
                personal_effort.append({"trial_id": trial_id, "case_id": case["id"], "repeat": repeat,
                                        "total_minutes": coherent[0]["total_minutes"],
                                        "reviewers": sorted({item["reviewer"] for item in coherent})})
        outcomes = Counter(row["outcome"] for row in case_rows)
        complete_case = all(row["outcome"] == "pass" for row in case_rows)
        case_summaries.append({"case_id": case["id"], "planned_attempts": repeats,
                               "recorded_attempts": sum(row["trial_id"] is not None for row in case_rows),
                               "completed_attempts": sum(row["result_observable"] for row in case_rows),
                               "successes": outcomes["pass"], "failures": outcomes["fail"], "unknown": outcomes["unknown"],
                               "success_fraction_of_planned": outcomes["pass"] / repeats,
                               "all_attempts_observed_pass": complete_case,
                               "variability": {"quality": _describe([row["quality"] for row in case_rows if row["quality"] is not None]),
                                               "execution_seconds": _describe([row["execution_seconds"] for row in case_rows if _number(row.get("execution_seconds"))])}})
    technical_status = "fail" if blockers else "unknown" if unknown else "observed_pass"
    status = "blocked" if blockers else "inconclusive" if unknown else "provisional"
    cost_groups = []
    if len(cost_values) == planned:
        grouped = defaultdict(list)
        for provider, currency, provenance, amount in cost_values:
            grouped[(provider, currency, provenance)].append(amount)
        for (provider, currency, provenance), amounts in sorted(grouped.items()):
            cost_groups.append({"provider": provider, "currency": currency, "provenance": provenance,
                                "observations": len(amounts), "total": _sum(amounts), "median": _median(amounts)})
    personal_complete = (len(human_trials) == planned and len(accepted_trials) == planned
                         and len(total_time_trials) == planned and len(preference_use_trials) == planned
                         and len(personal_effort) == planned
                         and not human_preferences["reject"] and not human_preferences["revise"]
                         and not acceptances["revise"] and not acceptances["rejected"])
    personal_status = "supported_observed_scope" if personal_complete and technical_status == "observed_pass" and not warnings else "review" if human_preferences["reject"] or human_preferences["revise"] else "unknown"
    result = {
        "family": cases[0]["family"], "case_ids": sorted(case["id"] for case in cases),
        "independent_cases": len(cases), "minimum_independent_cases": minimum,
        "counts": dict(counts), "coverage": {"completion": _coverage(counts["completed"], planned),
                                             "grading": _coverage(counts["graded"], planned)},
        "status": status, "technical_status": technical_status,
        "qualification": {"scope": "declared observed cases and final-state checks only", "generalization": "unestablished",
                          "representativeness": "not validated", "new_case_confirmation": "unknown",
                          "case_count_alone_qualifies": False},
        "blockers": sorted(blockers), "unknown": sorted(unknown), "warnings": sorted(warnings),
        "operational": {"failure_types": dict(sorted(failure_types.items())),
                        "capacity_inferred_from_operational_failure": False},
        "quality": {"floor": floor, "aggregation": "agreement of active assessments; disagreement unresolved",
                    "median": _median(scores) if scores else None,
                    "distribution": {str(score): number for score, number in sorted(Counter(scores).items())},
                    "assessment_distribution": {str(score): number for score, number in sorted(Counter(assessment_scores).items())},
                    "below_floor_trials": below_floor, "critical_failed_trials": critical_failed,
                    "critical_unknown_trials": critical_unknown, "disagreement_trials": disagreements,
                    "zero_critical_failures_confirmed": not critical_failed and not critical_unknown},
        "trajectory": {"pass": trajectory_counts["pass_"], "fail": trajectory_counts["fail"],
                       "unknown": trajectory_counts["unknown"], "independent_audit_required": True},
        "checks": {"failed_trials": failed_checks, "unknown_trials": unknown_checks},
        "efficiency": {"execution_seconds": _metric(execution, planned), "queue_seconds": _metric(queue, planned),
                       "cost_estimates": {"coverage": _coverage(len(cost_values), planned), "groups": cost_groups,
                                          "status": "complete" if len(cost_values) == planned else "unknown_or_partial"},
                       "tokens_aggregated": False},
        "human_feedback": {"status": "observed" if human_trials else "unknown",
                           "coverage": _coverage(len(human_trials), planned),
                           "preferences": dict(sorted(human_preferences.items())),
                           "acceptance": dict(sorted(acceptances.items())),
                           "accepted_coverage": _coverage(len(accepted_trials), planned),
                           "total_time_coverage": _coverage(len(total_time_trials), planned),
                           "personal_recommendation_status": personal_status,
                           "accepted_personal_effort_by_trial": personal_effort,
                           **{key: {**_describe(values), "observations": len(values)} for key, values in human_values.items()}},
        "reliability": {"successes": sum(c["successes"] for c in case_summaries),
                        "failures": sum(c["failures"] for c in case_summaries),
                        "unknown": sum(c["unknown"] for c in case_summaries),
                        "unit": "planned attempt; grouped by independent case", "cases": case_summaries},
        "limitations": sorted(limitations), "trials": trial_summaries,
    }
    result["comparison_observed"] = all(row["outcome"] != "unknown" for row in trial_summaries)
    result["pareto_eligible"] = not blockers and any(case["all_attempts_observed_pass"] for case in case_summaries)
    data_needed = sorted(unknown)
    if personal_status != "supported_observed_scope":
        data_needed.append("explicit_acceptance_preference_and_total_effort")
    data_needed.extend(("representative_real_actions", "confirmation_on_new_cases"))
    result["guidance"] = {"action": "use_observed_scope" if personal_status == "supported_observed_scope"
                           else "review" if blockers or warnings or personal_status == "review"
                           else "candidate_for_human_validation" if technical_status == "observed_pass" else "inconclusive",
                          "scope": "declared observed cases only",
                          "reason": "Technical evidence and personal acceptance are separate; text screening remains provisional.",
                          "data_needed": data_needed, "human_feedback": personal_status}
    return result


def _describe(values):
    return {"median": _median(values) if values else None, "minimum": min(values) if values else None,
            "maximum": max(values) if values else None, "count": len(values),
            "uncertainty": "descriptive only; no statistical significance or confidence interval"}

def _comparisons(profiles, families, manifest, pairwise_feedback):
    policy = manifest.get("comparison_policy") or {}
    margins_known = _number(policy.get("quality_margin")) and _number(policy.get("execution_seconds_margin"))
    quality_margin = policy.get("quality_margin") if margins_known else None
    time_margin = policy.get("execution_seconds_margin") if margins_known else None
    comparisons = []
    for family_name in families:
        members = {p["id"]: next(f for f in p["families"] if f["family"] == family_name) for p in profiles}
        observed = {}
        exclusions = []
        for pid, family in members.items():
            comparable_cases = []
            excluded_cases = []
            for case in family["reliability"]["cases"]:
                rows = [row for row in family["trials"] if row["case_id"] == case["case_id"]]
                if case["all_attempts_observed_pass"] and all(_number(row.get("execution_seconds")) for row in rows):
                    comparable_cases.append(case["case_id"])
                else:
                    excluded_cases.append({"case_id": case["case_id"], "reason": "incomplete_or_unresolved_attempts_or_timing"})
            if family["blockers"]:
                exclusions.append({"profile_id": pid, "reasons": family["blockers"], "excluded_cases": excluded_cases})
            elif not comparable_cases:
                exclusions.append({"profile_id": pid, "reasons": family["unknown"] or ["no_comparable_cases"], "excluded_cases": excluded_cases})
            else:
                observed[pid] = {"family": family, "case_ids": sorted(comparable_cases), "excluded_cases": excluded_cases}
        pairs = []
        for pid_a, pid_b in itertools.combinations(sorted(observed), 2):
            a, b = observed[pid_a], observed[pid_b]
            matched = sorted(set(a["case_ids"]) & set(b["case_ids"]))
            if not matched:
                pairs.append({"profile_a": pid_a, "profile_b": pid_b, "status": "no_matching_observed_cases", "case_ids": [], "cases": []})
                continue
            cases, differences = [], []
            for case_id in matched:
                rows_a = {row["repeat"]: row for row in a["family"]["trials"] if row["case_id"] == case_id}
                rows_b = {row["repeat"]: row for row in b["family"]["trials"] if row["case_id"] == case_id}
                attempts = []
                for repeat in sorted(rows_a):
                    left, right = rows_a[repeat], rows_b[repeat]
                    quality_difference = left["quality"] - right["quality"]
                    time_difference = right["execution_seconds"] - left["execution_seconds"]
                    differences.append((quality_difference, time_difference))
                    attempts.append({"repeat": repeat, "trial_a": left["trial_id"], "trial_b": right["trial_id"],
                                     "quality_a": left["quality"], "quality_b": right["quality"],
                                     "execution_seconds_a": left["execution_seconds"], "execution_seconds_b": right["execution_seconds"],
                                     "quality_ordinal_difference_a_minus_b": quality_difference,
                                     "execution_seconds_advantage_a": time_difference})
                cases.append({"case_id": case_id, "attempts": attempts,
                              "quality_ordinal_difference": _describe([x["quality_ordinal_difference_a_minus_b"] for x in attempts]),
                              "execution_seconds_advantage_a": _describe([x["execution_seconds_advantage_a"] for x in attempts])})
            matching_subset = a["case_ids"] == b["case_ids"]
            sufficient_for_descriptive_dominance = margins_known and matching_subset and len(matched) >= 2
            domination, practical_tie = None, False
            if sufficient_for_descriptive_dominance:
                a_no_worse = all(q >= -quality_margin and t >= -time_margin for q, t in differences)
                b_no_worse = all(q <= quality_margin and t <= time_margin for q, t in differences)
                a_better = any(q > quality_margin or t > time_margin for q, t in differences)
                b_better = any(q < -quality_margin or t < -time_margin for q, t in differences)
                if a_no_worse and a_better and not b_no_worse:
                    domination = pid_a
                elif b_no_worse and b_better and not a_no_worse:
                    domination = pid_b
                practical_tie = not a_better and not b_better
            human_records = [dict(item) for item in pairwise_feedback
                             if item.get("case_id") in matched and {item.get("profile_a"), item.get("profile_b")} == {pid_a, pid_b}]
            pairs.append({"profile_a": pid_a, "profile_b": pid_b, "status": "descriptive_paired_evidence",
                          "case_ids": matched, "independent_paired_cases": len(matched), "cases": cases,
                          "matching_full_observed_subset": matching_subset,
                          "excluded_cases": sorted(set(members[pid_a]["case_ids"]) - set(matched)),
                          "descriptive_dominant_profile": domination, "practical_tie": practical_tie,
                          "human_pairwise_feedback": human_records,
                          "uncertainty": "case-grouped description only; correlated repeats; no significance claim"})
        groups = defaultdict(list)
        for pid, item in observed.items():
            groups[tuple(item["case_ids"])].append(pid)
        subsets, all_front, ties = [], [], []
        for case_ids, ids in sorted(groups.items()):
            if len(ids) < 2:
                continue
            group_pairs = [pair for pair in pairs if pair["profile_a"] in ids and pair["profile_b"] in ids]
            dominated = {pair["profile_b"] if pair.get("descriptive_dominant_profile") == pair["profile_a"] else pair["profile_a"]
                         for pair in group_pairs if pair.get("descriptive_dominant_profile")}
            pareto_available = margins_known and len(case_ids) >= 2
            front = sorted(set(ids) - dominated) if pareto_available else []
            group_ties = [[pair["profile_a"], pair["profile_b"]] for pair in group_pairs if pair.get("practical_tie")]
            all_front.extend(front)
            ties.extend(group_ties)
            subsets.append({"profile_ids": sorted(ids), "case_ids": list(case_ids),
                            "excluded_profile_ids": sorted(set(members) - set(ids)),
                            "pareto_profile_ids": front, "practical_ties": group_ties,
                            "status": "provisional_descriptive_pareto" if pareto_available else "descriptive_only",
                            "scope": "same observed cases, all planned attempts; no generalization"})
        comparisons.append({"family": family_name, "profile_ids": sorted(members),
                            "eligible_profile_ids": sorted(observed), "exclusions": exclusions,
                            "matching_cases": any(pair["case_ids"] for pair in pairs),
                            "complete_compared_coverage": bool(pairs) and all(pair["case_ids"] for pair in pairs),
                            "complete_inventory_coverage": all(f["comparison_observed"] for f in members.values()),
                            "status": "descriptive" if any(pair["case_ids"] for pair in pairs) else "inconclusive_or_provisional",
                            "practical_margins": {"quality_ordinal": quality_margin, "execution_seconds": time_margin,
                                                 "predeclared": margins_known},
                            "pairs": pairs, "subsets": subsets,
                            "pareto": {"axes": ["paired_quality_no_worse", "paired_execution_seconds_no_worse"],
                                       "profile_ids": sorted(set(all_front)), "ties": sorted(ties),
                                       "status": "provisional_descriptive" if all_front else "unavailable",
                                       "scope": "separate matching subsets; never a global frontier"},
                            "cost_and_human_preference_included": False})
    return comparisons


def _mean(values):
    value = 0
    for index, item in enumerate(values, 1):
        value += (item - value) / index
    return value


def _aggregate_recommendation(manifest, profiles, families):
    """Project observed accepted human effort onto a predeclared action mix.

    Quality, trajectory, acceptance and personal preference are eligibility
    gates. The numeric projection contains human minutes only, never grades,
    model execution time, cost or an invented utility score.
    """
    result = {"status": "provisional_observed_evidence", "general_winner": None,
              "aggregate_status": "unavailable_missing_action_weights", "defaults_changed": False,
              "action_weights": manifest.get("action_weights"), "normalized_action_weights": {},
              "personal_time_margin_minutes": None, "candidates": [], "exclusions": [],
              "scope": "provisional projection of observed accepted human effort onto the declared action distribution",
              "reason": "Predeclared positive action weights and complete accepted personal feedback are required; no universal calibration is inferred."}
    weights = manifest.get("action_weights")
    if not isinstance(weights, dict) or not weights or any(family not in families or not _number(weight) for family, weight in weights.items()):
        return result
    positive = {family: weight for family, weight in weights.items() if weight > 0}
    if not positive:
        return result
    maximum = max(positive.values())
    scaled = {family: weight / maximum for family, weight in positive.items()}
    if any(weight == 0 for weight in scaled.values()):
        result["aggregate_status"] = "unavailable_unrepresentable_weights"
        return result
    total = sum(scaled.values())
    normalized = {family: weight / total for family, weight in sorted(scaled.items())}
    if any(weight == 0 for weight in normalized.values()):
        result["aggregate_status"] = "unavailable_unrepresentable_weights"
        return result
    result["normalized_action_weights"] = normalized
    policy = manifest.get("comparison_policy") or {}
    margin = policy.get("personal_time_margin_minutes")
    if not _number(margin):
        result["aggregate_status"] = "unavailable_missing_personal_time_margin"
        return result
    result["personal_time_margin_minutes"] = margin
    signatures = {}
    for profile in profiles:
        projected, reasons = {}, []
        for family_name in normalized:
            family = next((item for item in profile["families"] if item["family"] == family_name), None)
            if (family is None or family["technical_status"] != "observed_pass"
                    or family["human_feedback"]["personal_recommendation_status"] != "supported_observed_scope"):
                reasons.append({"family": family_name, "reason": "incomplete_technical_or_accepted_personal_evidence"})
                continue
            effort = family["human_feedback"]["accepted_personal_effort_by_trial"]
            projected[family_name] = {"mean_total_minutes": _mean([item["total_minutes"] for item in effort]),
                                     "observations": len(effort), "case_ids": family["case_ids"],
                                     "planned_attempts": family["counts"]["planned"]}
        if reasons:
            result["exclusions"].append({"profile_id": profile["id"], "reasons": reasons})
            continue
        value, used_weight = 0, 0
        for family_name, weight in normalized.items():
            used_weight += weight
            value += (projected[family_name]["mean_total_minutes"] - value) * (weight / used_weight)
        signatures[profile["id"]] = tuple((family_name, tuple(projected[family_name]["case_ids"]), projected[family_name]["planned_attempts"]) for family_name in normalized)
        result["candidates"].append({"profile_id": profile["id"], "weighted_mean_total_human_minutes": value,
                                     "families": projected})
    if len(result["candidates"]) < 2 or len(set(signatures.values())) != 1:
        result["aggregate_status"] = "unavailable_insufficient_comparable_personal_feedback"
        return result
    ordered = sorted(result["candidates"], key=lambda item: (item["weighted_mean_total_human_minutes"], item["profile_id"]))
    best = ordered[0]["weighted_mean_total_human_minutes"]
    tied = [item["profile_id"] for item in ordered if item["weighted_mean_total_human_minutes"] - best <= margin]
    result["practical_tie_profile_ids"] = tied if len(tied) > 1 else []
    if len(tied) > 1:
        result["aggregate_status"] = "provisional_projection_practical_tie"
        result["reason"] = "Observed accepted human-effort differences fall within the predeclared practical margin; no unique recommendation."
    else:
        result["aggregate_status"] = "provisional_contextual_recommendation"
        result["general_winner"] = ordered[0]["profile_id"]
        result["reason"] = "Lower observed accepted total human effort for the declared action mix, beyond the practical margin, among the comparable eligible candidates only."
    return result


def build_report(manifest, trials, grades, feedback, trajectory=None, pairwise_feedback=None):
    """Return a JSON-serializable report without changing experiment state.

    Core validates schema and provenance. Defensive identity checks here prevent
    accidental double counting when this public function is used independently.
    """
    profiles, cases = manifest["profiles"], manifest["cases"]
    repeats = manifest["repeats"]
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats <= 0:
        raise ValueError("repeats must be a positive integer")
    if not profiles or not cases:
        raise ValueError("report requires planned profiles and cases")
    if len({p["id"] for p in profiles}) != len(profiles) or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("planned identities must be unique")
    planned_profiles = {p["id"] for p in profiles}
    planned_cases = {c["id"]: c for c in cases}
    indexed, known = {}, set()
    for trial in trials:
        key = (trial.get("profile_id"), trial.get("case_id"), trial.get("repeat"))
        if (key[0] not in planned_profiles or key[1] not in planned_cases
                or isinstance(key[2], bool) or not isinstance(key[2], int)
                or not 1 <= key[2] <= repeats):
            raise ValueError("trial is outside the planned matrix")
        if trial.get("family") != planned_cases[key[1]]["family"]:
            raise ValueError("trial family differs from planned case")
        if key in indexed or not trial.get("id") or trial["id"] in known:
            raise ValueError("duplicate or missing trial identity")
        indexed[key] = trial
        known.add(trial["id"])
    grade_map = _assessment_map(grades, known, "evaluator", revisions=True)
    feedback_map = _assessment_map(feedback, known, "reviewer")
    audit_map = _assessment_map(trajectory, known, "evaluator")
    minimum = max(3, manifest.get("minimum_cases_per_family", manifest.get("minimum_trials", 3)))
    floor = manifest.get("quality_floor", 3)
    families = sorted({c["family"] for c in cases})
    reported_profiles = []
    for profile in sorted(profiles, key=lambda p: p["id"]):
        profile_trials = [trial for trial in trials if trial["profile_id"] == profile["id"]]
        reported_models = [trial["model_reported"] for trial in profile_trials
                           if isinstance(trial.get("model_reported"), str) and trial["model_reported"].strip()]
        reported_profiles.append({"id": profile["id"], "requested": dict(profile),
                                  "confirmed_model_identity": "not inferred from requested profile",
                                  "model_reported": {"status": "reported" if reported_models else "unknown",
                                                     "labels": sorted(set(reported_models)),
                                                     "coverage": _coverage(len(reported_models), len(cases) * repeats),
                                                     "source": "execution result; label is not independently verified"},
                                  "families": [_family(profile, [c for c in cases if c["family"] == family],
                                                       repeats, indexed, grade_map, feedback_map, audit_map, floor, minimum, manifest)
                                               for family in families]})
    totals = Counter()
    for profile in reported_profiles:
        for family in profile["families"]:
            totals.update(family["counts"])
    comparisons = _comparisons(reported_profiles, families, manifest, pairwise_feedback or [])
    return {"schema_version": 2, "experiment_id": manifest.get("id"),
            "experiment_created_at": manifest.get("created_at"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": manifest.get("mode"), "scope": "bounded observed cases and declared checks",
            "counts": dict(totals), "profiles": reported_profiles,
            "family_comparisons": comparisons,
            "recommendation": _aggregate_recommendation(manifest, reported_profiles, families),
            "limitations": ["Human feedback is explicit and separate from model grades.",
                            "Unknown trajectory requires an independent audit before qualification.",
                            "Repeats do not increase the independent case count.",
                            "Costs are estimates grouped by provider, currency and provenance; tokens are not aggregated.",
                            "Comparisons preserve paired cases and practical margins; no median-only dominance.",
                            "Operational failures do not imply model incapacity; an explicit deadline is a separate fit constraint.",
                            "Active judge disagreement requires adjudication; superseded records remain in history.",
                            "Case counts alone do not establish representative actions or statistical confidence."]}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _value(value):
    return "desconhecido" if not _number(value) else f"{value:g}"


def render_markdown(report):
    """Render evidence and uncertainty in Portuguese, keeping original rationales."""
    states = {"provisional": "evidência provisória", "inconclusive": "inconclusivo", "blocked": "bloqueado",
              "descriptive": "comparação descritiva", "inconclusive_or_provisional": "inconclusivo ou provisório",
              "provisional_observed_evidence": "evidência observada provisória"}
    actions = {"use_observed_scope": "uso apoiado apenas no recorte observado", "review": "revisar",
               "inconclusive": "inconclusivo", "candidate_for_human_validation": "candidato para validação humana"}
    reasons = {"critical_failures": "falhas críticas no julgamento ativo", "semantic_failure": "falha semântica julgada",
               "empty_output": "entrega textual vazia", "hard_format_limit": "limite de formato obrigatório",
               "deadline_unmet": "prazo explicitamente declarado não atendido", "failed_trajectory": "trajetória reprovada",
               "quality_below_floor": "qualidade abaixo do piso", "incomplete_execution": "execuções incompletas",
               "missing_grades": "avaliações ausentes", "unknown_critical_failures": "falhas críticas sem julgamento completo",
               "unknown_checks": "checagens desconhecidas", "unknown_trajectory": "auditoria de trajetória ausente",
               "unresolved_transport_errors": "erros de transporte aguardando reconciliação",
               "operational_failure": "falha operacional, sem inferência de incapacidade",
               "operational_outcome_unknown": "resultado operacional sem observabilidade",
               "missing_or_unresolved_grades": "avaliações ausentes ou não resolvidas",
               "adjudication_required": "discordância entre avaliadores, exige adjudicação",
               "independent_review_required": "revisão sem conflito de autoria ou possível autoavaliação ainda ausente",
               "trajectory_adjudication_required": "discordância de auditoria de trajetória",
               "format_limit_exceeded": "limite de formato excedido, gravidade depende da tarefa",
               "observed_workflow_failure": "falha observada nas checagens do estado final do fluxo",
               "unknown_workflow_final_state": "estado final do fluxo sem observação válida",
               "unknown_workflow_artifacts": "artefatos do fluxo sem comprovantes observados",
               "explicit_acceptance_preference_and_total_effort": "aceitação, preferência e esforço total explícitos",
               "representative_real_actions": "ações reais representativas", "confirmation_on_new_cases": "confirmação em casos novos"}
    family_names = {"retrieval": "recuperação", "ingestion": "ingestão", "analysis": "análise",
                    "research": "pesquisa", "code": "código", "communication": "comunicação"}

    def labels(values):
        return ", ".join(reasons.get(value, value) for value in values)

    lines = [f"# Avaliação de modelos: {_cell(report.get('experiment_id'))}", "",
             f"Gerado em: {_cell(report['generated_at'])}", "",
             "Escopo: evidência dos casos e condições declarados. Casos textuais não qualificam ações completas; fluxos preparados comprovam somente as checagens observadas.", "",
             "Recomendação: evidência observada provisória. Padrões alterados: não.", "",
             "| Perfil | Família | Casos independentes | Concluídos / planejados | Avaliados / planejados | Ausentes / pendentes / erros | Situação |",
             "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for profile in report["profiles"]:
        for family in profile["families"]:
            c = family["counts"]
            lines.append(f"| {_cell(profile['id'])} | {_cell(family_names.get(family['family'], family['family']))} | {family['independent_cases']} | {c['completed']} / {c['planned']} | {c['graded']} / {c['planned']} | {c['missing']} / {c['pending']} / {c['errors']} | {states[family['status']]} |")
    for profile in report["profiles"]:
        requested, reported = profile["requested"], profile["model_reported"]
        lines += ["", f"## Perfil {_cell(profile['id'])}", "",
                  f"Solicitado: modelo {_cell(requested.get('model', 'desconhecido'))}; provedor {_cell(requested.get('provider', 'desconhecido'))}; esforço {_cell(requested.get('effort', 'desconhecido'))}.", "",
                  f"Modelos informados nas execuções: {_cell(', '.join(reported['labels']) or 'desconhecidos')}; cobertura {reported['coverage']['observed']} / {reported['coverage']['planned']}. Rótulos sem verificação independente; a configuração solicitada não comprova a servida."]
        for family in profile["families"]:
            quality, trajectory, efficiency, human = (family[key] for key in ("quality", "trajectory", "efficiency", "human_feedback"))
            lines += ["", f"### {_cell(family_names.get(family['family'], family['family']))}", "",
                      f"Casos independentes: {family['independent_cases']}. Repetições não são casos independentes. Nenhuma contagem, isoladamente, comprova representatividade ou validade estatística.", "",
                      f"Orientação: {actions[family['guidance']['action']]}. Escopo: apenas os casos e condições observados; recomendação pessoal depende de aceitação e esforço humano explícitos.", "",
                      f"Dados necessários: {_cell(labels(family['guidance']['data_needed']))}.", "",
                      f"Qualidade: mediana descritiva {_value(quality['median'])}; piso {quality['floor']}; distribuição {_cell(quality['distribution'])}. Somente avaliações ativas concordantes; divergências não viram a menor nota.", "",
                      f"Discordâncias: {quality['disagreement_trials']} execuções. Falhas críticas: {quality['critical_failed_trials']} julgadas; {quality['critical_unknown_trials']} sem julgamento resolvido. Ausência confirmada no julgamento ativo: {'sim' if quality['zero_critical_failures_confirmed'] else 'não'}.", "",
                      "Ancoragem literal verifica a presença da citação. Sozinha não comprova que o trecho sustenta a conclusão ou tem detalhe suficiente para o critério; citações curtas não são vetadas por tamanho.", "",
                      f"Trajetória: {trajectory['pass']} aprovadas, {trajectory['fail']} reprovadas, {trajectory['unknown']} desconhecidas, por auditoria independente.", "",
                      f"Checagens: {family['checks']['failed_trials']} reprovadas, {family['checks']['unknown_trials']} desconhecidas.", "",
                      f"Bloqueios: {_cell(labels(family['blockers']) or 'nenhum observado')}. Evidência inconclusiva: {_cell(labels(family['unknown']) or 'nenhuma')}. Avisos: {_cell(labels(family['warnings']) or 'nenhum')}.", "",
                      f"Falhas operacionais por tipo: {_cell(family['operational']['failure_types'])}. Timeout e indisponibilidade não recebem nota de capacidade zero.", ""]
            for name, title in (("execution_seconds", "Tempo de execução em segundos"), ("queue_seconds", "Tempo em fila em segundos")):
                metric, coverage = efficiency[name], efficiency[name]["coverage"]
                lines += [f"{title}: mediana {_value(metric['median'])}; observado {coverage['observed']} / {coverage['planned']}.", ""]
            costs = efficiency["cost_estimates"]
            lines += [f"Estimativas de custo: {'completas' if costs['status'] == 'complete' else 'desconhecidas ou parciais'}; observado {costs['coverage']['observed']} / {costs['coverage']['planned']}.", ""]
            for group in costs["groups"]:
                lines += [f"- {_cell(group['provider'])}, {_cell(group['currency'])}, proveniência {_cell(group['provenance'])}: total {_value(group['total'])}; mediana {_value(group['median'])}."]
            if costs["groups"]:
                lines.append("")
            preferences = {"usar" if key == "use" else "revisar" if key == "revise" else "rejeitar": value
                           for key, value in human["preferences"].items()}
            lines += [f"Retorno humano: {'observado' if human['status'] == 'observed' else 'desconhecido'}; cobertura {human['coverage']['observed']} / {human['coverage']['planned']}; preferências {_cell(preferences)}.", "",
                      f"Aceitação explícita: {_cell(human['acceptance'])}; entregas aceitas {human['accepted_coverage']['observed']} / {human['accepted_coverage']['planned']}. Preferência não implica aceitação.", "",
                      f"Minutos de revisão humana: mediana {_value(human['review_minutes']['median'])}; correções: mediana {_value(human['corrections']['median'])}.", "",
                      f"Esforço total observado em minutos: mediana {_value(human['total_minutes']['median'])}; cobertura {human['total_time_coverage']['observed']} / {human['total_time_coverage']['planned']}. Não é calculado pela soma de parcelas potencialmente sobrepostas.", "",
                      f"Tempo até entrega aceita em minutos: mediana {_value(human['accepted_delivery_minutes']['median'])}; preparação: mediana {_value(human['preparation_minutes']['median'])}; integração: mediana {_value(human['integration_minutes']['median'])}.", "",
                      "#### Confiabilidade por caso", "",
                      "| Caso | Tentativas planejadas | Sucessos | Falhas julgadas | Desconhecidas |",
                      "| --- | ---: | ---: | ---: | ---: |"]
            for case in family["reliability"]["cases"]:
                lines.append(f"| {_cell(case['case_id'])} | {case['planned_attempts']} | {case['successes']} | {case['failures']} | {case['unknown']} |")
            for limitation in family["limitations"]:
                lines += ["", f"Limitação informada pela execução: {_cell(limitation)}"]
            graded = [trial for trial in family["trials"] if trial.get("grades")]
            if graded:
                lines += ["", "#### Histórico e evidências das avaliações", ""]
            for trial in graded:
                decision = trial["judgment"]
                lines += [f"- Caso {_cell(trial['case_id'])}, repetição {trial['repeat']}, execução {_cell(trial['trial_id'])}."]
                if "artifact_receipts_observed" in trial:
                    lines += ["", f"Estado final do fluxo: {_cell(trial['workflow_final_state']['status'])}; comprovantes de artefatos observados: {'sim' if trial['artifact_receipts_observed'] else 'não'}. Fontes textuais verificadas: {_cell(trial['artifact_text_sources'])}. A verificação visual continua limitada ao que foi explicitamente observado."]
                if not trial["result_observable"]:
                    lines += ["", "Resultado sem observabilidade confiável: avaliações preservadas para revisão, excluídas das métricas até reconciliar a execução."]
                if decision["disagreement"]:
                    lines += ["", "Discordância não resolvida: exige adjudicação; não constitui automaticamente falha grave do candidato."]
                independence = decision["independence"]
                if independence["independent_review_required"]:
                    lines += ["", "Revisão independente necessária: todas as avaliações ativas têm conflito declarado ou possível autoavaliação, ou falta avaliação sem o conflito detectado."]
                if independence["potential_self_judges"]:
                    lines += ["", f"Risco de autoavaliação por igualdade exata de rótulo: {_cell(independence['potential_self_judges'])}. A origem solicitada ou reportada não confirma a identidade servida."]
                for grade in trial["grades"]:
                    active = grade["id"] in decision["active_ids"]
                    lines += ["", f"Avaliação {_cell(grade['id'])}, {'ativa' if active else 'substituída'}; avaliador {_cell(grade.get('evaluator'))}; substitui {_cell(grade.get('supersedes') or 'nenhuma')}; nota {_value(grade.get('quality'))}. Justificativa: {_cell(grade.get('notes', 'ausente'))}.", "",
                              f"Evidências: {_cell('; '.join(str(item) for item in grade.get('evidence', [])) or 'ausentes')}. Falhas críticas declaradas: {_cell('; '.join(str(item) for item in grade.get('critical_failures', [])) or 'nenhuma')}.", "",
                              f"Configuração do avaliador: {_cell(grade.get('evaluator_config', 'desconhecida'))}; versão da rubrica: {_cell(grade.get('rubric_version', 'desconhecida'))}; conflito de autoria: {_cell(grade.get('conflict_of_authorship', 'desconhecido'))}."]
                    for criterion in grade.get("criteria", []):
                        lines += ["", f"Critério {_cell(criterion['id'])}: {_cell(criterion['status'])}; evidência literal {_cell('; '.join(criterion.get('evidence', [])) or 'ausente')}."]
    lines += ["", "## Comparações por família", ""]
    for comparison in report["family_comparisons"]:
        front = comparison["pareto"]["profile_ids"]
        lines += [f"### {_cell(family_names.get(comparison['family'], comparison['family']))}", "",
                  f"Situação: {states[comparison['status']]}; candidatos com subconjuntos observados: {_cell(', '.join(comparison['eligible_profile_ids']) or 'nenhum')}.", "",
                  f"Fronteiras descritivas por subconjunto: {_cell(', '.join(front) or 'indisponíveis')}; empates práticos: {_cell(comparison['pareto']['ties'])}. Nenhum vencedor sobre perfis excluídos.", "",
                  f"Margens práticas congeladas: qualidade ordinal {_value(comparison['practical_margins']['quality_ordinal'])}; execução em segundos {_value(comparison['practical_margins']['execution_seconds'])}. Sem margens, apenas descrição.", ""]
        for exclusion in comparison["exclusions"]:
            lines += [f"- Excluído {_cell(exclusion['profile_id'])}: {_cell(labels(exclusion['reasons']))}."]
        for subset in comparison["subsets"]:
            lines += ["", f"Subconjunto: perfis {_cell(', '.join(subset['profile_ids']))}; casos {_cell(', '.join(subset['case_ids']))}; perfis fora desta comparação {_cell(', '.join(subset['excluded_profile_ids']) or 'nenhum')}."]
        for pair in comparison["pairs"]:
            lines += ["", f"Par {_cell(pair['profile_a'])} / {_cell(pair['profile_b'])}: casos correspondentes {_cell(', '.join(pair['case_ids']) or 'nenhum')}; descrição por caso, sem significância estatística."]
            if pair.get("excluded_cases"):
                lines += ["", f"Casos fora deste par: {_cell(', '.join(pair['excluded_cases']))}."]
            for case in pair["cases"]:
                q, t = case["quality_ordinal_difference"], case["execution_seconds_advantage_a"]
                lines += ["", f"- Caso {_cell(case['case_id'])}: diferença ordinal de qualidade do primeiro perfil {_signed_value(q['median'])} (mínimo {_signed_value(q['minimum'])}, máximo {_signed_value(q['maximum'])}); vantagem de execução do primeiro em segundos {_signed_value(t['median'])} (mínimo {_signed_value(t['minimum'])}, máximo {_signed_value(t['maximum'])})."]
            if pair.get("human_pairwise_feedback"):
                lines += ["", f"Preferências humanas pareadas, separadas: {_cell(pair['human_pairwise_feedback'])}."]
    aggregate = report["recommendation"]
    lines += ["", "## Recomendação geral contextual", ""]
    if aggregate["general_winner"] is not None:
        lines += [f"Projeção provisória: {_cell(aggregate['general_winner'])} apresentou menor esforço humano total na distribuição de ações declarada, além da margem prática. A conclusão vale apenas para os candidatos comparáveis observados.", ""]
    elif aggregate["aggregate_status"] == "provisional_projection_practical_tie":
        lines += [f"Projeção inconclusiva por empate prático: {_cell(', '.join(aggregate['practical_tie_profile_ids']))}. Nenhuma recomendação única.", ""]
    else:
        lines += ["Agregação geral indisponível: faltam pesos positivos representáveis, margem prática ou feedback pessoal completo em candidatos comparáveis.", ""]
    lines += [f"Pesos de ações congelados, normalizados: {_cell(aggregate['normalized_action_weights'])}. Margem prática em minutos de esforço humano: {_value(aggregate['personal_time_margin_minutes'])}.", ""]
    if aggregate["candidates"]:
        lines += ["| Candidato observado | Média ponderada do esforço humano total em minutos |", "| --- | ---: |"]
        lines.extend(f"| {_cell(candidate['profile_id'])} | {_value(candidate['weighted_mean_total_human_minutes'])} |" for candidate in aggregate["candidates"])
        lines.append("")
    for exclusion in aggregate["exclusions"]:
        lines += [f"- Fora da projeção geral: {_cell(exclusion['profile_id'])}, por evidência técnica ou pessoal incompleta nas ações ponderadas."]
    lines += ["", "A projeção usa somente esforço humano total observado; não mistura notas, custos ou latência do modelo. Não demonstra calibração humana universal e não altera rotas automaticamente.", "", "## Limites", "",
              "- Repetições medem estabilidade no mesmo caso; não acrescentam casos independentes.",
              "- A ausência de auditoria, preferência, aceitação ou tempo humano permanece desconhecida.",
              "- Concordância de juízes não demonstra verdade nem calibração pessoal.",
              "- A descrição por casos preserva dispersão e não produz significância estatística artificial.",
              "- Pareto exige casos correspondentes e margens práticas congeladas; permanece descritivo e provisório.",
              "- Identidade e esforço solicitados não confirmam a configuração efetivamente servida.",
              "- A triagem textual não qualifica fluxos completos nem instala mudanças nas rotas padrão."]
    return "\n".join(lines) + "\n"


def _signed_value(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "desconhecido"
    try:
        return f"{value:g}" if math.isfinite(value) else "desconhecido"
    except OverflowError:
        return "desconhecido"
