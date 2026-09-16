#!/usr/bin/env python3
"""Regression checks for the Codex native-subagent supervision contract."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CodexDelegationPolicyTests(unittest.TestCase):
    def read_payload(self, relative_path):
        return (ROOT / "payload" / relative_path).read_text(encoding="utf-8")

    def test_agents_contract_keeps_orchestration_contextual_and_verifiable(self):
        agents = self.read_payload("AGENTS.md")
        self.assertIn("Classe de orquestração longa, como Astra", agents)
        self.assertIn("não o principal obrigatório", agents)
        self.assertIn("atribua caminhos exclusivos a cada agente", agents)
        self.assertIn("Auto-relato de conclusão não substitui a verificação", agents)
        self.assertIn("Ausência de atualização significa estado desconhecido", agents)
        self.assertIn("delegação não presume economia", agents)

    def test_codex_adapter_separates_native_and_external_supervision(self):
        adapter = self.read_payload("harness/adapters/codex.md")
        self.assertIn("Agentes nativos pertencem ao host Codex", adapter)
        self.assertIn("Colaboradores externos de `delegate.py`", adapter)
        self.assertIn("nao e heartbeat ativo", adapter)
        self.assertIn("Ausencia de atualizacao e `unknown`; nao autoriza retry", adapter)

    def test_delegate_runbook_defines_stale_state_without_fake_heartbeat(self):
        operation = self.read_payload("harness/operations/delegate.md")
        self.assertIn("## Agentes nativos e supervisão longa", operation)
        self.assertIn("não chame um modelo periodicamente só para gerar status", operation)
        self.assertIn("não presuma falha, cancelamento nem autorização para repetir trabalho", operation)
        self.assertIn("Esse prazo é TTL de estado reportado, não heartbeat", operation)


if __name__ == "__main__":
    unittest.main()
