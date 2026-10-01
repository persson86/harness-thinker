#!/usr/bin/env python3
"""Regression checks for the critical-review escalation policy."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SECTION = "## Escalonamento para revisão crítica"
POINTER = "`harness/operations/delegate.md` > Escalonamento para revisão crítica"
TRIGGERS = ("aposta", "irreversibilidade", "evidência frágil", "travamento")


class EscalationPolicyTests(unittest.TestCase):
    def read_payload(self, relative_path):
        return (ROOT / "payload" / relative_path).read_text(encoding="utf-8")

    def section(self):
        operation = self.read_payload("harness/operations/delegate.md")
        self.assertEqual(operation.count(SECTION), 1)
        body = operation.split(SECTION, 1)[1]
        return re.split(r"\n## ", body, maxsplit=1)[0]

    def test_triggers_are_observable_not_self_confidence(self):
        body = self.section()
        for trigger in ("**Aposta:**", "**Irreversibilidade:**", "**Evidência frágil:**", "**Travamento:**"):
            self.assertIn(trigger, body)
        self.assertIn("A própria sensação de confiança não é gatilho", body)
        self.assertIn("Concordância com outro modelo não promove a conclusão a fato", body)
        self.assertIn("Trocar de tática porque apareceu evidência melhor é adaptação normal", body)

    def test_consequence_overrides_size_exclusions(self):
        body = self.section()
        precedence = body.index("Consequência material e irreversibilidade prevalecem sobre tamanho e formato")
        self.assertLess(precedence, body.index("não escale pergunta rápida"))

    def test_blind_brief_never_bypasses_context_protection(self):
        body = self.section()
        self.assertIn("Recusa por segredo, credencial, configuração protegida ou escopo de circulação não se contorna com cópia", body)
        self.assertIn("declare a limitação no brief", body)

    def test_session_mode_governs_initiative(self):
        body = self.section()
        self.assertIn("Em `auto`, o modo herdado, submeta dentro dos limites", body)
        self.assertIn("Em `request`, proponha a revisão em uma linha e aguarde", body)
        self.assertIn("Com a extensão desligada ou a CLI indisponível, não submeta nem registre", body)
        self.assertIn("Os limites de chamadas valem para o escalonamento", body)
        self.assertIn("Agrupe decisões relacionadas da mesma entrega", body)

    def test_reviewer_choice_never_substitutes_silently(self):
        body = self.section()
        self.assertIn("Escolha explícita do usuário vence", body)
        self.assertIn("outro provedor que não o do principal", body)
        self.assertIn("sem que isso vire corroboração", body)
        self.assertIn("não substitua silenciosamente", body)
        self.assertIn("diga ao usuário que a revisão não ocorreu", body)

    def test_first_review_is_blind_and_reconciliation_is_bounded(self):
        body = self.section()
        self.assertIn("mas não a conclusão do principal", body)
        self.assertIn("verificado, inferência e não verificável", body)
        self.assertIn("confere cada objeção na fonte antes de aplicá-la", body)
        self.assertIn("no máximo uma chamada de reconciliação", body)
        self.assertIn("crie o `run` antes da primeira leitura", body)

    def test_escalations_are_recorded_with_named_trigger(self):
        body = self.section()
        self.assertIn("Somente com a extensão ligada e a CLI disponível", body)
        self.assertIn("passe `--model` sempre que a escolha for outra", body)
        self.assertIn('record --task review --reason "gatilho: <nome> — não escalado:', body)
        self.assertIn("sem alterar a política autonomamente", body)

    def test_documented_flags_exist_in_cli(self):
        cli = self.read_payload("harness/scripts/delegate.py")
        for parser in ('sub.add_parser("record"', 'sub.add_parser("feedback"'):
            self.assertIn(parser, cli)

    def test_every_cli_constitution_points_to_policy(self):
        for path in ("CLAUDE.md", "AGENTS.md", ".grok/rules/thinker.md"):
            text = self.read_payload(path)
            self.assertIn(POINTER, text, path)
            pointer_line = next(line for line in text.splitlines() if POINTER in line)
            for trigger in TRIGGERS:
                self.assertIn(trigger, pointer_line, path)
            self.assertIn("nunca pela própria sensação de confiança", pointer_line, path)

    def test_conversation_entry_recognizes_explicit_request(self):
        operation = self.read_payload("harness/operations/delegate.md")
        self.assertIn("“Peça uma segunda opinião de outro modelo”", operation)


if __name__ == "__main__":
    unittest.main()
