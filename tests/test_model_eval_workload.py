"""Public fixture guarantees only; never invoke a model or execute its code."""

import json
from collections import Counter
from pathlib import Path, PurePosixPath
import re
import unittest


REPO = Path(__file__).resolve().parents[1]
SUITE_ROOT = REPO / "payload" / "harness" / "evals" / "workload-v1"
FAMILIES = {"retrieval", "ingestion", "analysis", "research", "code", "communication"}
SLUG = re.compile(r"[a-z][a-z0-9-]*\Z")


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


class WorkloadFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = load_json(SUITE_ROOT / "suite.json")
        cls.cases = cls.suite["cases"]

    def declared_file(self, relative, directory, suffix):
        self.assertIsInstance(relative, str)
        path = PurePosixPath(relative)
        self.assertFalse(path.is_absolute())
        self.assertEqual(relative, path.as_posix())
        self.assertEqual(path.parts[0], directory)
        self.assertEqual(len(path.parts), 2)
        self.assertNotIn("..", path.parts)
        self.assertNotIn("\\", relative)
        self.assertEqual(path.suffix, suffix)
        current = SUITE_ROOT
        for component in path.parts:
            current /= component
            self.assertFalse(current.is_symlink(), relative)
        self.assertTrue(current.is_file(), relative)
        self.assertTrue(current.resolve().is_relative_to(SUITE_ROOT.resolve()))
        return current

    def test_coverage_is_twelve_cases_with_explicit_balanced_splits(self):
        self.assertEqual(self.suite["schema_version"], 1)
        self.assertEqual(self.suite["id"], "workload-v1")
        self.assertEqual(len(self.cases), 12)
        self.assertEqual({case["family"] for case in self.cases}, FAMILIES)
        self.assertEqual(
            Counter((case["family"], case["split"]) for case in self.cases),
            Counter({(family, split): 1 for family in FAMILIES
                     for split in ("development", "holdout")}),
        )
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for identifier in ids:
            self.assertRegex(identifier, SLUG)

    def test_all_candidate_inputs_are_bounded_regular_utf8_files(self):
        declared = set()
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(set(case),
                                 {"id", "family", "prompt", "rubric", "max_words", "split"})
                prompt = self.declared_file(case["prompt"], "cases", ".md")
                self.assertEqual(prompt.stem, case["id"])
                declared.add(prompt.name)
                data = prompt.read_bytes()
                self.assertGreater(len(data), 0)
                self.assertLessEqual(len(data), 6000)
                text = data.decode("utf-8")
                self.assertNotIn("\x00", text)
                ceiling = 700 if case["family"] == "code" else 450
                self.assertIs(type(case["max_words"]), int)
                self.assertGreater(case["max_words"], 0)
                self.assertLessEqual(case["max_words"], ceiling)
                self.assertIn(f"até {case['max_words']} palavras", text)
                self.assertIn("Screening de texto sintético delimitado", text)
        self.assertEqual(declared, {p.name for p in (SUITE_ROOT / "cases").iterdir()})

    def test_rubrics_have_independent_acceptance_criteria_and_reference_notes(self):
        declared = set()
        for case in self.cases:
            with self.subTest(case=case["id"]):
                rubric_path = self.declared_file(case["rubric"], "rubrics", ".json")
                self.assertEqual(rubric_path.stem, case["id"])
                declared.add(rubric_path.name)
                rubric = load_json(rubric_path)
                self.assertEqual(set(rubric), {"criteria", "reference_notes"})
                self.assertIsInstance(rubric["criteria"], list)
                self.assertGreaterEqual(len(rubric["criteria"]), 3)
                self.assertGreater(len(rubric["reference_notes"].strip()), 100)
                seen = set()
                for criterion in rubric["criteria"]:
                    self.assertEqual(set(criterion), {"id", "description", "critical"})
                    self.assertRegex(criterion["id"], SLUG)
                    self.assertNotIn(criterion["id"], seen)
                    seen.add(criterion["id"])
                    self.assertIs(type(criterion["critical"]), bool)
                    self.assertGreater(len(criterion["description"].strip()), 30)
                self.assertTrue(any(c["critical"] for c in rubric["criteria"]))
                self.assertTrue(any(not c["critical"] for c in rubric["criteria"]))
        self.assertEqual(declared, {p.name for p in (SUITE_ROOT / "rubrics").iterdir()})

    def test_hidden_material_is_separate_from_candidate_prompt(self):
        all_prompts = "\n".join((SUITE_ROOT / case["prompt"]).read_text(encoding="utf-8")
                                for case in self.cases)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                prompt = SUITE_ROOT / case["prompt"]
                rubric_path = SUITE_ROOT / case["rubric"]
                self.assertNotEqual(prompt.resolve(), rubric_path.resolve())
                self.assertNotEqual(prompt.stat().st_ino, rubric_path.stat().st_ino)
                rubric = load_json(rubric_path)
                self.assertNotIn(rubric["reference_notes"], all_prompts)
                for criterion in rubric["criteria"]:
                    self.assertNotIn(criterion["description"], all_prompts)
                self.assertNotIn(case["rubric"], all_prompts)
        self.assertNotIn('"reference_notes"', all_prompts)
        self.assertNotIn('"criteria"', all_prompts)

    def test_public_fixtures_do_not_embed_machine_paths_or_external_fetches(self):
        for path in SUITE_ROOT.rglob("*"):
            if not path.is_file():
                continue
            with self.subTest(path=str(path.relative_to(SUITE_ROOT))):
                self.assertFalse(path.is_symlink())
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"/(?:Users|home|private|tmp|var)/")
                self.assertNotRegex(text, r"[A-Za-z]:\\")
                self.assertNotRegex(text, r"(?:https?://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})")

    def test_readme_states_scope_and_holdout_limits(self):
        readme = (SUITE_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("screening de texto sintético delimitado", readme)
        self.assertIn("Não qualifica execução", readme)
        self.assertIn("decisão explícita", readme)
        self.assertIn("três", readme)
        self.assertIn("não pontuação automática", readme)


if __name__ == "__main__":
    unittest.main()
