# Changes

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
