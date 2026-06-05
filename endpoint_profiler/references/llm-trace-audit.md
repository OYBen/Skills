# Source Sampling Audit

Run this audit after every endpoint profiler execution. It is a quality gate
for correctness, completeness, and redundancy of `endpoints.json`; it is not a
topology report.

## Purpose

The audit samples source files across code layers, reads those source samples,
derives the ingress and egress endpoint evidence visible in the sampled files,
and compares that evidence against `endpoints.json`.

The question is:

```text
For sampled source files, are all visible endpoint contracts represented
correctly in endpoints.json, with no unsupported or redundant endpoint records?
```

## Sampling Rules

1. Group production source/config files by layer, such as:
   - controller/API/router/resource
   - listener/consumer/event handler
   - scheduler/job/task
   - client/Feign/Retrofit/HTTP wrapper/SDK facade
   - service/domain orchestration
   - repository/mapper/data access
   - config/binding/runtime metadata
2. For each layer with endpoint-looking evidence, sample 10% of files, with a
   minimum of one file per layer.
3. Prefer Graphify node metadata and source-file candidates to identify sample
   files and reduce token cost.
4. If Graphify evidence is missing, ambiguous, or incomplete, read source files
   directly.

## Required Checks

For every sampled source file:

1. Read Graphify/source evidence for endpoint-looking constructs.
2. Derive expected endpoint kinds and identifiers only when there is sufficient
   business contract evidence. Do not treat framework facilities, generic
   starter code, DTO fields, logging-only FQN strings, dynamic data-access
   wrappers, or cache/message infrastructure helpers as endpoints merely
   because they contain words such as `fqn`, `cache`, `topic`, `select`, or
   `send`.
3. Compare expected endpoints with `endpoints.json`.
4. Mark the row `PASS` only when sampled source evidence is complete and
   correct in `endpoints.json`.
5. Mark `FAIL` for missing, incorrectly classified, wrong-direction,
   wrong-identifier, unsupported, or redundant endpoint records.

When the sampled file's local evidence is ambiguous, inspect enough upstream
and downstream context to decide semantic sufficiency before marking a missing
endpoint. Examples include the caller that supplies a topic/FQN, the callee that
persists or publishes the contract, annotations on the referenced model class,
or the repository/entity that resolves a `ClassName.FQN`. If that context still
does not identify a stable business contract, classify the sample as a
false-positive candidate instead of failing the inventory.

## Rule Gap Discovery

Include a section named exactly `Rule Gap Discovery`.

Rows with missing source evidence in `endpoints.json` are rule-gap candidates.
Report expected endpoint kinds, representative source files, whether matching
records exist, verdict (`COVERED_BY_RULE`, `MISSING_ENDPOINT_RULE`,
`FALSE_POSITIVE_CANDIDATE`, or `NEEDS_DEEPER_REVIEW`), and suggested rule
updates.

## Required Report

Write:

```text
<output_dir>/endpoint_llm_trace_audit_<YYYYMMDD>.md
```

The report must include:

- input source root, endpoint JSON path, graphify index path, and audit date
- `Audit Verdict: PASS` or `Audit Verdict: FAIL`
- `Source Sampling Audit`
- layer-by-layer 10% sampling summary
- one row per sampled file with expected endpoint evidence, endpoint records
  found in `endpoints.json`, verdict, and notes
- `Rule Gap Discovery`
- findings grouped by correctness, completeness, and redundancy

## Boundaries

- This audit may use call or data-flow tracing as a validation aid, but tracing
  is not the objective.
- Do not write topology edges into `endpoints.json`.
- Prefer Graphify evidence first; read source when graph evidence is
  insufficient.
- Do not fail the audit on framework/basic infrastructure code that has no
  direct business endpoint effect.
- Do not equate data-model FQN YAQL with physical `DB_TABLE`; require explicit
  physical table evidence such as ORM table annotations or table-position SQL
  over a physical table identifier.
