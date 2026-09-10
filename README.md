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
  .agents/         #   optional delegation and model-eval skills for Codex
templates/vault/   # scaffold for a new vault (--init)
```

`payload/` and `templates/` are what you edit.

## Release discipline

Maintain the source repository, never its installed target. In Felipe's environment
the source is `/Users/persson/Builder/projects/harness-thinker`; the vault is a separate target.
For a harness change: run `bash tests/run.sh`, increment `VERSION`, document the change,
commit the reviewed paths, create `v<VERSION>`, push branch and tag, then update the
target with `install.sh TARGET --update`. Verify target `harness/.version`, manifest,
vault health and local/remote SHA parity. Publishing vault knowledge is a separate scope.

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
`vault.config.json`, `vault-heuristics.md` or `.claude/memory/`. It appends the exact generated-skill rules
`/.agents/skills/thinker-delegate/` and `/.agents/skills/thinker-model-eval/` to an existing regular
`.gitignore` when absent, preserving its other content.
If there's no `vault.config.json`, it derives one
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

What gets overwritten: `CLAUDE.md`, `AGENTS.md`, `harness/`, `.claude/commands/`, `.claude/hooks/`, `.claude/scripts/`, `.grok/`. `.claude/settings.json` is merged: custom `statusLine`, settings, permissions and unrelated hooks are preserved; on a fresh Claude vault the harness adds its 5-second delegation statusLine.
What is never touched: `wiki/`, `raw/`, `queue/`, `vault.config.json`, `vault-heuristics.md`, `.claude/memory/`, `.claude/settings.local.json`. The only `.gitignore` migration appends the two exact generated-skill rules for `thinker-delegate` and `thinker-model-eval` when absent; it preserves all existing lines and refuses a symlink or tracked collision.

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

Triggered in natural language or via `/command` (neutral playbooks in `payload/harness/operations/`): **INGEST**, **QUERY**, **REVIEW**, **AGENDA** (Gmail pessoal + Calendar do Mac profissional), **INBOX**, **FEED**, **TRANSCRIPT**, **DEEP**, **LINT**, **MODEL-EVAL**, **MEMORY** (Claude-only; Grok Build recusa), **DREAM**, **REVERIE**.

## 7.15.0 — Repeatable model evaluation

`MODEL-EVAL` turns local model comparisons into a reusable experiment: freeze blind cases, gold answers and a deterministic JSON spec before any generation; then run independent delegated jobs under an explicit call budget. It measures the observed route—requested model, effort, provider CLI, instructions, permissions and transport—not an abstract universal ranking.

The Codex and Grok skills route to the same canonical operation. A standard-library validator checks case IDs, controlled evidence IDs, required semantic fields, exact action labels and word limits without spending model quota. Semantic quality remains a reviewed judgment. Reports keep outcome, execution trajectory, efficiency and human feedback separate, apply a quality floor and preserve inconclusive results or Pareto ties.

Profiles are discovered at runtime, so a candidate can be compared with current baselines without hard-coding a permanent allowlist. `board --watch` exposes execution and delivery while the test runs. The workflow never sums provider token counters, infers model identity from a requested alias, changes routing defaults or promotes benchmark results into the vault without a separate decision.

## Delegation availability and terminal indication

Delegation is available after installation but never auto-spawns an agent. `route` and `submit` require an explicit benefit plus independent work or critical-review rationale; the principal remains responsible for the decision and integration. Initial routes use Sonnet medium for bounded transcript/draft work and Opus high for critical review.

`harness/scripts/delegation-indicator.py` renders compact external (`q/r/p/f`) and native-reported (`r/c/f/u`) counts without reading prompts, inventing progress, or claiming native-host coverage. A read failure is `unknown`, not zero. `--watch 1..60` is bounded; `board --watch 5` remains the persistent terminal board.

For Claude, installation merges settings instead of replacing them: a custom statusLine is retained, as are local settings, permissions and unrelated hooks; a new vault receives the harness statusLine at a five-second refresh. The merge script is source-owned at `scripts/merge-settings.py`. Codex has no promised arbitrary statusline callback; use the board and its native UI.

## 7.17.0 - Live delegation board

The board now focuses on active helpers and completions from the last five minutes. `--recent-seconds 120` changes that display window; `--history --limit 30` includes older entries. Nothing is deleted or acknowledged by hiding a row. Old inbox items and unacknowledged failures remain compact alerts. Native helpers have separate, explicitly reported model/task/state rows; the principal itself is not monitored.

```bash
python3 harness/scripts/delegate.py board --all-sessions --watch 5
```

Restart an already-running watch after updating the harness. Interactive terminals redraw in place, including with `--no-color`; redirected output remains append-only.

## 7.14.0 — Delegation board

`board` draws agents, tasks and progress as a table, with execution and delivery as separate columns: a job that returned is not a job you read. It reads state, starts nothing and works while the extension is off. `--watch` refreshes in a deterministic loop, so following the work costs no model turn.

## 7.13.0 — Measurable delegation runs

Delegation experiments can now be grouped as linear `chain` or `principal-eval` runs. A run records the declared principal separately from observed collaborators, manual account-quota snapshots, stage/role/parent handoffs, retries, one reviewed final result and run-level feedback. Principal identity is explicitly labelled declared and unverified; principal usage remains unavailable unless the host exposes it, and token counters from different providers are never summed as if they were comparable.

The first stage receives a `full` handoff. Later stages require a valid completed parent from the immediately preceding stage and use `delta` or `synthesis`, making context growth visible without automatic semantic compression. `run finish` selects exactly one valid final job and materializes only that proposal by default. Existing standalone jobs remain compatible.

The model catalog adds Claude Fable through the subscription alias `fable`, while Astra remains available as `gpt-6-astra`. `doctor --all-profiles` checks every configured profile without making generation calls and continues to report model access as untested. Attempts retain only safe stream metadata—exit code, byte counts and SHA-256 hashes—while raw stdout/stderr are deleted.

## 7.12.0 — Optional delegation and usage learning

Delegation is **OFF by default**. Ask the main agent to enable it for one session, delegate a bounded contribution, inspect pending results, or show the usage history. The agent remains responsible for context, review and integration; collaborators return proposals without overwriting live drafts.

Only existing subscription logins are supported. The extension does not accept API keys or switch to API billing when an account limit or authentication failure occurs.

An explicit model choice wins over session preference and task default. Git starts with Luna low; “use Sonnet for this commit” affects that operation only. Model choice never expands commit/push authority. The deterministic publication helper validates exact scope, serializes Git mutations and verifies remote parity.

The extension includes detached jobs, cancellation, deadlines, recovery, separate comparison drafts, local decision records and explicit feedback. It uses installed Codex/Claude/Grok CLIs with restricted proposal-only adapters; compatibility and model access must be checked in the actual environment. It does not promise a native wake-up notification on every host.

```bash
python3 harness/scripts/delegate.py status
python3 harness/scripts/delegate.py doctor
python3 harness/scripts/delegate.py --session UNIQUE-ID on
python3 harness/scripts/delegate.py --session UNIQUE-ID board
python3 harness/scripts/delegate.py off --all
```

Read [the operation](payload/harness/operations/delegate.md) for the conversational workflow and [the manual](payload/harness/delegation.md) for commands, Git and limitations. State and preferences stay in a private directory outside the vault and survive updates. The new Codex skill lives at `.agents/skills/thinker-delegate/`; install/update adds its exact ignore rule to existing vaults when needed. No background collector starts on install.

The release also fixes the existing calendar gate for “minha próxima agenda”, retaining a negative case for conceptual discussion about agendas.

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
