# Task Contract

- Skill: endpoint_profiler
- Requested meta-skill: metaSkill
- Objective: evolve the endpoint profiler skill so source trace audits do not contain large numbers of unresolved endpoints.
- Target symptom: the generated `endpoint_llm_trace_audit_20260603.md` for `D:/kylin_product_repo/MA/marketing-automation-develop` marked almost every sampled endpoint as `NEEDS_SOURCE_EXPANSION`.
- Iterations: 1 focused existing-skill patch.
- Strategies K: 4.
- Validation trials V: 5 lightweight checks.
- Pass threshold: 75%.
- Coverage skip threshold: 80%.
- Script limits: warning=200 lines, critical=400 lines.
- Audit required: true.

## Decision Axes

- Trace source: invariant. Source trace audits must read source/config and not merely create placeholder rows.
- Source root and output dir: parametric. Scripts must derive these from runtime arguments or `endpoints.json`.
- Endpoint identities/counts: instance-specific. Do not hardcode target endpoint names into reusable logic.
- Call graph depth: parametric. Use bounded local source expansion and keep unresolved status available for real source gaps.
- Verifier threshold: invariant default. Large unresolved ratios indicate a bad audit, while a small unresolved residue is acceptable for incomplete static graphs.
