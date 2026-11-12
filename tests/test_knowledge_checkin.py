"""Deterministic tests for `build-index.py checkin` (open subjects for the weekly round)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "payload/.claude/scripts/build-index.py"
TODAY = "2026-11-12"


class CheckinBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "wiki/work/sources").mkdir(parents=True)
        (self.root / "vault.config.json").write_text(json.dumps({
            "categories": [["work", "Work", "test"]],
            "subsharded": [], "fast_spheres": [], "inbox_dir": "work/inbox",
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, slug, body, typ="entity", status="current", as_of="2026-11-10", folder=""):
        lines = ["---", "title: \"%s\"" % slug, "summary: s", "category: work", "type: %s" % typ,
                 "tags: []", "sources: []", "created: 2026-01-01", "updated: %s" % as_of]
        if status:
            lines += ["knowledge_status: %s" % status, "as_of: %s" % as_of]
        lines += ["---", "", body]
        path = self.root / "wiki/work" / folder / ("%s.md" % slug)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def invoke(self, *args, today=TODAY):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "THINKER_TODAY": today}
        return subprocess.run(["python3", str(SCRIPT), "checkin", *args], env=env,
                              text=True, capture_output=True, check=False)

    def report(self, *args):
        result = self.invoke("--json", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def lines_for(self, data, slug):
        for row in data["open"]:
            if row["slug"] == slug:
                return row["items"]
        return []


HUB = """# Conta

## Estado vigente (20/out/2026)

O próximo marco é a reunião com o cliente em 30/out.

## Decisões abertas

- Contratação do PM: pedida em 15/out, sem resposta.
- Visita do cliente em 16/nov para fechar o escopo.
- Proposta enviada em 10/nov; aguardando.

## Movimento recente

