# Changes

## 7.23.0-rc.4 - 2026-10-02 (laboratory candidate)

- Ships the persistent evaluator prototyped locally in rc.3, with a high-effort minimum, dynamic inventory, explicit unavailable profiles and immutable comparison policies. Historical rounds stay readable; execution cannot silently mix executor versions.
- Adds a host-managed prepare/finish bridge with external temporary workspaces for complete fixture tasks. Explicit reconciliation can bind a verified job or abandon an interrupted attempt without replay. Final-state checks and artifact receipts are distinct from the agent response; arbitrary Python verification is explicitly gated on isolated Docker execution and remains unavailable without it. No provider supervisor is duplicated or granted broader permissions.
- Adds per-criterion judgments, stable evaluator attribution, explicit superseding revisions, blind paired feedback, judge packets and reference-calibration reports. Disagreement and missing observations cannot silently become personal approval.
- Reports separate capability from infrastructure failures, retain excluded candidates, compare matching observed subsets and expose practical margins, per-case variation and human effort. A case-count threshold no longer establishes general qualification.
- Adds a second public development suite with positive-action controls, workspace outcomes and calibration examples. Public fixtures are not held-out confirmation; human preference and visual quality require actual observation.
- Installation and automated checks do not invoke models. No routing defaults, private vault knowledge or provider credentials are published.

## 7.23.0-rc.3 - 2026-10-02 (laboratory candidate)

- Adds a persistent personal evaluation CLI with frozen case/rubric inputs, exact requested routes, bounded trials, resumable delegation and explicit unknown states. Model execution reuses the existing supervisor; installation and tests make no model calls.
- Adds blind review packets, attributed quality grades, separate trajectory audits and explicit human feedback. Reports preserve planned denominators, critical failures, missing observations, ties and qualification limits; no automatic routing changes or universal intelligence score.
- Adds twelve generic synthetic text cases across retrieval, ingestion, analysis, research, code and communication, with development/holdout separation. They screen bounded responses, not full workflows or rendered artifacts. Private runs remain in the target vault's ignored drafts directory.
- Source tests cover integrity, path boundaries, execution budgets/resume and conservative recommendation behavior. This candidate requires real-use calibration and broader independent cases before durable model recommendations.

## 7.23.0-rc.2 - 2026-10-01 (laboratory candidate)

- **Critical-review escalation.** `harness/operations/delegate.md` gains a section that lets any principal request a second reading from another model on its own initiative. Triggers are observable — stakes (a material user decision, or a wiki synthesis/contradiction/position change not directly recorded from a source), irreversibility, fragile evidence whose resolution would change the delivery, an error that returns after a fix — and never the principal's self-assessed confidence. Material consequence and irreversibility override size; otherwise quick questions, open reflection, deterministically checked mechanical work, helper-run Git and low-impact drafts under immediate user review are excluded.
- Session mode governs initiative: `auto` submits within the existing limits and announces the trigger in one line, `request` proposes and waits, off or an unavailable CLI submits and records nothing and states that no external review happened. One review per delivery; related decisions are grouped.
- Reviewer defaults to the frontier class of a different provider (Opus high under Codex/Grok, Sol high under Claude, passed with `--model` because the `review` route defaults to Opus); explicit user choice wins and unavailability is reported, not substituted. The first reading is blind to the principal's conclusion. Authorized material may be excerpted to `drafts/`, but refusals for secrets, credentials, protected configuration or circulation scope are never bypassed by copying. At most one reconciliation call follows an unresolved material divergence, inside a `run` opened beforehand when foreseeable. Agreement is not corroboration; a host-native advisor complements, not replaces, this review.
- Escalations name the trigger in `--reason`, with a complete `submit` example; declined escalations use `record`, so `history`/`feedback` can evaluate the triggers before any policy change.
- `CLAUDE.md`, `AGENTS.md` and `.grok/rules/thinker.md` carry a one-line pointer so the policy is loaded without `/delegate`. A conversation entry recognizes an explicit request for a second opinion.
- Tests: `test_delegation_escalation_policy.py` guards the text contract and pointers; CLI tests execute the playbook's own `submit` example with fake providers (Codex/Sol resolved under a Claude principal, explicit model over the session preference) and check that `record` is refused while off. No runtime code changed. Trigger rate and usefulness are unmeasured; the task-continuity candidate from rc.1 remains unpiloted.
- The policy was itself reviewed blind by Sol high before publication; seven findings (incomplete example, context-protection bypass, exclusion precedence, trigger breadth, `run` ordering, off-state recording, string-only tests) were verified against the source and applied.

## 7.23.0-rc.1 - 2026-09-30 (laboratory candidate)

