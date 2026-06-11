# Adaptador Codex

Este adaptador define como o Codex deve operar o second-brain sem depender dos hooks automaticos do Claude Code.

## Entrada de sessao

1. Ler `wiki/index.md` antes de responder qualquer pergunta nao trivial neste diretorio.
2. Usar `harness/contract.md` como fonte das invariantes.
3. Usar `harness/operations/` como playbooks por operacao.

## Execucao de operacoes

- Para `query`, `ingest`, `inbox`, `lint`, `feed`, `transcript` e `deep`, seguir o arquivo correspondente em `harness/operations/`.
- Para criar ou editar arquivos, respeitar as regras de seguranca do ambiente Codex e nunca tocar `raw/`.
- Para operacoes com mudanca duravel, atualizar `wiki/log.md` quando aplicavel e regenerar o indice quando paginas indexaveis forem criadas/removidas.

## Subagentes e modelo forte

Quando o usuario pedir analise profunda, usar `harness/operations/deep.md`.

No Codex, subagentes so devem ser usados quando a plataforma permitir e as regras ativas autorizarem. Se nao houver subagente ou override de modelo disponivel, executar localmente com o maior rigor possivel e explicitar a limitacao quando relevante.

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

## Memoria

O Codex nao tem store de auto-memory equivalente ao do Claude Code. Persistencia duravel de comportamento/preferencia do Codex e responsabilidade de `AGENTS.md` + decisao do usuario; nao ha operacao MEMORY automatica no Codex.

- Nao escrever aprendizado de sessao em `.claude/memory/` — essa pasta e um **snapshot point-in-time** da memoria viva do Claude (ver `.claude/memory/README.md`), nao memoria viva do Codex.
- Re-sincronizar o snapshot (`cp` da memoria viva do Claude para `.claude/memory/`) so quando o usuario pedir explicitamente; nunca como efeito colateral de uma operacao do vault.

## Nao fazer

- Nao editar `CLAUDE.md` ou `.claude/` para adaptar Codex, salvo pedido explicito.
- Nao editar `wiki/index.md` ou `wiki/*/_index.md` a mao.
- Nao criar wikilinks especulativos.
