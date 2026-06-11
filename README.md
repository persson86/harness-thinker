# harness-thinker

Um **harness para um "second brain" no padrão LLM Wiki** ([Andrej Karpathy](https://karpathy.bearblog.dev/)): um LLM compila e mantém uma base de conhecimento persistente em markdown, em vez de fazer RAG episódico. Este repo é a **maquinaria** genérica — contrato, operações, hooks de enforcement, gerador de índice e instalador. O **conteúdo e a configuração** (suas categorias, sua identidade, seu conhecimento) vivem no seu próprio repo de dados, privado.

Você instala o harness num diretório, ele vira seu vault, e um agente (Claude Code ou Codex) passa a mantê-lo sob um contrato: `raw/` imutável, `wiki/` como território autoral, frontmatter com `summary:`, wikilinks reais, índice gerado e log append-only.

## O que tem aqui

```
harness-thinker/
├── install.sh            # materializa o payload num vault (modos: adotar / --init)
├── VERSION               # versão do harness
├── payload/              # ← o que é instalado (1:1 no target)
│   ├── CLAUDE.md         #   adaptador Claude Code
│   ├── AGENTS.md         #   adaptador Codex
│   ├── harness/          #   contract.md + operations/ + adapters/ + scripts/verify.sh
│   └── .claude/          #   commands/ hooks/ scripts/build-index.py settings.json
├── templates/vault/      # scaffold de um vault novo (--init): config, .gitignore, README, stubs
└── docs/
    └── split-design.md   # design da separação harness × dados
```

**`payload/` e `templates/` são o que se edita.** `install.sh`, `VERSION` e `docs/` são a maquinaria do repo-fonte.

## Instalação

Dois modos.

**Criar um vault novo do zero** (`--init`):

```bash
./install.sh --init ~/meu-second-brain
```

Scaffolda `wiki/` com as categorias do `templates/vault/vault.config.json` (starter neutro, editável), `raw/`, `queue/`, um `.gitignore` de dados e um README, gera o índice inicial e instala o harness por cima. Depois é só virar um repo git **privado** e começar a ingerir.

**Adotar um vault que já existe** (default):

```bash
./install.sh ~/meu-second-brain --update
```

Instala só o harness sobre o vault existente, sem tocar em `wiki/`, `raw/`, `queue/`, `vault.config.json` nem `.claude/memory/`. Se não houver `vault.config.json`, deriva um a partir das pastas de `wiki/` para você revisar.

**Remoto** (sem clonar — requer o repo público):

```bash
curl -fsSL https://raw.githubusercontent.com/persson86/harness-thinker/main/install.sh \
  | bash -s -- --init ~/meu-second-brain
```

O installer marca hooks e `verify.sh` como executáveis e grava `harness/.version` + `harness/.manifest` no target.

## Configuração por-vault

As **categorias** do vault são dados, não código: vivem em `vault.config.json` no root do vault (`categories`, `subsharded`, `fast_spheres`, `inbox_dir`). O `build-index.py` lê esse arquivo — adicionar/renomear esfera é editar o config, nunca o script. Por isso `install.sh --update` num vault existente **não sobrescreve** suas categorias.

## Portabilidade

Hooks, `settings.json` e `build-index.py` resolvem a raiz do vault por `$CLAUDE_PROJECT_DIR` (com fallback script-relative) — o harness funciona em qualquer vault, em qualquer caminho.

## Controle de drift

Regra única: **edita-se o harness só aqui.** No vault os arquivos instalados são descartáveis e regeneráveis via `install.sh --update`.

`payload/harness/scripts/verify.sh` compara os arquivos instalados contra `harness/.manifest` (sha256). Drift — um arquivo editado in-place no vault em vez de na fonte — aparece como WARN no `verify.sh` (que o LINT roda no health-check). WARN, não FAIL: um hotfix legítimo não bloqueia o verify, só fica visível para reconciliar na fonte.

## Operações

Acionadas em linguagem natural ou via `/comando` no Claude Code (playbooks neutros em `payload/harness/operations/`): **INGEST**, **QUERY**, **INBOX**, **FEED**, **TRANSCRIPT**, **DEEP**, **LINT**, **MEMORY** (Claude-only), **DREAM**.
