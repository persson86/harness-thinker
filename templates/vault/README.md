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

Em linguagem natural ou via `/comando` no Claude Code: **INGEST** (ingere fonte), **QUERY** (responde citando páginas), **INBOX** (captura ideia), **FEED** (roteia a `queue/`), **TRANSCRIPT** (destila reuniões), **DEEP** (análise profunda), **LINT** (health-check), **MEMORY** (aprendizados), **DREAM** (manutenção proativa). Documentadas no harness-thinker.

## Manter o harness atualizado

```bash
# a partir de um clone do harness-thinker
./install.sh /caminho/deste/vault --update
```

Os arquivos do harness são **gitignorados** aqui (descartáveis/regeneráveis). **Edita-se o harness só na fonte**, nunca a cópia instalada. Para mudar categorias, edite `vault.config.json` (não o `build-index.py`).

## Segurança

- Nenhum segredo no repositório — credenciais no keychain do SO, lidas em runtime.
- `raw/` e `queue/` gitignored (fontes brutas e buffer transitório).
