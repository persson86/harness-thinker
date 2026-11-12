"""Deterministic tests for the people registry, resolver, people-check and quotes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "payload/.claude/scripts/build-index.py"


class KnowledgeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "wiki/work").mkdir(parents=True)
        (self.root / "vault.config.json").write_text(json.dumps({
            "categories": [["work", "Work", "test"]],
            "subsharded": [], "fast_spheres": [], "inbox_dir": "work/inbox",
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, slug, body, typ="entity", extra=(), tags="[]", sources="[]",
             title=None, created="2020-01-01"):
        lines = ["---", "title: \"%s\"" % (title or slug), "summary: s", "category: work",
                 "type: %s" % typ, "tags: %s" % tags, "sources: %s" % sources]
        lines += list(extra)
        lines += ["created: %s" % created, "updated: %s" % created, "---", "", body]
        (self.root / "wiki/work" / ("%s.md" % slug)).write_text("\n".join(lines), encoding="utf-8")

    def invoke(self, *args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        return subprocess.run(["python3", str(SCRIPT), *args], env=env,
                              text=True, capture_output=True, check=False)


MAP = """# Mapa

## Pessoas

### Beto Fonseca — Diretor de Design

**Desambiguação:** "Beto" em Design é Beto Fonseca; em People é Beto Brito.

- **Papel.** Design.

### Beto Brito — BP de People

- **Papel.** People.

### Mari (Mariana Mayer) — Head de CX

### Outros com peso

- **Meng (Thiago Mengue)** — TM da Wiz.
- **Clientes que pesam em decisões internas** — Romani e Júlio.
- **[[bruno]]** — externo.

## Lacunas

- **Fora** — não é pessoa do cadastro.
"""

HUB = """# Hub

## Pessoas e papéis citados

- **Thiago** — Tech Manager da conta.
- **Leonardo "Léo"** — DM.
- **Mari** — CS da conta.
- **Laura Giroleti (Laura)** — PM da conta.
  - Desambiguação: aqui "Laura" é ela. Outra frase que não entra.
