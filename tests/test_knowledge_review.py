#!/usr/bin/env python3
"""Black-box coverage for knowledge status, review and stale candidates."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "payload/.claude/scripts/build-index.py"


class KnowledgeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "wiki/fast").mkdir(parents=True)
        (self.root / "wiki/slow").mkdir(parents=True)
        (self.root / "wiki/fast/inbox").mkdir(parents=True)
        (self.root / "vault.config.json").write_text(json.dumps({
            "categories": [["fast", "Fast", "rápida"], ["slow", "Slow", "lenta"]],
            "subsharded": [], "fast_spheres": ["fast"], "inbox_dir": "fast/inbox",
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, rel, title=None, summary="Resumo", typ="entity", body="", sources=None, **meta):
        lines = ["---", "title: %s" % (title or Path(rel).stem), "summary: %s" % summary,
                 "category: %s" % Path(rel).parts[0], "type: %s" % typ,
                 "tags: []", "sources: %s" % (sources or "[]"), "created: 2020-01-01", "updated: 2020-01-01"]
        lines.extend("%s: %s" % item for item in meta.items())
        lines += ["---", "", body]
        path = self.root / "wiki" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    def invoke(self, *args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        return subprocess.run(["python3", str(SCRIPT), *args], env=env,
                              text=True, capture_output=True, check=False)

    def test_status_badges_search_and_legacy_pages(self):
        self.page("fast/current.md", summary="needle atual", knowledge_status="current", as_of="2026-09-01")
        self.page("fast/old.md", summary="needle antigo", knowledge_status="historical", as_of="2021-01-01", superseded_by="current")
        self.page("fast/replaced.md", summary="needle superado", knowledge_status="superseded", superseded_by="current")
        self.page("fast/legacy.md", summary="needle legado")
        self.assertEqual(self.invoke("generate").returncode, 0)
        index = (self.root / "wiki/fast/_index.md").read_text(encoding="utf-8")
        self.assertIn("**[atual; estado em 2026-09-01]**", index)
        self.assertIn("**[histórico; estado em 2021-01-01; estado posterior: current]**", index)
        self.assertIn("**[superado; substituído por current]**", index)
        self.assertIn("[[legacy]] — needle legado\n", index)
        search = self.invoke("search", "needle")
        self.assertEqual(search.returncode, 0)
        self.assertIn("[histórico; estado em 2021-01-01; estado posterior: current]", search.stdout)
        self.assertIn("[superado; substituído por current]", search.stdout)
        self.assertEqual(self.invoke("check").returncode, 0)
        generated_before = {
            path.relative_to(self.root): path.read_text(encoding="utf-8")
            for path in self.root.glob("wiki/**/_index*.md")
        }
        generated_before[Path("wiki/index.md")] = (self.root / "wiki/index.md").read_text(encoding="utf-8")
        self.assertEqual(self.invoke("generate").returncode, 0)
        generated_after = {
            path.relative_to(self.root): path.read_text(encoding="utf-8")
            for path in self.root.glob("wiki/**/_index*.md")
        }
        generated_after[Path("wiki/index.md")] = (self.root / "wiki/index.md").read_text(encoding="utf-8")
        self.assertEqual(generated_before, generated_after)
        self.assertEqual(self.invoke("check").returncode, 0)

    def test_review_body_sources_and_code_are_distinguished(self):
        self.page("fast/target.md", knowledge_status="current")
        self.page("fast/body.md", body="Veja [[target]].", knowledge_status="historical")
        self.page("slow/source.md", sources="[target, outra]", body="Contexto.")
        self.page("slow/code.md", body="```bash\nteste [[target]]\n```\n`[[target]]`")
        fragment = self.root / "wiki/fast/inbox/fragment.md"
        fragment.write_text("Rascunho [[target|apelido]] e [[target#seção]].", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.root.glob("wiki/**/*.md")}
        before_hashes = {path: hashlib.sha256(content).hexdigest() for path, content in before.items()}
        review = self.invoke("review", "target")
        self.assertEqual(review.returncode, 0)
        self.assertIn("[[target]] — status: atual", review.stdout)
        self.assertIn("[[body]] (fast; histórico) — wikilink no corpo", review.stdout)
        self.assertIn("[[source]] (slow; sem status declarado) — sources no frontmatter", review.stdout)
        self.assertIn("[[fragment]] (fast; sem status declarado) — wikilink no corpo", review.stdout)
        self.assertNotIn("[[code]]", review.stdout)
        self.assertIn("não prova ou correção automática", review.stdout)
        after = {path: path.read_bytes() for path in self.root.glob("wiki/**/*.md")}
        self.assertEqual(before, after)
        self.assertEqual(before_hashes, {path: hashlib.sha256(content).hexdigest() for path, content in after.items()})

    def test_review_rejects_missing_and_ambiguous_slugs(self):
        self.page("fast/duplicate.md")
        self.page("slow/duplicate.md")
        self.assertEqual(self.invoke("review", "missing").returncode, 2)
        self.assertEqual(self.invoke("review", "duplicate").returncode, 2)
        self.assertEqual(self.invoke("review", "fast/duplicate.md").returncode, 2)

    def test_stale_includes_insights_anywhere_but_skips_statuses_and_inbox(self):
        self.page("fast/entity.md", typ="entity")
        self.page("slow/insight.md", typ="insight")
        self.page("slow/historical-insight.md", typ="insight", knowledge_status="historical")
        self.page("fast/superseded-entity.md", typ="entity", knowledge_status="superseded")
        self.page("fast/inbox/inbox-insight.md", typ="insight")
        stale = self.invoke("stale", "--days", "1")
        self.assertEqual(stale.returncode, 0)
        self.assertIn("[[entity]]", stale.stdout)
        self.assertIn("[[insight]]", stale.stdout)
        self.assertNotIn("[[historical-insight]]", stale.stdout)
        self.assertNotIn("[[superseded-entity]]", stale.stdout)
        self.assertNotIn("[[inbox-insight]]", stale.stdout)

    def test_status_badge_is_rendered_in_subshard(self):
        config = json.loads((self.root / "vault.config.json").read_text(encoding="utf-8"))
        config["subsharded"] = ["fast"]
        (self.root / "vault.config.json").write_text(json.dumps(config), encoding="utf-8")
        self.page("fast/historical.md", typ="concept", knowledge_status="historical", superseded_by="current")
        self.assertEqual(self.invoke("generate").returncode, 0)
        subshard = (self.root / "wiki/fast/_index-concept.md").read_text(encoding="utf-8")
        self.assertIn("[[historical]] — Resumo **[histórico; estado posterior: current]**", subshard)
        self.assertEqual(self.invoke("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
