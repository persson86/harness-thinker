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

    def invoke(self, *args, **extra_env):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        env.pop("THINKER_SEARCH_ENGINE", None)
        env.update(extra_env)
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

    def configure(self, **changes):
        config = json.loads((self.root / "vault.config.json").read_text(encoding="utf-8"))
        config.update(changes)
        (self.root / "vault.config.json").write_text(json.dumps(config), encoding="utf-8")

    def set_created(self, rel, created):
        path = self.root / "wiki" / rel
        text = path.read_text(encoding="utf-8").replace("created: 2020-01-01\n", created)
        path.write_text(text, encoding="utf-8")

    def wiki_hashes(self):
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((self.root / "wiki").rglob("*.md"))}

    def test_monthly_sources_split_by_slug_date_then_created(self):
        self.configure(subsharded=["fast"], monthly_sources=["fast"])
        self.page("fast/2026-09-10-reuniao.md", typ="source", knowledge_status="historical", superseded_by="current")
        self.page("fast/2026-10-01-outra.md", typ="source")
        self.page("fast/2026-01-sem-dia.md", typ="source")
        self.page("fast/fonte-sem-data-no-slug.md", typ="source")
        self.set_created("fast/fonte-sem-data-no-slug.md", "created: 2026-08-05\n")
        self.page("fast/fonte-sem-data-alguma.md", typ="source")
        self.set_created("fast/fonte-sem-data-alguma.md", "")
        self.page("fast/pessoa.md", typ="entity")
        self.assertEqual(self.invoke("generate").returncode, 0)
        wiki = self.root / "wiki/fast"
        self.assertFalse((wiki / "_index-source.md").exists())
        for month in ("2026-10", "2026-09", "2026-08", "2026-01", "sem-data"):
            self.assertTrue((wiki / ("_index-source-%s.md" % month)).exists(), month)
        self.assertIn("[[fonte-sem-data-no-slug]]", (wiki / "_index-source-2026-08.md").read_text(encoding="utf-8"))
        self.assertIn("[[fonte-sem-data-alguma]]", (wiki / "_index-source-sem-data.md").read_text(encoding="utf-8"))
        september = (wiki / "_index-source-2026-09.md").read_text(encoding="utf-8")
        self.assertIn("# Fast — Fontes — 2026-09", september)
        self.assertIn("[[2026-09-10-reuniao]] — Resumo **[histórico; estado posterior: current]**", september)
        thin = (wiki / "_index.md").read_text(encoding="utf-8")
        self.assertIn("- **Fontes** `5 páginas`, por mês:", thin)
        order = [thin.index("_index-source-%s.md" % m) for m in ("2026-10", "2026-09", "2026-08", "2026-01", "sem-data")]
        self.assertEqual(order, sorted(order))
        self.assertIn("_index-entity.md", thin)
        before = self.wiki_hashes()
        self.assertEqual(self.invoke("generate").returncode, 0)
        self.assertEqual(self.wiki_hashes(), before)
        self.assertEqual(self.invoke("check").returncode, 0)

    def test_monthly_sources_removed_from_config_is_drift_until_generate(self):
        self.configure(subsharded=["fast"], monthly_sources=["fast"])
        self.page("fast/2026-09-10-reuniao.md", typ="source")
        self.assertEqual(self.invoke("generate").returncode, 0)
        self.configure(monthly_sources=[])
        check = self.invoke("check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("fast/_index-source-2026-09.md (deveria sumir)", check.stdout)
        self.assertIn("fast/_index-source.md (ausente)", check.stdout)
        self.assertEqual(self.invoke("generate").returncode, 0)
        self.assertFalse((self.root / "wiki/fast/_index-source-2026-09.md").exists())
        self.assertEqual(self.invoke("check").returncode, 0)

    def test_monthly_sources_outside_subsharded_is_ignored(self):
        self.configure(monthly_sources=["fast"])
        self.page("fast/2026-09-10-reuniao.md", typ="source")
        self.assertEqual(self.invoke("generate").returncode, 0)
        self.assertEqual(sorted(p.name for p in (self.root / "wiki/fast").glob("_index*.md")), ["_index.md"])
        self.assertIn("[[2026-09-10-reuniao]]", (self.root / "wiki/fast/_index.md").read_text(encoding="utf-8"))

    def test_thresholds_watch_the_biggest_month(self):
        self.configure(subsharded=["fast"], monthly_sources=["fast"])
        for i in range(160):
            self.page("fast/2026-%s-%02d-fonte-%03d.md" % ("09" if i % 2 else "10", i % 28 + 1, i), typ="source")
        self.assertEqual(self.invoke("generate").returncode, 0)
        split = self.invoke("thresholds")
        self.assertEqual(split.returncode, 0, split.stdout)
        for i in range(0, 160, 2):
            src = self.root / ("wiki/fast/2026-10-%02d-fonte-%03d.md" % (i % 28 + 1, i))
            src.rename(src.with_name(src.name.replace("2026-10-", "2026-09-")))
        self.assertEqual(self.invoke("generate").returncode, 0)
        crowded = self.invoke("thresholds")
        self.assertEqual(crowded.returncode, 1)
        self.assertIn("sub-shard fast/_index-source-2026-09.md", crowded.stdout)

    def test_thresholds_page_count_only_trips_without_fts5(self):
        cats = ["c%d" % i for i in range(6)]
        self.configure(categories=[[c, c.upper(), "escopo"] for c in cats], fast_spheres=[], inbox_dir="c0/inbox")
        for n in range(801):
            self.page("%s/p%03d.md" % (cats[n % 6], n))
        self.assertEqual(self.invoke("generate").returncode, 0)
        fts = self.invoke("thresholds")
        self.assertEqual(fts.returncode, 0, fts.stdout)
        self.assertIn("busca já em FTS5/BM25; contagem só informativa", fts.stdout)
        self.assertNotIn("avaliar FTS5", fts.stdout)
        legacy = self.invoke("thresholds", THINKER_SEARCH_ENGINE="legacy")
        self.assertEqual(legacy.returncode, 1)
        self.assertIn("total 801 páginas (> 800) com busca legado forçado → avaliar FTS5", legacy.stdout)

    def test_review_literal_finds_unlinked_restatements_without_writing(self):
        self.page("fast/target.md", body="A versão vigente é v9.0.0.")
        self.page("fast/linked.md", body="Ver [[target]]: a versão é v8.3.2.")
        self.page("fast/unlinked.md", body="Linha um\nA versão é V8.3.2 desde junho.")
        self.page("slow/historical.md", body="Em junho era v8.3.2.", knowledge_status="historical")
        self.page("slow/regex-trap.md", body="Nada de v8x3y2 aqui.")
        self.page("slow/accent.md", body="Revisão em São Paulo.")
        for n in range(30):
            self.page("slow/many-%02d.md" % n, body="também v8.3.2")
        self.page("slow/target.md")
        self.assertEqual(self.invoke("review", "target", "--literal", "v8.3.2").returncode, 2)
        (self.root / "wiki/slow/target.md").unlink()
        before = self.wiki_hashes()
        review = self.invoke("review", "target", "--literal", "v8.3.2", "--literal", "sao paulo")
        self.assertEqual(review.returncode, 0, review.stdout)
        self.assertEqual(self.wiki_hashes(), before)
        out = review.stdout
        self.assertIn('[[linked]] (fast; sem status declarado) — wikilink no corpo; literal "v8.3.2" (linha 12)', out)
        self.assertEqual(out.count("[[linked]]"), 1)
        self.assertIn('[[unlinked]] (fast; sem status declarado) — literal "v8.3.2" (linha 13)', out)
        self.assertIn('[[historical]] (slow; histórico) — literal "v8.3.2"', out)
        self.assertIn('[[accent]] (slow; sem status declarado) — literal "sao paulo"', out)
        self.assertNotIn("[[regex-trap]]", out)
        self.assertEqual(sum(out.count("[[many-%02d]]" % n) for n in range(30)), 30)
        self.assertIn("complemente com `search`", out)

    def test_review_literal_requires_a_value(self):
        self.page("fast/target.md")
        self.assertEqual(self.invoke("review", "target", "--literal").returncode, 2)
        self.assertEqual(self.invoke("review", "target", "--literal", "  ").returncode, 2)
        self.assertEqual(self.invoke("review", "--literal", "x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