- Reconciliation supports explicit constraint corrections and moved evidence references with a reason, verified replacement bytes and preserved audit history. Omission still never retires evidence or critical context.
- Adds natural-language entry points to the installed Claude/Codex instructions and bounded checkpoint input through `--file -`, so the agent can register progress without an intermediate workspace file. README documents the complete create/checkpoint/resume/view workflow and its limits.
- Adds opt-in task continuity outside the workspace: explicit task IDs, checkpoints, corrections, revision checks, idempotency receipts, reset generations and portable handoffs. Resume compiles a measured UTF-8 byte budget and refuses to omit critical context silently.
- Evidence fingerprints indicate byte identity only. Changed, missing or unverifiable references prevent a ready handoff. A linked session or job remains unobserved; task state does not control provider execution or imply approval.
- Adds a read-only loopback task surface for an explicitly generated snapshot, with explicit task selection, token/Host/origin checks and unavailable states. It does not follow live agents, run models, or write knowledge.
- Adds synthetic laboratory preparation, an instrumented paired human-pilot protocol, boundary tests and install/update/rollback rehearsal. The protocol keeps human value unobserved until actual use; simulations and model outputs never supply human feedback.
- The candidate does not migrate delegation state, change model routes, import private conversations or install itself into an existing vault. Source-level installation remains explicit. See `specs/setup-optimization/` for scope, validation gates and experimental limitations.

## 7.22.1 - 2026-09-27

- **Codex aliases follow the newest generation.** `luna`, `terra`, `sol` and `astra` resolve to the highest `gpt-<version>-<family>` listed in the Codex CLI's local catalog (`$CODEX_HOME/models_cache.json`, default `~/.codex`); hidden entries and other families never count. The embedded IDs (`gpt-6-luna`, `gpt-5.6-terra`, `gpt-6-sol`, `gpt-6-astra`) are only the minimum used when the catalog is missing, unreadable or lacks the family. An exact ID passed with `--provider` stays literal, and Claude aliases are unaffected.
- The delegation test suite runs with an empty `CODEX_HOME`, so results do not depend on the machine's catalog.

## 7.22.0 - 2026-09-26

Trustworthy delegation data before the October 3 decision gate, less friction, and the playbook gap that let hub pages grow.

- **Reported-model provenance.** Job results carry `model_reported_source` (`stream`, `not_emitted`, `not_emitted_ephemeral`), validated by `reported_view()`; old or malformed records read as absent, never as an inferred value. The name avoids colliding with `model_source`, which is the origin of the *choice* of model. Codex jobs record `not_emitted_ephemeral`: the command runs with `--ephemeral`, so no session file exists to consult, and configuration would not prove the served model.
- **Board and history.** The board projection adds `model_reported` and its provenance without exposing `result`; a note appears only when the reported model differs from the requested one, and a footer states that the shown effort is requested, not confirmed. `history` labels effort as requested, names the provenance and adds a per-provider "total input" (Claude: input + both cache fields; Codex: `input_tokens`), shown as unknown when a field is missing and never compared across providers. `run show` keeps its `usage_note`.
- **Native reports.** `native report --effort` (`low`…`ultra`, `unknown` by default). `snapshot()` exposes `effort` and `created_at`, tolerating records written before 7.22.0. Reusing an id in `running` after a terminal state reopens the record in place; a repeated terminal report keeps its original time. The board shows the declared effort and a "DESDE 1º" column — time since the first report, not work duration.
- **`board --compact`.** Several lines per agent for a narrow side pane: the full model and effort wrap instead of being cut; the reason is the only field abbreviated. Lines are built as plain text, wrapped at spaces when possible and colored last, so no escape fragments leak. Works with `--watch`, `--all-sessions` and `--ascii`.
- **Unrated deliveries.** The board counts completed, valid deliveries without feedback across the full scope and suggests the `feedback` command; `ack` prints the same hint without recording an evaluation.
- **`.json` context.** Accepted after `json.loads` on the same bounded bytes already read (no reopen), with a depth limit of 64 checked iteratively. Hidden, secret/config (`vault.config.json` stays refused), symlink and traversal refusals are unchanged. The hidden-file refusal is kept and now names the suffix too and points to copying only the needed excerpt into `drafts/` as `.txt`.
- **`run start --print-id`** prints only the full run UUID for scripts; it is mutually exclusive with `--json`.
- **Haiku profile** (`claude`, `low`), with no recommended route while access and effort remain unverified.
- **Hub pages.** `contract.md` defines a hub page, its shape and frozen `*-historico-*` snapshots; a "recent movement" line leaves only when it no longer changes a current decision, never by age alone. TRANSCRIPT step 5 now applies the shape rule that INGEST already had.
- **Form warnings in `thresholds`.** A separate section, which does not change the exit code, lists current hub pages above 40 KB, `summary` values above 600 characters and `log.md` entries out of descending date order (listed, never reordered). LINT cites them.

- **Board fixes found in review.** `clock()` switches to days above 24 hours; native columns were narrowed so the pasteable session id fits whole at 100 columns again; `--compact --ascii` converts before measuring; `wrap()` always advances.

**Rollback to 7.21.0** reads 7.22.0 state: extra job and native fields are ignored. One visible effect: 7.21.0 refuses `.json` context, so a job submitted with a `.json` file shows as stale there, and `accept` records `accepted_stale`. State is not corrupted.

Deferred to 7.23.0 with their own design: parallel run stages, early Grok refusal without spawning the CLI, and tag publication through the Git helper.

