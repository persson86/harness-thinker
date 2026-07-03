# Operacao: feed

Use para rotear itens pendentes de `queue/` ou uma nova entrada solta.

## Passo 0 — Verificar queue

Antes de classificar nova entrada, verificar arquivos pendentes em `queue/`, excluindo `queue/processed/` e `queue/README.md`.

Padroes esperados:

- `[ts]-audio-[slug].txt`: INBOX com transcricao de audio.
- `[ts]-url-[slug].md`: classificar como INGEST, INBOX ou ANALISE.
- `[ts]-nota-[slug].md`: INBOX.
- `[ts]-meeting-[slug].md`: TRANSCRIPT; companion `.jsonl` de mesmo basename deve mover junto.

Depois de processar arquivo da fila, mover para `queue/processed/[YYYY-MM-DD]/`. Nao deletar brutos sem confirmacao.

## Classificacao

Use INGEST se todos forem verdadeiros:

- autor identificavel e relevante;
- profundidade para criar pelo menos source + entity/concept;
- conceitos transferiveis alem do contexto da fonte.

Use INBOX se qualquer for verdadeiro:

- conteudo raso;
- ideia embrionaria;
- qualidade mista sem separacao limpa.

Use TRANSCRIPT quando for transcricao de reuniao real do usuario.

Use ANALISE + CONFIRMACAO se houver vies comercial forte, cruzamento ambiguo de categorias ou duvida real sobre duplicidade no vault.

## Execucao

1. Abra com decisao tomada + razao.
2. Execute a operacao derivada pelo playbook correspondente.
3. Se veio da queue, mova o arquivo e companions para `queue/processed/[data]/`.

## Done when

- Queue foi verificada.
- Fonte classificada como INGEST, INBOX, TRANSCRIPT ou ANALISE.
- Operacao derivada cumpriu seu proprio done when.
- Arquivo processado foi preservado em `queue/processed/[data]/`.
