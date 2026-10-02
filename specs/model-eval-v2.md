# Personal evaluation v2: implementation boundary

This revision builds on `model-eval-v1.md`. Public source contains generic fixtures and
software only. Experiments, model outputs and human feedback remain private in the target.
The release implements an instrument, not proof that a particular model is best.

## Candidate coverage and effort

New plans require requested effort high or above. `inventory` discovers the configured
aliases dynamically; explicit profiles extend the inventory. `inventory --doctor` checks
the existing CLI interface without running a model. Availability is dated and distinct
from served identity, access to the model and confirmation of effort. Unknown is not zero.
Unavailable configurations stay visible and are not submitted or silently substituted.
The maximum-call budget counts eligible trial slots and must be checked before creation.
Higher effort labels remain separate configurations, not assumed equal computation.

The manifest freezes inputs, rubrics, local context, executor source and optional comparison
policy. Historical formats remain readable. New execution against changed source/context
requires a new plan. No install, unit test, plan, calibration or report starts paid calls.

## Execution modes

Text trials use the existing `delegate.py` supervisor with the frozen provider/model/effort,
call ceiling, concurrency, timeout and no retry. Interrupted submission remains ambiguous
until reconciled. The explicit reconcile command can bind an identity-checked known job or abandon an interrupted attempt while preserving its artifacts; it never retries the model. Collection cannot invent a completed response.

Workspace tasks use a host-managed bridge. Prepare exports candidate-visible inputs into a
fresh external temporary workspace, outside the vault and experiment tree, and leaves private scoring material outside it. The host executes the task
with its own authorized tools; finish independently evaluates the final state and collects
artifact evidence. This is not an autonomous background runner, a new provider integration,
or an operating-system sandbox. Path separation is a procedural guard when the host can
read the entire filesystem. The operator must preserve the blind context boundary.

Trusted structural checks do not execute candidate code. Python execution requires explicit
selection of the isolated Docker path, with network disabled and bounded resources. A
missing runtime or failed isolation gate is operationally unavailable, never a passing test.
Expected results stay on the host. The worker shares a Python interpreter with candidate
code, so introspection can undermine observations such as argument mutation. These are
behavioral tests, not proof against malicious implementations tailored to the tests.
The host's identity and action trace are attributed as observed or declared; neither a
success message nor a claimed trace proves unobserved actions happened.

Research fixtures use frozen documents and cannot measure current web discovery. HTML or
document structure checks cannot certify rendered visual quality. An observed visual audit
is required before making that stronger claim. No candidate task writes the live vault.

## Judging and revisions

V2 grades identify the evaluator and configuration, rubric version and authorship conflict.
They record each criterion separately, with pass/partial/fail/unknown and literal evidence.
Critical failures stay distinct from ordinal quality and minor format/style issues. A judgment made only by conflicted authors or potential self-judges needs independent review before technical acceptance.
Judges require effort high or above. Human feedback is explicit and separately attributed.

Grades are append-only through the supported API. This is a local integrity contract, not cryptographic protection against an operator able to rewrite every file. A revision supersedes a specific active record for the same trial
and evaluator; history remains available. Duplicate, cross-trial, foreign-evaluator and
branched revisions are refused. Reports use active judgments, expose disagreement and do
not turn the most severe unadjudicated opinion into a settled fact.

`judge-packet` exports original responses, rubric versions and instructions for a named
judge. It makes no model call. Local disk access can defeat blinding; packet masking is
procedural. Candidate metadata is omitted. Response content is never cleaned to improve
a score. Native or delegated judges consume the packet under a separately declared budget;
the principal reviews and imports their actual output.

`calibrate` compares an attributed set of reference judgments with supplied assessments.
It reports coverage, criterion agreement and critical disagreements. Missing or unknown
criteria do not count as agreement. Synthetic references are distinct from explicit human
references. The report neither authenticates a claimed human author nor creates preference
feedback or automatic qualification. Each calibration preserves its input in a new receipt.

## Comparison and personal recommendation

Reports distinguish operational failure, content failure, missing evidence and explicit
deadline failure. They retain the full inventory and explain excluded configurations.
Observed configurations can be compared on matching cases without requiring every other
candidate to be available. Comparisons never claim superiority over unobserved candidates.

Paired case results, repetitions and descriptive variation remain visible. Practical margins
must be declared before claiming descriptive dominance. A tiny timing difference in one
trial is not evidence of a generally better model. Distinct case IDs are not proof of
methodological independence and no fixed count establishes validity.

Technical observed success does not imply personal acceptance. Preparation, review,
integration, corrections, preference and time to accepted delivery need explicit human
observations. Costs require provenance and compatible units; subscription usage estimates
are not bills. General recommendations require an appropriate action distribution and
adequate observations, otherwise remain unavailable. No result changes default routing.

## Acceptance

- Freeze/integrity, paths/symlinks, immutable revisions and no accidental model calls.
- Unavailable candidate does not erase valid matched comparisons.
- Infrastructure failure cannot masquerade as low intelligence or content failure.
- Unknown feedback cannot produce personal approval.
- Genuine workspace prepare/change/finish detects final-state success and violations.
- Candidate code never executes outside the explicit isolation gate.
- Judge packets preserve output, hide identity metadata and specify high effort.
- Calibration distinguishes missing data, critical disagreement and synthetic references.
- Installed CLI lifecycle, full repository test suite and real target manifest verification.

Model benchmarking and human calibration remain measured operations after installation,
with their own visible budgets and frozen cases. Passing software tests is not a benchmark
result, and a smoke demonstration is not a model recommendation.