## 7.20.1 - 2026-09-19

- `board --all-sessions` shows the full session id instead of an 8-char prefix, so it can be copied straight into `--session`. The SESSÃO column now competes for width on equal footing with the progress bar and other columns — it degrades from the full id down to a shortened, ellipsis-clipped one only when the terminal is too narrow, and always fits without breaking row alignment.
- Fixed a layout edge case where a narrow MOTIVO column could pad to exactly the length of its own header, leaving it glued to the next column with no visible gap.

## 7.20.0 - 2026-09-18

- Codex parse results now capture a sanitized structural schema (event type to top-level key names, never values) so a missing `model_reported` is diagnosable from `job.json` instead of unexplained; `history()` flags when that schema is available.
- Codex agent messages are concatenated in order instead of keeping only the last one; when more than one is emitted, the count is recorded in the job's `limitations`.
- `history()` now surfaces the provider-reported reasoning-token counter (Codex top-level `reasoning_output_tokens`, Claude's nested `output_tokens_details.thinking_tokens`) alongside the existing usage counters.
- `delegation.md` documents that `--effort` is a parameter sent to the CLI, never confirmed by it; the reasoning-token counter is the only indirect signal, and zero does not distinguish "did not need to reason" from "effort was not applied".
- Fixed a `diagnose_failure` false positive: an incompatible-argument error whose stderr echoes the CLI's own `--sandbox` flag no longer misclassifies as `environment_blocked`; the pattern now requires an actual denial/violation phrase near "sandbox".
- `provider_failed` (an unrecognized CLI failure) now blocks further attempts against the same provider in the session, matching the existing behavior for classified failures like `model_unavailable`.

## 7.19.0 - 2026-09-16

- Added a Codex-native long-task supervision contract: exclusive write ownership, evidence-bearing returns, principal verification and reconciliation before completion.
- Distinguished host-native subagents from external `delegate.py` jobs across the Codex adapter and delegation runbook. Native reports remain declared metadata and do not imply process telemetry.
- Defined event-driven course correction and clarified that the 15-minute native-report expiry is a stale-state TTL, not a heartbeat, callback, failure signal or retry authorization.
- Added Astra as a contextual long-horizon orchestration class without changing the existing principal default or promoting an unverified model ranking. Efficiency remains an end-to-end measurement, not an assumed benefit of delegation.

## 7.18.0 - 2026-09-09

- Board watch survives expected state-read failures with an explicit unavailable frame and last successful read time. It retries on the next interval without presenting old rows as live or exposing private errors.
- Board metadata reads skip source hashing and fail promptly on lock contention, while preserving orphan-supervisor recovery. Full result/acceptance integrity checks remain unchanged; malformed display/native state is rejected.
- Keyword search normalizes case/accents, supports quoted exact phrases and optional `--all`, and keeps broad OR matching by default. Search remains read-only and dependency-free; fixed synthetic retrieval checks compare against the prior ranking.
- Added reusable knowledge-mini-v1 screening fixture: eight synthetic cases, two positive controls, separate blind case/spec/semantic rubric. Reuses model-eval with no automatic calls, new skill, service or model-default changes. Private model outputs are not part of the release.

## 7.17.0 - 2026-09-09

- Live delegation board defaults to active jobs plus completions from the last five minutes. Expired rows leave the screen, never the stored history; `--recent-seconds` adjusts the window and `--history` restores historical inspection.
- Native helpers get individual model/task/session/reported-state rows, distinct from externally supervised jobs. Unknown native state remains explicit; the principal is not falsely presented as monitored.
- Old unread deliveries and unacknowledged failures remain compact alerts instead of filling the table. Indicator totals retain the full scope.
- Watch redraws interactive terminals even with colors disabled; narrow all-session layouts and wide Unicode text respect terminal columns. Native report confirmations display the supplied model.

## 7.16.0 — 2026-09-09

- Delegation available by default for new sessions, without automatic model calls. Explicit session/global stops survive updates; configurable 6 calls/session and 4/provider defaults.
- Principal-aware local-first routing gate with declared marginal benefit, independent work or critical review; requested identity remains distinct from served identity. Sonnet medium / Opus high routes are policy hypotheses, not benchmark winners.
- Expiring manual provider-quota snapshots; no inferred balances or silent provider/billing substitution. Retry rechecks policy, records diagnosis, and does not bypass call caps or failed-provider protection.
- Sanitized classification for provider failures even when a CLI exits zero. Raw logs remain private/discarded; completed transport is not model quality.
- Compact terminal indicator and live board, separating external lifecycle from explicitly reported native agents. Claude statusline integration preserves custom settings and hooks; Codex/Grok use the supported terminal panel.
- Ingestion reconciles obsolete pending decisions, preserves source-only boundaries and causal uncertainty, and separates dated current state from linked history. Additional semantic evaluation cases remain separate from structural checks.
- Release workflow: change source payload, test, increment VERSION, commit/tag/push, install target and verify version/manifest. No direct installed-target code edits.
