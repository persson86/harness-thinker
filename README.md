# harness-thinker

A harness for a **second brain in the LLM Wiki pattern** ([Andrej Karpathy](https://karpathy.bearblog.dev/)): an agent compiles and maintains a persistent markdown knowledge base instead of doing episodic RAG. This repo is the reusable **machinery** — contract, operations, enforcement hooks, index generator, installer. Your **content and config** (categories, identity, knowledge) live in your own private data repo.

Install it into a directory and it becomes your vault, maintained by an agent (Claude Code, Codex, or Grok Build) under a contract: `raw/` immutable, `wiki/` as authored territory, frontmatter with `summary:`, real wikilinks, generated index, append-only log.

## Layout

```
install.sh         # installs the payload into a vault (modes: adopt / --init)
payload/           # what gets installed 1:1 into the target
  CLAUDE.md        #   Claude Code adapter
  AGENTS.md        #   Codex adapter
  harness/         #   contract + operations/ + adapters/ + scripts/verify.sh
  .claude/         #   commands/ hooks/ scripts/build-index.py settings.json
  .grok/           #   Grok Build rules, hook shim, memory-skill shadow
templates/vault/   # scaffold for a new vault (--init)
```

`payload/` and `templates/` are what you edit.

## Install

This repo is the **installer**, not the vault. You clone it once, then run `install.sh`
pointing at the directory you want to be (or become) your vault — a **separate** folder.

### Step 1 — get the installer

```bash
git clone https://github.com/persson86/harness-thinker.git
cd harness-thinker
```

### Step 2 — install into a vault

**A) Create a brand-new vault from scratch** (`--init`):

```bash
./install.sh --init ~/my-second-brain
```

Scaffolds `~/my-second-brain` with `wiki/` (categories from `templates/vault/vault.config.json`,
a neutral editable starter), `raw/`, `queue/`, a data `.gitignore` and README, generates the
index, and installs the harness. The target folder doesn't need to exist yet — it's created.

**B) Point at a vault that already exists** (adopt — the default, no `--init`):

```bash
./install.sh ~/my-existing-vault --update
```

Installs only the harness over your existing files; never touches `wiki/`, `raw/`, `queue/`,
`vault.config.json`, `vault-heuristics.md` or `.claude/memory/`. If there's no `vault.config.json`, it derives one
from your `wiki/` subfolders for you to review.

### Step 3 — make the vault a private repo

The vault is **your data** — keep it private and separate from this installer:

```bash
cd ~/my-second-brain
git init && git add -A && git commit -m "init vault"   # then push to a PRIVATE remote
```

Open the vault folder in Claude Code, Codex, or Grok Build and start with `/ingest`, `/inbox`, `/query`.

### Without cloning (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/persson86/harness-thinker/main/install.sh \
  | bash -s -- --init ~/my-second-brain
# adopt an existing vault:
curl -fsSL https://raw.githubusercontent.com/persson86/harness-thinker/main/install.sh \
  | bash -s -- ~/my-existing-vault --update
```

## Update

**From inside the vault** — the only command you need:

```bash
bash harness/scripts/update.sh
```

Pulls the latest harness from GitHub and reinstalls it in place. Run from the vault root.

What gets overwritten: `CLAUDE.md`, `AGENTS.md`, `harness/`, `.claude/commands/`, `.claude/hooks/`, `.claude/scripts/`, `.claude/settings.json`, `.grok/`.  
What is never touched: `wiki/`, `raw/`, `queue/`, `vault.config.json`, `vault-heuristics.md`, `.claude/memory/`, `.claude/settings.local.json`.

## Per-vault config

Categories are data, not code: they live in `vault.config.json` (`categories`, `subsharded`, `fast_spheres`, `inbox_dir`). `build-index.py` reads that file, so `--update` never overwrites your categories.

Optional decision heuristics live in `vault-heuristics.md`. The installer may scaffold the file on `--init`, but update/adopt never overwrite it.

## Drift control

Edit the harness **only here**. In the vault the installed files are disposable and regenerated via `install.sh --update`. `verify.sh` compares installed files against `harness/.manifest` (sha256) and flags drift as a warning (it runs in the LINT health-check). Hooks, `settings.json` and `build-index.py` resolve the vault root via `$CLAUDE_PROJECT_DIR`, so the harness works at any path.

## Closing gate

Two hooks enforce the contract while an agent works. `protect-raw.sh` blocks any write or delete
under `raw/`. `track-ingest.sh` records which pages the session created or edited, and on `Stop`
`check-ingest.sh` refuses to end the turn until the durable-knowledge invariants hold:

- every page created this session is recorded in `wiki/log.md`;
- indexable pages have a `summary:` in the frontmatter;
- new or edited pages contain no broken `[[wikilinks]]`;
- the generated index is in sync with the frontmatter.

The log check reads the log's **content** — it looks for each new page's slug — rather than
watching which tool wrote the file. A log appended via Bash counts, and a log merely touched
without recording anything does not. A blocked `Stop` is evidence, not friction: fix the page,
the link, the index or the log, and the turn closes.

## Operations

Triggered in natural language or via `/command` (neutral playbooks in `payload/harness/operations/`): **INGEST**, **QUERY**, **REVIEW**, **AGENDA** (Gmail pessoal + Calendar do Mac profissional), **INBOX**, **FEED**, **TRANSCRIPT**, **DEEP**, **LINT**, **MEMORY** (Claude-only; Grok Build recusa), **DREAM**, **REVERIE**.

## 7.11.0 — Revisable knowledge and conversation

Corrections now have an explicit REVIEW workflow: trace the affected assertion and candidate dependencies, preserve historical context, and update both body and summary within the user's authorization. Approval to save is distinct from evidence supporting a claim; a source note is an editorial representation, not necessarily the original artifact.

Optional `knowledge_status`, `as_of` and `superseded_by` metadata make historical context visible in generated indexes and search. Existing pages remain compatible; missing metadata does not imply current truth. `build-index.py review <slug>` lists direct references from wikilinks and `sources:` as review candidates, not corroboration. `stale` also considers insights across categories and skips explicitly historical/superseded pages.

QUERY and DEEP adapt to exploration, critique, decision and execution. They propose saving when useful instead of ending every exchange with a publication question. Personal voice remains vault-owned in `vault-heuristics.md`.

Validation has two distinct layers:

- `bash tests/run.sh` and `python3 tests/test_knowledge_review.py`: deterministic regression checks.
- `payload/harness/evals/knowledge-review.md`: five behavioral scenarios with explicit expectations and failure criteria; these require observed runs and judgment, not a claim that structural tests prove reasoning quality.

Known baseline limitation: the 7.10.0 smoke suite reports 55 passing checks and four failing agenda-gate assertions. The same four failures remain in 7.11.0; agenda behavior is outside this change. The five new knowledge-review tests pass independently.

Analyses of source material start with a short **Resumo** and **Ideias principais**, followed by critical analysis, uncertainties and durable deltas. **TRANSCRIPT** uses an explicit two-phase UX: a request to analyze remains read-only and returns a delta ledger; a request to ingest runs analysis and ingestion in the same turn without a redundant approval checkpoint. The source note preserves meeting context and source-only items, while live pages receive only durable promoted deltas. Ingestion never implies commit or push; both remain separate explicit actions.

Grok Build loads `.grok/rules/thinker.md` as its native entry (it also auto-loads `AGENTS.md` and `CLAUDE.md`; Grok rules win on conflict). Enforcement goes through `.grok/hooks/shim.sh`, which translates Grok's hook JSON and calls the existing Claude hook scripts without modifying them. Project hooks require `/hooks-trust` once.
