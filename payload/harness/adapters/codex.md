# Adaptador Codex

Este adaptador define como o Codex deve operar o second-brain sem depender dos hooks automaticos do Claude Code.

## Entrada de sessao

1. Ler `wiki/index.md` antes de responder qualquer pergunta nao trivial neste diretorio.
2. Usar `harness/contract.md` como fonte das invariantes.
3. Usar `harness/operations/` como playbooks por operacao.

## Execucao de operacoes

- Para `query`, `review`, `ingest`, `inbox`, `lint`, `feed`, `transcript`, `deep`, `handoff` e `model-eval`, seguir o arquivo correspondente em `harness/operations/`.
- Para delegação entre CLIs, seguir `harness/operations/delegate.md`; disponível por padrão, respeitando off explícito. O Codex consulta a inbox durante a conversa porque não recebe os hooks passivos do Claude. Declare o principal conhecido e o benefício antes do spawn; mantenha identidade desconhecida quando o host não a expuser.
- Para criar ou editar arquivos, respeitar as regras de seguranca do ambiente Codex e nunca tocar `raw/`.
- Para operacoes com mudanca duravel, atualizar `wiki/log.md` quando aplicavel e regenerar o indice quando paginas indexaveis forem criadas/removidas.

## Subagentes nativos e modelo forte

Quando o usuario pedir analise profunda, usar `harness/operations/deep.md`.

No Codex, subagentes so devem ser usados quando a plataforma permitir e as regras ativas autorizarem. Modelo e esforco podem ser escolhidos por tarefa quando a interface expuser essa capacidade; uma escolha explicita do usuario nunca e substituida silenciosamente. Se ela estiver indisponivel, informe a limitacao e devolva a decisao. Sem escolha explicita, a ausencia de subagente permite execucao local com o maior rigor possivel.

Agentes nativos pertencem ao host Codex e podem compartilhar o worktree da sessao. O principal atribui caminhos exclusivos para escrita, evita edicoes concorrentes e usa a UI e os controles nativos para inspecionar, orientar, interromper ou aguardar. Colaboradores externos de `delegate.py` recebem contexto e arquivos pela extensao e devolvem propostas; `board`, `inbox` e `native report` nao transformam um tipo no outro nem supervisionam o processo nativo.

Supervisao longa e orientada por eventos reais de conclusao, falha, bloqueio ou mudanca de premissa. Um intervalo de 15 minutos pode marcar estado reportado como desatualizado, mas nao e heartbeat ativo, callback nem promessa de despertar um terminal ocioso. Ausencia de atualizacao e `unknown`; nao autoriza retry. Antes de concluir, o principal reconcilia agentes ativos, confere o contrato de retorno e verifica os artefatos integrados.

## Checagem manual obrigatoria

Como os hooks do Claude nao rodam automaticamente no Codex, antes de concluir uma mudanca duravel rode:

```bash
python3 .claude/scripts/build-index.py check
bash harness/scripts/verify.sh
```

Se uma pagina indexavel foi criada/removida antes do check:

```bash
python3 .claude/scripts/build-index.py generate
```

## Calendario

Gmail (Google Calendar MCP) = pessoal. Calendar do Mac (`bash harness/scripts/agenda.sh`) = profissional. Sempre as duas, em qualquer mencao a agenda, calendario, reuniao do dia, disponibilidade ou planejamento de horario. Playbook: `harness/operations/agenda.md`. Gmail vazio nao implica dia livre. Nunca reexibir senha, link de reuniao ou lista crua de participantes.

## Memoria

O Codex nao tem store de auto-memory equivalente ao do Claude Code. Persistencia duravel de comportamento/preferencia do Codex e responsabilidade de `AGENTS.md` + decisao do usuario; nao ha operacao MEMORY automatica no Codex.

- Nao escrever aprendizado de sessao em `.claude/memory/` — essa pasta e um **snapshot point-in-time** da memoria viva do Claude (ver `.claude/memory/README.md`), nao memoria viva do Codex.
- Re-sincronizar o snapshot (`cp` da memoria viva do Claude para `.claude/memory/`) so quando o usuario pedir explicitamente; nunca como efeito colateral de uma operacao do vault.

## Nao fazer

- Nao editar `CLAUDE.md` ou `.claude/` para adaptar Codex, salvo pedido explicito.
- Nao editar `wiki/index.md` ou `wiki/*/_index.md` a mao.
- Nao criar wikilinks especulativos.
