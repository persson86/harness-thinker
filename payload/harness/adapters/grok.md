# Adaptador Grok Build

Como o Grok Build opera o second-brain. Não depende dos hooks nativos do Claude Code; o enforcement equivalente vive em `.grok/hooks/` e despacha para os scripts já existentes em `.claude/hooks/`, sem modificá-los.

Este arquivo não é auto-carregado. A entrada automática do Grok Build é `.grok/rules/thinker.md`. `AGENTS.md` e `CLAUDE.md` também são carregados pela plataforma — as regras Grok prevalecem em conflito. Não edite `AGENTS.md` nem `CLAUDE.md` para adaptar Grok.

## Entrada de sessão

1. Ler `wiki/index.md` e `vault.config.json` antes de responder pergunta não trivial neste diretório.
2. Usar `harness/contract.md` como fonte das invariantes.
3. Usar `harness/operations/` como playbooks por operação.
4. Usar este adaptador para checagens e limites específicos do Grok Build.
5. Se existir `vault-heuristics.md`, consultar em decisões de julgamento; prevalece sobre defaults do harness.

## Execução de operações

- Para `query`, `agenda`, `ingest`, `inbox`, `lint`, `feed`, `transcript`, `deep` e `handoff`, seguir o arquivo correspondente em `harness/operations/`.
- Slash commands em `.claude/commands/` apontam para esses playbooks — reutilizar, não duplicar em `.grok/skills/`, com a exceção de `/memory`.
- Nunca tocar `raw/`.
- Para mudança durável: atualizar `wiki/log.md` quando aplicável e regenerar o índice quando páginas indexáveis forem criadas/removidas.

## Subagentes

Quando o usuário pedir análise profunda, usar `harness/operations/deep.md`.

Síntese do vault fica no pai. Spawn só para trabalho mecânico ou frentes independentes.

- Exploração / extração: tipo `explore` ou `grok-4.5` quando disponível.
- Trabalho comum: in-process. Não spawne o mesmo modelo da sessão.
- Profundidade máxima: 2.

Ignore o roteamento Luna/Terra/Sol de `AGENTS.md`. Se subagente não estiver disponível, executar localmente e explicitar a limitação.

## Hooks

`.grok/hooks/thinker.json` registra UserPromptSubmit, PreToolUse, PostToolUse e Stop. O `shim.sh` traduz o JSON camelCase do Grok para os scripts Claude. `agenda-gate` corre no Stop depois do `check-ingest` para não encerrar virada de agenda sem Gmail + Calendar do Mac.

Hooks de projeto só rodam depois de `/hooks-trust` (ou `--trust`). Sem trust, o shim é skip silencioso.

## Checagem de encerramento

Com shim ativo e projeto trusted, o Stop gate é o mesmo do Claude: log, `summary:`, wikilinks, índice. Bloqueio é evidência.

Sem trust ou sem shim, antes de concluir mudança durável:

```bash
python3 .claude/scripts/build-index.py check
bash harness/scripts/verify.sh
```

Se uma página indexável foi criada/removida antes do check:

```bash
python3 .claude/scripts/build-index.py generate
```

## Memória

Grok Build não tem store equivalente ao MEMORY do Claude Code. Persistência de comportamento/preferência do Grok vive em `.grok/rules/thinker.md` e neste adaptador, por decisão explícita do usuário.

- Não escrever em `.claude/memory/` nem em `~/.claude/projects/*/memory/`.
- Não ressincronizar o snapshot `.claude/memory/` a partir de uma sessão Grok.
- `/memory` nesta plataforma é recusa (skill `.grok/skills/memory` sombreia o command Claude).
- Não ligar `GROK_MEMORY` como substituto sem pedido explícito.

## Calendário

Gmail (Google Calendar MCP) = pessoal. Calendar do Mac (`bash harness/scripts/agenda.sh`) = profissional. Sempre as duas, em qualquer menção a agenda, calendário, reunião do dia, disponibilidade ou planejamento de horário. Playbook: `harness/operations/agenda.md`. Gmail vazio não implica dia livre. Nunca reexibir senha, link de reunião ou lista crua de participantes.

## Output

Conclusão primeiro. Sem narrar ferramenta. Cumprir limite de palavras quando houver. Separar fato, inferência e o que precisa ser verificado.

## Não fazer

- Não editar `CLAUDE.md`, `AGENTS.md` ou `.claude/` para adaptar Grok, salvo pedido explícito.
- Não editar `wiki/index.md` ou `wiki/*/_index.md` à mão.
- Não criar wikilinks especulativos.
- Não criar `GROK.md` no root — o Grok Build não auto-carrega esse nome; a entrada nativa é `.grok/rules/`.
