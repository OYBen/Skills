# Strategies and Validation

## Strategies Considered

1. Tighten instructions only.
   - Result: rejected. It would not prevent future placeholder audits.
2. Add verifier-only ratio check.
   - Result: partial. It catches the failure but does not help agents produce better audits.
3. Add a reusable deterministic trace-audit helper plus verifier quality gate.
   - Result: selected. It creates an executable source-reading path and a regression guard.
4. Build full Java semantic compilation.
   - Result: deferred. Too large for a focused patch and likely brittle across mixed Maven modules.

## Validation

1. Python syntax check.
   - Command: `python -m py_compile scripts/generate_trace_audit.py scripts/verify_endpoint_profiler.py`
   - Result: PASS.
2. Generate audit on MA marketing automation output.
   - Command: `python scripts/generate_trace_audit.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out --source-root D:/kylin_product_repo/MA/marketing-automation-develop --graph-skip-if-missing`
   - Result: PASS.
3. Source trace status distribution.
   - Result: unresolved reduced to 14/62 status mentions after bounded call-graph tracing.
4. Full endpoint profiler verifier.
   - Command: `python scripts/verify_endpoint_profiler.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out`
   - Result: PASS.
5. Graphify-missing behavior.
   - Result: graph audit skip report generated with `GRAPH_AUDIT_SKIPPED_NO_GRAPHIFY_INDEX`.
