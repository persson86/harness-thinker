#!/usr/bin/env python3
"""Validate the deterministic surface of a Thinker model-eval response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def load_response(args: argparse.Namespace) -> str:
    raw = read_text(args.result_json or args.response)
    if args.result_json:
        outer = json.loads(raw)
        try:
            text = outer["result"]["text"]
        except (KeyError, TypeError):
            raise ValueError("result JSON must contain result.text") from None
        if not isinstance(text, str):
            raise ValueError("result.text must be a string")
        return text
    return raw


def extract_json(text: str) -> tuple[object, str, str]:
    stripped = text.strip()
    for marker in (chr(96) * 3, "~~~"):
        if stripped.startswith(marker) and stripped.endswith(marker):
            body = stripped[len(marker) : -len(marker)].strip()
            if body.lower().startswith("json"):
                body = body[4:].lstrip()
            stripped = body
            break
    start = stripped.find("{")
    if start < 0:
        raise ValueError("response does not contain a JSON object")
    value, end = json.JSONDecoder().raw_decode(stripped[start:])
    return value, stripped[:start].strip(), stripped[start + end :].strip()


def require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def validate_spec(spec: object) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    expected_ids = require_string_list(spec.get("expected_ids"), "expected_ids")
    if not expected_ids:
        raise ValueError("expected_ids must not be empty")
    if "allowed_evidence_ids" not in spec:
        raise ValueError("allowed_evidence_ids is required")
    allowed_evidence = require_string_list(spec["allowed_evidence_ids"], "allowed_evidence_ids")
    if not allowed_evidence:
        raise ValueError("allowed_evidence_ids must not be empty")
    max_words = spec.get("max_words")
    if not isinstance(max_words, int) or isinstance(max_words, bool) or max_words <= 0:
        raise ValueError("max_words must be a positive integer")
    if "action_fields" not in spec:
        raise ValueError("action_fields is required")
    action_fields = spec["action_fields"]
    if not isinstance(action_fields, dict):
        raise ValueError("action_fields must be an object")
    normalized_actions = {}
    for field, allowed in action_fields.items():
        if not isinstance(field, str) or not field:
            raise ValueError("action field names must be non-empty strings")
        normalized_actions[field] = require_string_list(allowed, f"action_fields.{field}")
    required_action_fields = {"claim_action", "corrected_evidence_action"}
    missing_action_fields = sorted(required_action_fields - set(normalized_actions))
    if missing_action_fields:
        raise ValueError("action_fields missing required fields: " + ", ".join(missing_action_fields))
    expected_actions = spec.get("expected_actions", {})
    if not isinstance(expected_actions, dict):
        raise ValueError("expected_actions must be an object")
    unknown = sorted(set(expected_actions) - set(expected_ids))
    if unknown:
        raise ValueError("expected_actions contains unknown IDs: " + ", ".join(unknown))
    for identifier, fields in expected_actions.items():
        if not isinstance(fields, dict):
            raise ValueError(f"expected_actions.{identifier} must be an object")
        for field, expected in fields.items():
            if field not in normalized_actions:
                raise ValueError(f"expected_actions.{identifier} contains unknown field {field}")
            if expected not in normalized_actions[field]:
                raise ValueError(f"expected_actions.{identifier}.{field} is not an allowed action")
    return {
        "expected_ids": expected_ids,
        "allowed_evidence_ids": allowed_evidence,
        "max_words": max_words,
        "action_fields": normalized_actions,
        "expected_actions": expected_actions,
    }


def evaluate(response: object, text: str, spec: dict, prefix: str, suffix: str) -> dict:
    errors: list[str] = []
    if not isinstance(response, dict):
        raise ValueError("response JSON must be an object")
    findings = response.get("findings")
    if not isinstance(findings, list):
        raise ValueError("response.findings must be a list")

    ids: list[str] = []
    action_matches = 0
    action_total = 0
    invalid_actions = []
    invalid_evidence = []
    allowed_evidence = set(spec["allowed_evidence_ids"])

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} is not an object")
            continue
        identifier = finding.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"finding {index} has invalid id")
            continue
        ids.append(identifier)
        for field in ("defect", "epistemic_state"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                errors.append(f"{identifier}.{field} must be a non-empty string")
        evidence = finding.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(item, str) and item for item in evidence)
        ):
            errors.append(f"{identifier}.evidence must be a non-empty string list")
        else:
            invalid_evidence.extend(
                {"id": identifier, "evidence": item}
                for item in evidence
                if item not in allowed_evidence
            )
        for field, allowed in spec["action_fields"].items():
            actual = finding.get(field)
            if actual not in allowed:
                invalid_actions.append({"id": identifier, "field": field, "value": actual})
            expected = spec["expected_actions"].get(identifier, {}).get(field)
            if expected is not None:
                action_total += 1
                if actual == expected:
                    action_matches += 1

    expected = spec["expected_ids"]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    missing = [item for item in expected if item not in ids]
    extra = sorted(set(ids) - set(expected))
    words = len(re.findall(r"\S+", text))
    structural_valid = not (
        errors or duplicates or missing or extra or invalid_actions or invalid_evidence or prefix or suffix
    )

    return {
        "structural_valid": structural_valid,
        "word_count": words,
        "max_words": spec["max_words"],
        "word_limit_valid": words <= spec["max_words"],
        "finding_count": len(findings),
        "expected_finding_count": len(expected),
        "missing_ids": missing,
        "extra_ids": extra,
        "duplicate_ids": duplicates,
        "invalid_actions": invalid_actions,
        "invalid_evidence_ids": invalid_evidence,
        "action_matches": action_matches,
        "action_total": action_total,
        "extra_text_before_json": prefix,
        "extra_text_after_json": suffix,
        "errors": errors,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--spec", required=True, help="Path to the frozen JSON evaluation spec")
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument("--response", help="Response text path, or - for stdin")
    source.add_argument("--result-json", help="delegate.py --json result output path, or - for stdin")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        spec = validate_spec(json.loads(Path(args.spec).read_text(encoding="utf-8")))
        text = load_response(args)
        response, prefix, suffix = extract_json(text)
        report = evaluate(response, text, spec, prefix, suffix)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"structural_valid": False, "fatal_error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["structural_valid"] and report["word_limit_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
