# Strategies and validation

Resolved controls:

- K / strategies = 4
- V / validation_trials = 5

## K4 strategy sketches

1. Kotlin identity correctness
   - Fix scheduled/event listener identifiers for Kotlin syntax and multi-class files.
   - Outcome: selected and implemented.

2. Audit-first validation
   - Keep the prior mandatory audit gate and generate fresh source/graph audits for the new target.
   - Outcome: selected and implemented.

3. Graph coverage honesty
   - Treat root graph and shard coverage as audit inputs; report partial graph coverage instead of inventing paths.
   - Outcome: selected and implemented in audit guidance.

4. Expand external egress families
   - Investigate why no HTTP_CALL/MQ/SDK/FILE endpoints were emitted for `loyalty4`.
   - Outcome: deferred to a future focused evolution after the current verifier/audit loop passes.

## V5 validation trials

1. Python compile check for `.agents` scripts.
   - Result: PASS.

2. Re-run endpoint profiler on `D:/kylin_product_repo/loyalty4`.
   - Result: PASS, `endpoints=358`, `services=4`.

3. Regression check for Kotlin identifiers.
   - Result: PASS. `RemindJob.executeInternal` and `ApplicationReadyEvent` are present; `spring-event-listener` and `RemindRedisConfig.executeInternal` are absent.

4. Required audit freshness.
   - Result: PASS. Source and graph audit reports were generated after current `endpoints.json`.

5. Executable verifier on current output.
   - Result: PASS.
