# Personal model evaluation v1

Implementation contract, 2026-10-02. Python standard library only. Reuse delegate.py for all model execution. No supervisor/provider reimplementation. No automatic routing changes, model calls during installation/tests, or wiki ingestion. Generic synthetic fixtures only in public source; private experiments under vault drafts/model-eval/.

## Deliverables and ownership

- Engine agent: `payload/harness/scripts/model-eval.py`, `payload/harness/scripts/thinker_model_eval/core.py`, `__init__.py`, `tests/test_model_eval_core.py`.
- Reporting agent: `payload/harness/scripts/thinker_model_eval/report.py`, `tests/test_model_eval_report.py`.
- Cases agent: `payload/harness/evals/workload-v1/**`, `tests/test_model_eval_workload.py`.
- Principal: integration, adversarial tests, operation/skill/docs, version, installer verification and private pilot. No concurrent edits in another owner's paths.

## Data contract

suite.json: `{schema_version:1,id,title,cases:[{id,family,prompt:"cases/ID.md",rubric:"rubrics/ID.json",max_words:450,split:"development"|"holdout"}]}`. Paths relative to suite root, regular files within root, no symlinks/traversal. Rubric JSON `{criteria:[{id,description,critical:boolean}],reference_notes:string}`. Exactly 12 synthetic cases, six families: retrieval, ingestion, analysis, research, code, communication. Two per family: development and holdout. Research uses supplied fixed sources; code delivers code text, never executes arbitrary candidate code. Explicitly label bounded text screening, not end-to-end qualification. Prompts <= 6000 UTF-8 bytes, output <= 450 words by default; code up to 700. No hidden answers in prompts; no auto-scoring semantics by keyword.

Frozen manifest.json: `{schema_version:1,id,created_at,suite_id,session,mode:"screening"|"candidate"|"regression",profiles:[{id,model,provider?,effort}],cases:[suite case objects with copied paths],repeats,max_calls,timeout,concurrency,hashes:{relative_path:sha256},environment:{...},quality_floor:3,minimum_trials:3}`. Hash frozen manifest content separately if necessary. Frozen copied input files; changes rejected before execution, grading/reporting. Output trial records in `trials.json`: list `[{id,blind_id,case_id,family,profile_id,repeat,status,job_id,response,execution_seconds,queue_seconds,model_reported,usage,cost_estimate,checks:{nonempty:boolean,word_limit:boolean},trajectory:{status:"unknown"|"pass"|"fail",violations:[]},limitations:[]}]`. Missing observability is null/unknown, not zero. Cost estimates have provider/currency/provenance or are null. Provider requested model/effort never equals confirmed identity by inference.

`grades.json`: list `[{trial_id,evaluator,quality:0..4,critical_failures:[string],notes,evidence:[string]}]`. Append immutable assessments; no duplicate trial/evaluator; reject unknown IDs/nonfinite values/booleans/empty justification. `feedback.json`: list `[{trial_id,reviewer,preference:"use"|"revise"|"reject",review_minutes:number|null,corrections:int|null,notes}]`; explicit human feedback only, never inferred from model grade. Optional `trajectory.json`: list `[{trial_id,evaluator,status:"pass"|"fail",violations:[],notes}]`, independent audit of observable actions (not hidden reasoning). Reports must preserve unknown if no audit.

## Core interface / CLI

`model-eval.py --vault PATH plan --suite PATH --profile ID:EFFORT [repeat] --case ID [repeat] --repeats N --max-calls N --timeout 180 --concurrency 2 --id ID --mode candidate` freezes an experiment without model calls. Support explicit new profiles via JSON file [{id,provider,model,effort}] (`--profiles-file`). Runtime paths confined to real vault drafts/model-eval; IDs safe slugs, no escaping via symlink. No implicit holdout selection. Validate bounded positive integers, unique case/profile IDs, total calls <= cap before writing.

`run --id ID`: resumable, bounded submission via delegate.py route/submit/result/ack using manifest session and explicit model/effort. Runtime checks delegation status enabled/concurrency compatible; never activates or changes limits silently. Reserve trial/submitting state before submit, never auto-resubmit ambiguous interrupted submission. Stop new submissions on failure, preserve/drain existing jobs. No automatic retries. Use --prompt with selected case contents only (not rubric or manifest); instructor adds word limit. Refresh results with `collect --id ID`, idempotent. Prefer run submitting up to available slots then returning; repeated run/collect advances bounded queue. CLI prints exact progress/board command and remaining work, no background service. Result parser grounded in existing delegate API.

`blind --id ID`: exports blind packet JSON with only blind_id, case prompt, rubric, response; shuffled order stable for experiment, no model/timing/cost identity. Mapping retained separately; blinding is procedural, not a security boundary against local disk access.

`grade --id ID --file PATH`, `feedback --id ID --file PATH`, `trajectory --id ID --file PATH`: validate/import arrays; core can accept blind_id resolving internally for grading. `report --id ID` writes report.json/report.md via report module; `verify --id ID` checks frozen inputs. No report silently treats unknown as pass.

## Report API

`build_report(manifest, trials, grades, feedback, trajectory=None) -> dict`; `render_markdown(report) -> str`. Core owns filesystem and validation. Report groups per profile/family, uses full planned case/repeat denominator, shows completion/graded/missing/error counts and coverage. Require complete compared coverage and matching cases before comparisons. A critical failure, failed check or failed trajectory blocks that family; unknown trajectory or missing grades means inconclusive. Default minimum 3 independent cases (not repeats counted as cases) per family for qualified recommendations; small suite stays provisional. Feedback separate and unknown without input. Quality distribution, median execution, per-provider cost estimates only when complete provenance, no cross-provider token aggregation. Deterministic Pareto only among fully observed comparable eligible candidates; ties stay ties. No arbitrary scalar combining quality and cost/trajectory. No general winner with incomplete family coverage. Do not call repeat trials independent cases. All recommendations evidence-bounded, dated, never installed as defaults.

## Validation and implementation plan

1. Build engine, reports and fixtures in parallel.
2. Test freeze/tamper, traversal/symlinks, no rubric leakage, no accidental paid calls, budgets, resume/idempotence, failures, partial grades and ties. Use fake delegate transport via injection/mocks, never fake scores presented as real.
3. Integrate documentation and run full repository tests; install into temporary vault and verify.
4. Install authorized implementation into user's target via installer and verify manifest/version. Public release operations remain subject to publication scope.
5. Live smoke: three declared profiles high, two development cases, six total calls, concurrency two, timeout 180, no retry. Independently read outputs and record principal grades, human feedback unknown. Distinguish smoke result from qualification.

No data from user vault enters source repo. Extending real full workflows is a later suite, explicitly not claimed complete by this text-screening version.
