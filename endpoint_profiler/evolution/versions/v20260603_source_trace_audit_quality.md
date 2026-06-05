# Version: v20260603_source_trace_audit_quality

## Goal

Reduce unresolved source trace audit rows and prevent placeholder audit reports from passing verification.

## Skill Changes

- Added `scripts/generate_trace_audit.py`.
  - Generates `endpoint_llm_trace_audit_<YYYYMMDD>.md`.
  - Parses production Java/Kotlin methods.
  - Follows local methods, injected fields, and interface implementation methods.
  - Classifies samples as traced, terminal, or genuinely unresolved.
  - Can write a Graphify skip audit when no graph index is available.
- Updated `SKILL.md` to make the trace helper the standard post-scan audit step.
- Updated `scripts/verify_endpoint_profiler.py`.
  - Requires documented source trace statuses.
  - Requires at least one traced or terminal source status.
  - Fails when `NEEDS_SOURCE_EXPANSION` exceeds 30% of sampled statuses for reports with at least 10 statuses.
- Updated `references/verifier.md` with the new audit quality gate.

## Tests Passed

- Python syntax check: PASS.
- New trace audit generation on `marketing-automation-develop-profile-out`: PASS.
- Full endpoint profiler verifier on target output: PASS.

## Auditor Findings

- No hardcoded target endpoint identifiers were added to reusable scripts.
- Source and output paths are runtime arguments.
- The script is intentionally heuristic, not a semantic compiler; residual unresolved rows remain allowed below the verifier threshold.

## Residual Risk

- Cross-language targets need future parser extensions.
- Deep Spring proxy behavior, lambdas, reflection, generated code, and runtime-only bindings can still require manual expansion or Graphify support.
