# Strategies and validation

Resolved controls:

- K / strategies = 4
- V / validation_trials = 5

## K4 strategy sketches

1. Strict verifier gate
   - Convert audit from narrative instruction into executable freshness checks.
   - Outcome: selected and implemented.

2. Audit artifact renewal
   - Re-run the target analysis and generate current source and graph audit reports after the new `endpoints.json`.
   - Outcome: selected and implemented.

3. Documentation and versioning synchronization
   - Update verifier references and save evolution records so the behavior survives future runs.
   - Outcome: selected and implemented.

4. Full automated graph traversal helper
   - Build a separate graph traversal audit helper for endpoint-to-endpoint paths.
   - Outcome: deferred. Current graph edges are useful but still mixed with structural edges (`imports`, `contains`, `references`); this needs a dedicated graph/link-analysis stage rather than a small verifier patch.

## V5 validation trials

1. Python compile check for `.agents` scripts.
   - Result: PASS.

2. Re-run endpoint profiler on `siyu-develop` using the explicit Graphify index.
   - Result: PASS, `endpoints=1932`, `services=6`.

3. Executable verifier on `.agents` skill path and current output.
   - Result: PASS.

4. Audit freshness check by file timestamps.
   - Result: PASS. `endpoint_llm_trace_audit_20260603.md` and `endpoint_graph_edge_trace_audit_20260603.md` are newer than `endpoints.json`.

5. Executable verifier from `.codex` synced skill path and current output.
   - Result: PASS.