- **Do lado do cliente:** Kátia e Vanessa.
"""


class PeopleRegistryTests(KnowledgeBase):
    def setUp(self):
        super().setUp()
        self.page("mapa", MAP, typ="concept", extra=['people_section: "Pessoas"'])
        self.page("hub", HUB, extra=['people_section: "Pessoas e papéis citados"'])
        self.page("beto-fonseca", "corpo", title="Beto Fonseca — Diretor",
                  extra=["aliases: [Beto, Roberto Fonseca]"])
        self.page("lider", "## Léo\n\n### Léo (Leonardo Gonçalves) — DM\n", typ="concept",
                  extra=['people_section: "Léo"'])

    def registry(self):
        result = self.invoke("people", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return {e["name"]: e for e in json.loads(result.stdout)}

    def test_registry_merges_page_section_and_exact_aliases(self):
        reg = self.registry()
        self.assertIn("Beto Fonseca", reg)
        self.assertEqual(sorted(reg["Beto Fonseca"]["where"]),
                         ["beto-fonseca", "mapa#Beto Fonseca — Diretor de Design"])
        self.assertIn("Roberto Fonseca", reg["Beto Fonseca"]["aliases"])
        self.assertEqual(len(reg["Beto Fonseca"]["rules"]), 1)
        self.assertIn("Mariana Mayer", reg)
        self.assertIn("hub#Pessoas e papéis citados", reg["Mariana Mayer"]["where"])
        self.assertNotIn("Clientes que pesam em decisões internas", reg)
        self.assertNotIn("Fora", reg)
        self.assertNotIn("Papel.", reg)

    def test_short_name_is_not_merged_by_first_name(self):
        reg = self.registry()
        self.assertIn("Thiago", reg)
        self.assertEqual(reg["Thiago Mengue"]["where"], ["mapa#Outros com peso"])

    def test_bullet_rule_stops_at_sentence(self):
        reg = self.registry()
        self.assertEqual(reg["Laura Giroleti"]["rules"], ['aqui "Laura" é ela.'])

    def test_resolve_exit_codes(self):
        unique = self.invoke("resolve", "Mari")
        self.assertEqual(unique.returncode, 0, unique.stdout)
        self.assertIn("Mariana Mayer", unique.stdout)
        ambiguous = self.invoke("resolve", "beto")
        self.assertEqual(ambiguous.returncode, 1)
        self.assertIn("Beto Brito", ambiguous.stdout)
        self.assertIn("regra:", ambiguous.stdout)
        thiago = self.invoke("resolve", "Thiago", "--json")
        self.assertEqual(thiago.returncode, 1)
        payload = json.loads(thiago.stdout)
        self.assertEqual(payload["status"], "ambíguo")
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertEqual(self.invoke("resolve", "Ninguém").returncode, 4)
        self.assertEqual(self.invoke("resolve").returncode, 2)
        leo = self.invoke("resolve", "Léo")
        self.assertEqual(leo.returncode, 0, leo.stdout)
        self.assertIn("Leonardo Gonçalves", leo.stdout)
        self.assertEqual(self.invoke("resolve", "mengue").returncode, 0)

    def test_people_check_blocks_only_unruled_names_in_use(self):
        clean = self.invoke("people-check")
        self.assertEqual(clean.returncode, 0, clean.stdout)
        self.page("src-a", "Thiago conduz.", typ="source", tags="[thiago]")
        blocked = self.invoke("people-check")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("thiago → Thiago | Thiago Mengue", blocked.stdout)
        self.page("src-b", "Beto fala.", typ="source", tags="[beto]")
        out = self.invoke("people-check").stdout
        self.assertNotIn("beto → Beto Brito", out.split("nomes compartilhados com regra")[0])

    def test_candidates_need_person_signal(self):
        for i in range(5):
            self.page("s%d" % i, "Romani disse que sim. Romani pediu prazo. Salesforce caiu.",
                      typ="source", tags="[romani, salesforce, qa]")
        out = self.invoke("people-check").stdout
        cands = out.split("candidatas a cadastro")[1]
        self.assertIn("romani: 5 sources", cands)
        self.assertNotIn("salesforce", cands)
        self.assertNotIn("qa", cands)


class ReviewRegressionTests(KnowledgeBase):
    """Casos reproduzidos pelo Reviewer na revisão do 7.23.10."""

    def names(self):
        return [e["name"] for e in json.loads(self.invoke("people", "--json").stdout)]

    def test_same_short_name_with_different_rules_stays_ambiguous(self):
        self.page("hub1", '## Pessoas\n\n- **Beto** — design.\n  - Desambiguação: neste projeto é Beto Fonseca.\n',
                  extra=['people_section: "Pessoas"'])
        self.page("hub2", '## Pessoas\n\n- **Beto** — people.\n  - Desambiguação: neste projeto é Beto Brito.\n',
                  extra=['people_section: "Pessoas"'])
        self.assertEqual(self.invoke("resolve", "Beto").returncode, 1)
        self.page("beto-fonseca", "x", title="Beto Fonseca — Design", extra=["aliases: [Beto]"])
        self.assertEqual(self.names().count("Beto"), 2)

    def test_short_name_shared_with_another_person_is_not_merged(self):
        self.page("beto-fonseca", "x", title="Beto Fonseca — Design", extra=["aliases: [Beto]"])
        self.page("beto-brito", "x", title="Beto Brito — People", extra=["aliases: []"])
        self.page("hub", "## Pessoas\n\n- **Beto** — alguém.\n", extra=['people_section: "Pessoas"'])
        self.assertIn("Beto", self.names())
        self.assertEqual(self.invoke("resolve", "Beto").returncode, 1)

    def test_shared_alias_does_not_merge_full_names(self):
        self.page("joao-pereira", "x", title="João Pereira", extra=["aliases: [João Silva]"])
        self.page("joao-souza", "x", title="João Souza", extra=["aliases: [João Silva]"])
        self.assertEqual(sorted(self.names()), ["João Pereira", "João Souza"])
        self.assertEqual(self.invoke("resolve", "João Silva").returncode, 1)

    def test_resolve_does_not_mix_words_of_different_forms(self):
        self.page("ana-souza", "x", title="Ana Souza", extra=["aliases: [Maria Lima]"])
        self.assertEqual(self.invoke("resolve", "Ana Lima").returncode, 4)
        self.assertEqual(self.invoke("resolve", "Maria Lima").returncode, 0)

    def test_prose_mention_is_not_a_rule(self):
        self.page("mapa", "## Pessoas\n\n### Beto Fonseca — Design\n\nAinda sem desambiguação documentada.\n\n"
                          "### Beto Brito — People\n", extra=['people_section: "Pessoas"'])
        self.page("src", "Beto", typ="source", tags="[beto]")
        out = self.invoke("people-check")
        self.assertEqual(out.returncode, 1, out.stdout)
        reg = json.loads(self.invoke("people", "--json").stdout)
        self.assertEqual([e["rules"] for e in reg], [[], []])

    def test_merge_is_order_independent(self):
        self.page("a1", "x", title="Ana Souza", extra=["aliases: []"])
        self.page("a2", "x", title="Ana Lima", extra=["aliases: []"])
        self.page("a3", "x", title="Ana Souza", extra=["aliases: [Ana Lima]"])
        self.assertEqual(self.names(), ["Ana Souza"])

    def test_blank_line_before_subitem_rule(self):
        self.page("hub", '## Pessoas\n\n- **Laura Giroleti (Laura)** — PM\n\n  - Desambiguação: aqui Laura é a PM.\n',
                  extra=['people_section: "Pessoas"'])
        reg = json.loads(self.invoke("people", "--json").stdout)
        self.assertEqual(reg[0]["rules"], ["aqui Laura é a PM."])

    def raw(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def grade(self, quote, files):
        for name, text in files.items():
            self.raw("queue/processed/2026-02-01/%s" % name, text)
        self.page("2026-02-01-s", 'Bruto: `queue/processed/2026-02-01/`.\n\n*"%s"*' % quote, typ="source")
        out = self.invoke("quotes", "2026-02-01-s").stdout
        line = [l for l in out.splitlines() if l.startswith("  exatas:")][0]
        counts = dict(part.strip().rsplit(": ", 1) for part in line.split("|"))
        return next(k for k, v in counts.items() if v.split()[0] == "1")

    def test_scattered_trigrams_are_not_exact(self):
        raw = ("o cliente aprovou apenas a primeira etapa. O cliente aprovou tudo sob condição. "
               "Ninguém aprovou tudo ontem.")
        self.assertEqual(self.grade("o cliente aprovou tudo ontem", {"m.md": raw}), "parciais")

    def test_quote_does_not_cross_files(self):
        self.assertEqual(self.grade("o cliente aprovou tudo ontem",
                                    {"a.md": "fim: o cliente aprovou", "b.md": "tudo ontem e mais"}),
                         "parciais")

    def test_short_fragment_after_ellipsis_counts(self):
        self.assertEqual(self.grade("o cliente aprovou tudo... sem ressalvas",
                                    {"m.md": "o cliente aprovou tudo com ressalvas"}), "parciais")

    def test_reversed_fragments_are_not_exact(self):
        self.assertEqual(self.grade("segunda parte da fala… primeira parte da fala",
                                    {"m.md": "primeira parte da fala e depois a segunda parte da fala"}),
                         "parciais")

    def test_fuzzy_first_word_and_later_exact_word(self):
        self.assertEqual(self.grade("Beto aprovou tudo", {"m.md": "Peto aprovou tudo"}), "edição leve")

    def test_later_exact_word_does_not_hide_fuzzy_path(self):
        self.assertEqual(self.grade("o Beto aprovou", {"m.md": "e o Peto aprovou o Beto"}), "edição leve")

    def test_anchor_limit_uses_rarest_word(self):
        raw = "ele " * 450 + "ele de fato aprovou tudo"
        self.assertEqual(self.grade("ele aprovou tudo", {"m.md": raw}), "edição leve")

    def test_extra_short_word_is_light_but_negation_is_not(self):
        self.assertEqual(self.grade("o medo de perder tira a vontade",
                                    {"m.md": "o medo de perder tira vontade de ganhar"}), "edição leve")

    def test_inserted_negation_is_not_light(self):
        self.assertEqual(self.grade("o cliente não aprovou tudo",
                                    {"m.md": "o cliente aprovou tudo ontem"}), "ausentes")

    def test_folder_keeps_jsonl_of_another_recording(self):
        self.assertEqual(self.grade("o cliente aprovou tudo ontem", {
            "a.md": "outra conversa qualquer",
            "b.jsonl": json.dumps({"text": "o cliente aprovou tudo ontem"}) + "\n",
        }), "exatas")


class QuoteCheckTests(KnowledgeBase):
    def raw(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_quote_grades_and_exit(self):
        self.raw("queue/processed/2026-01-02/m1.md",
                 "# Reunião\n\n[00:01] Você: eu apanho pra caralho dos sócios, cara.\n"
                 "[00:05] Remoto: a gente precisa se desprender um pouco do peto agora.\n"
                 "[00:09] Remoto: o cliente aprovou tudo ontem à noite.\n")
        body = ('Fonte em `queue/processed/2026-01-02/`.\n\n'
                '- *"o cliente aprovou tudo ontem"* e *"apanho dos sócios"*.\n'
                '- *"desprender um pouco do Beto"*.\n'
                '- *"frase que nunca foi dita em lugar algum"*.\n'
                '- *"ok"* é curta demais.\n')
        self.page("2026-01-02-src", body, typ="source")
        result = self.invoke("quotes")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("exatas: 1 | edição leve: 2 | em source ligada: 0 | parciais: 0 | ausentes: 1",
                      result.stdout)
        self.assertIn('AUSENTE: "frase que nunca foi dita em lugar algum"', result.stdout)

    def test_linked_source_and_brace_paths(self):
        self.raw("queue/processed/2026-01-03/a.md", "conversa um sobre o plano trimestral da conta\n")
        self.raw("queue/processed/2026-01-03/a.jsonl", "")
        self.raw("queue/processed/2026-01-04/b.jsonl",
                 json.dumps({"type": "turn", "text": "vamos fazer de conta que nada mudou"}) + "\n")
        self.page("2026-01-04-b", "Bruto: `queue/processed/2026-01-04/b.jsonl`.", typ="source")
        self.page("2026-01-03-a",
                  'Bruto: `queue/processed/2026-01-03/a.{md,jsonl}`. Ver [[2026-01-04-b]].\n\n'
                  '*"plano trimestral da conta"* e o *"fazer de conta que nada mudou"*.',
                  typ="source")
        result = self.invoke("quotes", "2026-01-03-a")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("exatas: 1 | edição leve: 0 | em source ligada: 1", result.stdout)

    def test_days_window_and_missing_raw(self):
        self.page("old", '*"uma frase antiga qualquer aqui"*', typ="source", created="2000-01-01")
        result = self.invoke("quotes", "--days", "30")
        self.assertEqual(result.returncode, 0)
        self.assertIn("com bruto localizável: 0", result.stdout)
        result = self.invoke("quotes", "old")
        self.assertIn("sem bruto localizável (informativo): 1", result.stdout)
        self.assertEqual(self.invoke("quotes", "--days", "x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
