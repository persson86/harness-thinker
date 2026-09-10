"""Deterministic contract tests for keyword search parsing and ranking."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "payload/.claude/scripts/build-index.py"


class KnowledgeSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "wiki/notes").mkdir(parents=True)
        (self.root / "vault.config.json").write_text(json.dumps({
            "categories": [["notes", "Notes", "test"]],
            "subsharded": [], "fast_spheres": [], "inbox_dir": "notes/inbox",
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, slug, title, summary, body="", status=None):
        lines = ["---", "title: %s" % title, "summary: %s" % summary,
                 "category: notes", "type: concept", "tags: []",
                 "created: 2020-01-01", "updated: 2020-01-01"]
        if status:
            lines.append("knowledge_status: %s" % status)
        lines += ["---", "", body]
        (self.root / "wiki/notes" / ("%s.md" % slug)).write_text(
            "\n".join(lines), encoding="utf-8")

    def invoke(self, *args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        return subprocess.run(["python3", str(SCRIPT), *args], env=env,
                              text=True, capture_output=True, check=False)

    def slugs(self, result):
        return re.findall(r"\[\[([^]]+)\]\]", result.stdout)

    def test_accents_and_exact_phrase(self):
        self.page("formal", "Separação formal", "Processo de separação formal")
        self.page("separate", "Separação", "Processo de separação", "formal aparece longe")
        self.page("prefix", "Separação formalização", "Sem a frase exata")
        self.page("agua", "Água", "d'água")
        broad = self.invoke("search", "separacao formal")
        phrase = self.invoke("search", '"separação formal"')
        self.assertEqual(broad.returncode, 0)
        self.assertEqual(phrase.returncode, 0)
        self.assertIn("formal", self.slugs(phrase))
        self.assertNotIn("separate", self.slugs(phrase))
        self.assertNotIn("prefix", self.slugs(phrase))
        self.assertEqual(self.invoke("search", "d'agua").returncode, 0)
        self.assertEqual(self.slugs(self.invoke("search", "d'agua")), ["agua"])
        self.assertEqual(self.slugs(self.invoke("search", "separacao")),
                         self.slugs(self.invoke("search", "separação")))

    def test_all_requires_every_term_and_default_is_or(self):
        self.page("one", "Alpha", "alpha")
        self.page("two", "Beta", "beta")
        self.page("both", "Alpha Beta", "alpha beta")
        self.assertEqual(set(self.slugs(self.invoke("search", "alpha beta"))), {"one", "two", "both"})
        self.assertEqual(set(self.slugs(self.invoke("search", "--all", "alpha beta"))), {"both"})
        reordered = self.slugs(self.invoke("search", "--all", "beta alpha"))
        self.assertEqual(reordered, self.slugs(self.invoke("search", "--all", "alpha beta")))

    def test_unicode_quotes_malformed_query_and_status_badges(self):
        self.page("current", "Atual", "separação formal", status="current")
        self.page("historical", "Histórico", "separação formal", status="historical")
        self.assertEqual(self.invoke("search", '“separação formal”').returncode, 0)
        malformed = self.invoke("search", '“separação formal')
        self.assertEqual(malformed.returncode, 2)
        self.assertIn("aspas não fechadas", malformed.stdout)
        trailing = self.invoke("search", 'separação formal”')
        self.assertEqual(trailing.returncode, 2)
        for query in ('separação formal"', '"separação"formal', 'abc“def'):
            self.assertEqual(self.invoke("search", query).returncode, 2, query)
        output = self.invoke("search", "separacao").stdout
        self.assertIn("[atual]", output)
        self.assertIn("[histórico]", output)

    def test_fixed_retrieval_set_compares_legacy_and_new_hit_at_5(self):
        # Held-fixed synthetic corpus: eight pages, eight queries, known labels.
        records = [
            ("p0", "Dados", "separação formal"), ("p1", "Dados", "separacao formal"),
            ("p2", "Dados", "governança"), ("p3", "Formal", "processo"),
            ("p4", "Busca", "café"), ("p5", "Busca", "governanca"),
            ("p6", "Estado", "não determinístico"), ("p7", "Design", "design"),
        ]
        for slug, title, summary in records:
            self.page(slug, title, summary)
        cases = [("separacao formal", {"p0", "p1"}),
                 ('"separação formal"', {"p0", "p1"}), ("governanca", {"p2", "p5"}),
                 ("separação formal", {"p0", "p1"}), ("cafe", {"p4"}), ("nao", {"p6"}),
                 ("processo", {"p3"}), ("design", {"p7"})]

        def legacy_rank(query):
            terms = query.lower().split()
            ranked = []
            for slug, title, summary in records:
                fields = (title.lower(), summary.lower(), "", "")
                score = sum(weight * (term in value)
                            for term in terms for value, weight in zip(fields, (5, 3, 2, 1)))
                if score:
                    ranked.append((score, slug))
            return [slug for _score, slug in sorted(ranked, key=lambda row: (-row[0], row[1]))]

        before = {p: hashlib.sha256(p.read_bytes()).digest()
                  for p in self.root.glob("wiki/**/*.md")}
        baseline_hits = improved_hits = 0
        for query, relevant in cases:
            baseline_hits += bool(set(legacy_rank(query)[:5]) & relevant)
            improved_hits += bool(set(self.slugs(self.invoke("search", query))[:5]) & relevant)
        after = {p: hashlib.sha256(p.read_bytes()).digest()
                 for p in self.root.glob("wiki/**/*.md")}
        self.assertEqual(before, after)
        self.assertEqual((baseline_hits, improved_hits), (5, 8))


if __name__ == "__main__":
    unittest.main()
