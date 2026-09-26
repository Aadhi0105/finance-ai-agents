# Agent 1: execution and reporting (Batch 3)

Batch 3 separates model completion, financial approval, and artifact generation.
A model finishing its answer does not establish that the financial evidence is
complete or that its report is approved.

## Execution and tool contracts

The shared loop returns a `RunOutcome` with status `completed`, `incomplete`, or
`failed`, plus the text, reason, and iteration count. Only an `end_turn` response
with nonempty text and no outstanding tool requests completes. Truncation,
refusal, exhausted offline scripts, and the iteration limit are incomplete.
Invalid tool protocols and model exceptions fail. Interruptions are incomplete.
All text blocks in a final answer are retained. Agent 2's triage wrapper keeps
its string interface and labels incomplete or failed results.

Tool arguments must satisfy the advertised JSON schema before execution.
Agent 1 rejects extra arguments, malformed tickers, and a ticker that differs
from the run subject. Nonfinite JSON values are rejected. Unknown tools, invalid
arguments, exceptions, and interrupted tool calls produce recorded failures;
the model can recover from ordinary tool failures in a subsequent turn.
Exceptions retain their type, not potentially sensitive provider messages.
Unsupported model content blocks fail rather than being silently discarded.

Audit inputs and outputs are copied independently from working results and
from callers. Reading `state.calls` returns another copy. Refreshing financials
or prices removes dependent ratios, DCF, peers, and downstream derived results;
refreshing consensus or history also invalidates their derived comparisons.
The original call history remains available for validation and inspection.
This protects against accidental aliasing, not deliberate tampering with files
or private Python attributes.

## Saved execution evidence

Each run has a unique timestamp/UUID output directory. `model.json` is saved
before the first model call and checkpointed around model and tool execution.
It records the original note template, grounded note, current results, complete
call history, invalidations, conversation, system prompt, goal, tool schemas,
model configuration, stop reasons, token usage when supplied, request IDs,
durations, execution status, and any operation in flight. Git provenance records
the full commit and whether the checkout was dirty at run start. Environment
variables and API keys are not dumped into the record.

Terminal checkpoints retain the final note. A storage error stops further model
work. A process kill or unavailable disk can still prevent a final checkpoint;
inspect the last saved status and in-flight operation rather than assuming
completion. Usage on a response that never arrives cannot be recovered locally.

## Report lifecycle

Analysis is saved before chart data acquisition or importing matplotlib.
History acquisition and each chart render are independent. Failed charts are
labelled unavailable; other charts and the underlying analysis remain saved.
Empty, unordered, duplicate-date, nonfinite, or nonpositive price histories are
rejected. Artifact errors require a review report and a failure exit code.

JSON, PNG, and self-contained HTML writes use same-directory temporary files,
flush/fsync, and atomic replacement. This is atomic per file, not a transaction
across the entire directory. Artifact completion is recorded only after the
HTML write succeeds. A report lock serializes rebuilds. Old approved and review
HTML files are removed before revalidation/rendering; a failed rebuild cannot
leave an old approved report presented as current.

`python run.py --rebuild PATH/model.json` uses saved evidence only, with no model
or data-provider calls. It reruns grounding and the current validation gate,
including date checks and explicit execution-completion evidence. A saved
`pass` verdict is never trusted. Legacy records without completion evidence
require review. Rebuild retries chart rendering errors but preserves historical
acquisition failures. The rebuilt report is not guaranteed byte-identical:
validation policy, evidence age, renderer versions, and rebuild timestamps matter.

## Command line and exits

Default execution is offline ASML.AS. `--offline TICKER` forces fixture data even
when the ambient environment selects yfinance; it does not load `.env`.
`--live TICKER` requires credentials and selects yfinance. `--peers` is live-only;
`--output` selects the new-run root and `--trace` prints the execution trace.
Modes are mutually exclusive and malformed arguments fail before execution.

| Code | Meaning |
| --- | --- |
| 0 | Completed execution, approved evidence, successful artifacts |
| 1 | Execution or artifact failure, including partial chart failure |
| 2 | Invalid command-line usage |
| 3 | Completed execution and successful artifacts; financial review required |
| 4 | Incomplete execution with no artifact failure |
| 130 | Interrupted execution or reporting |

Offline fixture runs normally return 3. Runtime dependencies include jsonschema
and filelock; offline execution is not a standard-library-only installation.
Tests use local fixtures and simulated failures, with no paid LLM calls.
[Batch 4 verification](agent1-verification.md) adds full CLI acceptance checks,
controlled provider observations, enforced peer selection, and schema-version
checks.
