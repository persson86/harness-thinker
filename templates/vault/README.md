# meu second-brain

Wiki pessoal no padrão **LLM Wiki** ([Andrej Karpathy](https://karpathy.bearblog.dev/)): um LLM compila e mantém uma base de conhecimento persistente em markdown. O humano lê; o agente escreve e mantém.

Repositório de **dados** (mantenha-o **privado**). A infraestrutura que governa o agente vive em [**harness-thinker**](https://github.com/persson86/harness-thinker) e é instalada aqui como dependência.

## Estrutura

```
.
├── vault.config.json   # categorias do vault (edite aqui, não no build-index.py)
├── raw/                # fontes originais imutáveis (NÃO versionado)
├── queue/              # buffer de entrada (NÃO versionado, só o README)
├── wiki/               # território do agente — o ativo
│   ├── index.md        # root fino gerado
│   ├── log.md          # registro cronológico append-only
│   └── <categoria>/    # uma pasta por categoria do config
└── .claude/
    └── memory/         # snapshot da memória do agente (opcional)
```

## Operações

Em linguagem natural ou via `/comando` no Claude Code, Codex ou Grok Build: **INGEST** (ingere fonte), **QUERY** (responde citando páginas), **REVIEW** (revisa registros afetados por correções e evidências novas), **INBOX** (captura ideia), **FEED** (roteia a `queue/`), **TRANSCRIPT** (destila reuniões), **DEEP** (análise profunda), **LINT** (health-check), **MEMORY** (aprendizados; Claude-only), **DREAM** (manutenção proativa), **REVERIE** (exploração livre). Documentadas no harness-thinker.

Autorização para salvar não comprova a hipótese registrada. Contexto histórico pode ser sinalizado com `knowledge_status`, `as_of` e `superseded_by`; índice e busca exibem esses campos opcionais. O comando `python3 .claude/scripts/build-index.py review <slug>` lista referências diretas como candidatas a revisão, sem alterar arquivos nem certificar evidência.

## Manter o harness atualizado

```bash
# a partir de um clone do harness-thinker
./install.sh /caminho/deste/vault --update
```

Os arquivos do harness são **gitignorados** aqui (descartáveis/regeneráveis). **Edita-se o harness só na fonte**, nunca a cópia instalada. Para mudar categorias, edite `vault.config.json` (não o `build-index.py`). Para heurísticas pessoais de decisão, edite `vault-heuristics.md`.

## Segurança

- Nenhum segredo no repositório — credenciais no keychain do SO, lidas em runtime.
- `raw/` e `queue/` gitignored (fontes brutas e buffer transitório).
- Transcrições processadas permanecem em `queue/processed/`; não são apagadas como efeito do processamento. Preservação local e Git da wiki não substituem backup independente dos originais.
