# Task Contract

Date: 2026-06-03

User request:

- Evolve `endpoint_profiler` with `metaSkill`.
- Ensure the two required audit items are implemented with the corrected semantics.

Resolved controls:

- iterations: 1 focused existing skill patch
- strategies: targeted semantic repair, no broad rewrite
- validation_trials: direct script run plus verifier run
- audit_required: true

Correct audit semantics:

1. Source Sampling Audit
   - Sample 10% of source files from each code layer.
   - Read Graphify evidence first, then source code when graph evidence is insufficient.
   - Infer ingress/egress endpoint kinds from sampled source files.
   - Pass only when the inferred sampled source endpoints are present, correct, complete, and non-redundant in `endpoints.json`.

2. Endpoint Trace Sampling Audit
   - Sample already extracted/traced endpoints.
   - Validate whether sampled endpoint evidence and any reached endpoint evidence are present, correct, complete, and non-redundant in `endpoints.json`.
   - Its primary purpose is endpoint-profiler quality validation, not topology trace generation.
   - Read Graphify evidence first, then source code when graph evidence is insufficient.

Invariant:

- `Audit Verdict: FAIL` is the correct outcome when sampled evidence reveals missing, wrong, incomplete, or redundant endpoint extraction.
