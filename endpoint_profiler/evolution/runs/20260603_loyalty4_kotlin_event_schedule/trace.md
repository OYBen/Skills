# Trace

## Iteration 1

Initial run:

```text
endpoints=358
services=4
```

Verifier failed only because mandatory audit reports were missing.

New project-specific extraction issue found by inspection:

- `@Scheduled` in `RemindScheduler.kt` was emitted as `RemindRedisConfig.executeInternal`, but the annotated method is inside the later Kotlin class `RemindJob`.
- `@EventListener(ApplicationReadyEvent::class)` was emitted as generic `spring-event-listener`, losing the event contract.

Patch:

- Added nearest enclosing Java/Kotlin type lookup.
- Added Kotlin `fun` method fallback.
- Added Spring/Kotlin event listener identifier parsing for `::class`, Java `.class`, Java method parameters, and Kotlin method parameters.
- Added verifier regressions for `RemindJob.executeInternal`, `ApplicationReadyEvent`, and absence of generic `spring-event-listener`.

## Iteration 2

Re-ran profiler:

```text
endpoints=358
services=4
```

Confirmed corrected endpoint identifiers:

- `SCHEDULED_JOB RemindJob.executeInternal`
- `EVENT_BUS_LISTENER ApplicationReadyEvent`

Generated required audit reports:

- `D:/kylin_product_repo/loyalty4-profiler-out/endpoint_llm_trace_audit_20260603.md`
- `D:/kylin_product_repo/loyalty4-profiler-out/endpoint_graph_edge_trace_audit_20260603.md`

Verifier result:

```text
Endpoint profiler verifier
Input: D:\kylin_product_repo\loyalty4-profiler-out
Result: PASS
```

## Iteration 3

Documentation and generalization patch:

- Updated `rules/types/event_bus_listener_rules.md` for Kotlin `@EventListener(...::class)`, Java `.class`, parameter-derived event types, and method fallback.
- Updated `rules/types/scheduled_job_rules.md` for Kotlin functions and nearest enclosing type in multi-class files.
- Updated `references/graph-edge-trace-audit.md` for root graph vs shard coverage and `GRAPH_INDEX_PARTIAL`.
