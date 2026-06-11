# harness-thinker

A harness for a **second brain in the LLM Wiki pattern** ([Andrej Karpathy](https://karpathy.bearblog.dev/)): an agent compiles and maintains a persistent markdown knowledge base instead of doing episodic RAG. This repo is the reusable **machinery** — contract, operations, enforcement hooks, index generator, installer. Your **content and config** (categories, identity, knowledge) live in your own private data repo.

Install it into a directory and it becomes your vault, maintained by an agent (Claude Code or Codex) under a contract: `raw/` immutable, `wiki/` as authored territory, frontmatter with `summary:`, real wikilinks, generated index, append-only log.

## Layout

```
install.sh         # installs the payload into a vault (modes: adopt / --init)
payload/           # what gets installed 1:1 into the target
  CLAUDE.md        #   Claude Code adapter
  AGENTS.md        #   Codex adapter
  harness/         #   contract + operations/ + adapters/ + scripts/verify.sh
  .claude/         #   commands/ hooks/ scripts/build-index.py settings.json
templates/vault/   # scaffold for a new vault (--init)
```

`payload/` and `templates/` are what you edit.

## Install

**New vault** (`--init`):

```bash
./install.sh --init ~/my-second-brain
```

Scaffolds `wiki/` with the categories from `templates/vault/vault.config.json` (neutral starter, editable), plus `raw/`, `queue/`, a data `.gitignore` and README, generates the index, and installs the harness. Then make it a **private** git repo and start ingesting.

**Existing vault** (adopt, default):

```bash
./install.sh ~/my-second-brain --update
```

Installs only the harness; never touches `wiki/`, `raw/`, `queue/`, `vault.config.json` or `.claude/memory/`. Derives a `vault.config.json` from your `wiki/` folders if absent.

**Remote** (no clone):

```bash
curl -fsSL https://raw.githubusercontent.com/persson86/harness-thinker/main/install.sh \
  | bash -s -- --init ~/my-second-brain
```

## Per-vault config

Categories are data, not code: they live in `vault.config.json` (`categories`, `subsharded`, `fast_spheres`, `inbox_dir`). `build-index.py` reads that file, so `--update` never overwrites your categories.

## Drift control

Edit the harness **only here**. In the vault the installed files are disposable and regenerated via `install.sh --update`. `verify.sh` compares installed files against `harness/.manifest` (sha256) and flags drift as a warning (it runs in the LINT health-check). Hooks, `settings.json` and `build-index.py` resolve the vault root via `$CLAUDE_PROJECT_DIR`, so the harness works at any path.

## Operations

Triggered in natural language or via `/command` in Claude Code (neutral playbooks in `payload/harness/operations/`): **INGEST**, **QUERY**, **INBOX**, **FEED**, **TRANSCRIPT**, **DEEP**, **LINT**, **MEMORY** (Claude-only), **DREAM**.