- **28/out:** prazo de entrega previsto para 29/out foi cumprido.
"""


class CheckinCandidatesTest(CheckinBase):
    def test_open_section_and_forward_marker_with_past_dates(self):
        self.page("conta", HUB)
        items = self.lines_for(self.report(), "conta")
        kinds = {item["excerpt"][:30]: item["kind"] for item in items}
        self.assertIn("marco vencido", kinds.values())
        self.assertTrue(any("Contratação do PM" in item["excerpt"] for item in items))
        # Futuro e passado recente (dentro da carência) não são perguntas ainda.
        self.assertFalse(any("16/nov" in item["excerpt"] for item in items))
        self.assertFalse(any("10/nov" in item["excerpt"] for item in items))
        # Movimento recente é histórico, mesmo com "previsto".
        self.assertFalse(any("cumprido" in item["excerpt"] for item in items))

    def test_reconcile_when_state_heading_predates_as_of(self):
        self.page("conta", HUB, as_of="2026-11-10")
        data = self.report()
        self.assertEqual([r["slug"] for r in data["reconcile"]], ["conta"])
        self.assertEqual(data["reconcile"][0]["state_date"], "2026-10-20")

    def test_only_live_entities_count(self):
        self.page("conceito", HUB, typ="concept")
        self.page("antiga", HUB, status="historical")
        self.page("2026-10-01-reuniao", HUB, typ="source", folder="sources")
        data = self.report()
        self.assertEqual(data["open"], [])
        self.assertEqual(data["reconcile"], [])

    def test_forward_word_needs_a_nearby_date(self):
        self.page("conta", "# Conta\n\n**Como manter (convenção de 24/out/2026).** Um prazo novo entra na tabela.\n")
        self.assertEqual(self.lines_for(self.report(), "conta"), [])

    def test_table_header_is_not_a_candidate(self):
        body = "# Conta\n\n## Pendências\n\n| Tema | Estado em 24/out |\n|---|---|\n| Preço | sem decisão desde 20/out |\n"
        self.page("conta", body)
        excerpts = [i["excerpt"] for i in self.lines_for(self.report(), "conta")]
        self.assertEqual(len(excerpts), 1)
        self.assertIn("Preço", excerpts[0])

    def test_year_is_inferred_near_as_of(self):
        body = "# Conta\n\n## Pendências\n\n- Renovação combinada para 15/jan.\n"
        self.page("conta", body, as_of="2026-11-10")
        # 15/jan perto de nov/2026 é jan/2027: futuro, não candidato.
        self.assertEqual(self.lines_for(self.report(), "conta"), [])

    def test_ranking_by_inbound_links(self):
        self.page("menor", "# Menor\n\n## Pendências\n\n- Algo de 01/out.\n")
        self.page("maior", "# Maior\n\n## Pendências\n\n- Algo de 01/out.\n")
        self.page("cita", "# Cita\n\n[[maior]] e [[maior|de novo]]\n", typ="concept")
        slugs = [r["slug"] for r in self.report()["open"]]
        self.assertEqual(slugs, ["maior", "menor"])


class CheckinReviewRegressionTest(CheckinBase):
    """Casos reproduzidos pelo Reviewer antes da publicação de 7.23.11."""

    def test_closed_line_does_not_come_back_after_grace(self):
        body = ("# Conta\n\n## Pendências\n\n"
                "- Visita prevista para 30/out; não aconteceu, nada relevante, item encerrado em 12/nov/2026.\n")
        self.page("conta", body)
        for today in (TODAY, "2026-11-19", "2026-12-20"):
            data = json.loads(self.invoke("--json", today=today).stdout)
            self.assertEqual(self.lines_for(data, "conta"), [], today)

    def test_past_cue_keeps_old_pending_item_in_the_past(self):
        body = "# Conta\n\n## Pendências\n\n- Aguardando resposta desde 15/jan.\n"
        self.page("conta", body, as_of="2026-11-10")
        items = self.lines_for(self.report(), "conta")
        self.assertEqual([i["latest"] for i in items], ["2026-01-15"])

    def test_leap_day_takes_the_nearest_valid_year(self):
        body = "# Conta\n\n## Pendências\n\n- Assinatura pedida em 29/fev, sem retorno.\n"
        self.page("conta", body, as_of="2023-12-20")
        data = json.loads(self.invoke("--json", today="2024-04-01").stdout)
        self.assertEqual([i["latest"] for i in self.lines_for(data, "conta")], ["2024-02-29"])

    def test_heading_that_names_open_items_wins_over_history_word(self):
        body = "# Conta\n\n## Registro de pendências\n\n- Aguardando aprovação desde 2026-10-01.\n"
        self.page("conta", body)
        self.assertEqual(len(self.lines_for(self.report(), "conta")), 1)

    def test_wrongly_typed_state_counts_as_empty(self):
        for raw in ('{"last_run": 123}', '{"last_run": "9999-12-31"}',
                    '{"last_run": "2026-11-01", "dismissed": ["x"]}', '[1, 2]'):
            (self.root / "checkin.json").write_text(raw, encoding="utf-8")
            result = self.invoke("--due")
            self.assertNotIn("Traceback", result.stderr, raw)
            self.assertIn(result.returncode, (0, 1), raw)
            self.assertEqual(self.invoke("--json").returncode, 0, raw)
        (self.root / "checkin.json").write_text('{"last_run": 123}', encoding="utf-8")
        self.assertEqual(self.invoke("--due").returncode, 0)

    def test_concurrent_writes_keep_every_dismissal_and_valid_json(self):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "THINKER_TODAY": TODAY}
        keys = ["conta:%08x" % i for i in range(24)]
        procs = [subprocess.Popen(["python3", str(SCRIPT), "checkin", "--dismiss", key], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                 for key in keys]
        procs += [subprocess.Popen(["python3", str(SCRIPT), "checkin", "--record"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                  for _ in range(8)]
        errors = [p.communicate()[1] for p in procs]
        self.assertTrue(all(p.returncode == 0 for p in procs), errors)
        state = json.loads((self.root / "checkin.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(state["dismissed"]), sorted(keys))
        self.assertEqual(state["last_run"], TODAY)
        leftovers = [p.name for p in self.root.iterdir() if p.name.startswith(".checkin-") or p.name.endswith(".lock")]
        self.assertEqual(leftovers, [])


class CheckinStateTest(CheckinBase):
    def test_due_record_and_next_week(self):
        self.assertEqual(self.invoke("--due").returncode, 0)
        self.assertEqual(self.invoke("--record").returncode, 0)
        state = json.loads((self.root / "checkin.json").read_text(encoding="utf-8"))
        self.assertEqual(state["last_run"], TODAY)
        self.assertEqual(self.invoke("--due").returncode, 1)
        self.assertEqual(self.invoke("--due", today="2026-11-18").returncode, 1)
        self.assertEqual(self.invoke("--due", today="2026-11-19").returncode, 0)

    def test_dismiss_hides_line_until_it_changes(self):
        path = self.page("conta", HUB)
        items = self.lines_for(self.report(), "conta")
        target = next(i for i in items if "Contratação" in i["excerpt"])
        self.assertEqual(self.invoke("--dismiss", target["key"]).returncode, 0)
        keys = [i["key"] for i in self.lines_for(self.report(), "conta")]
        self.assertNotIn(target["key"], keys)
        # Editar a linha gera chave nova: o item volta se ainda estiver vencido.
        path.write_text(path.read_text(encoding="utf-8").replace(
            "sem resposta", "ainda sem resposta"), encoding="utf-8")
        excerpts = [i["excerpt"] for i in self.lines_for(self.report(), "conta")]
        self.assertTrue(any("ainda sem resposta" in e for e in excerpts))

    def test_dismiss_rejects_malformed_keys(self):
        self.assertEqual(self.invoke("--dismiss", "conta").returncode, 2)
        self.assertFalse((self.root / "checkin.json").exists())

    def test_unreadable_state_counts_as_empty(self):
        (self.root / "checkin.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.invoke("--due").returncode, 0)
        self.assertEqual(self.report()["last_run"], None)

    def test_text_report_prints_keys(self):
        self.page("conta", HUB)
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[[conta]]", result.stdout)
        self.assertRegex(result.stdout, r"\{conta:[0-9a-f]{8}\}")


if __name__ == "__main__":
    unittest.main()
