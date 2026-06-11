# Operacao: feed

Use para rotear itens pendentes de `queue/`.

## Passo 0 — Verificar queue

Antes de classificar uma nova entrada, verificar arquivos pendentes em `queue/`, excluindo `queue/processed/` e `queue/README.md`.

Padroes esperados:

- `[ts]-audio-[slug].txt`: INBOX com transcricao de audio.
- `[ts]-url-[slug].md`: classificar como INGEST, INBOX ou ANALISE.
- `[ts]-nota-[slug].md`: INBOX.
- `[ts]-meeting-[slug].md`: TRANSCRIPT (transcricao de reuniao; companion `.jsonl` de mesmo basename, mover junto para `processed/`).

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

Use ANALISE + CONFIRMACAO se houver:

- vies comercial forte;
- cruzamento ambiguo de categorias;
- duvida real sobre duplicidade no vault.

## Done when

- Queue foi verificada.
- Itens pendentes foram processados ou reportados.
- Arquivos processados foram movidos para `queue/processed/[data]/`.
- Operacao derivada cumpriu seu proprio done when.
