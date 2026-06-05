# Version: v20260603_loyalty4_kotlin_event_schedule

Purpose:

- Improve endpoint identity extraction for Kotlin/Spring scheduled jobs and event listeners.
- Record Graphify partial-coverage audit behavior for multi-module projects.

Changes:

- `scripts/endpoint_profiler.py`
  - Added nearest enclosing Java/Kotlin type lookup.
  - Added Kotlin `fun` method fallback.
  - Parsed `@EventListener(ApplicationReadyEvent::class)` and Java `.class` annotation arguments into event identifiers.
  - Used method/parameter fallback instead of generic `spring-event-listener`.
- `scripts/verify_endpoint_profiler.py`
  - Fails generic `EVENT_BUS_LISTENER` identifier `spring-event-listener`.
  - Adds loyalty4 regression checks for `RemindJob.executeInternal` and `ApplicationReadyEvent`.
- `rules/types/event_bus_listener_rules.md`
  - Documents Kotlin `::class`, Java `.class`, parameter-derived event type, and method fallback policy.
- `rules/types/scheduled_job_rules.md`
  - Documents nearest enclosing type for multi-class Java/Kotlin files.
- `references/graph-edge-trace-audit.md`
  - Documents root graph/shard coverage checks and `GRAPH_INDEX_PARTIAL`.

Validation:

- Profiler run on `D:/kylin_product_repo/loyalty4` passed.
- Verifier passed on `D:/kylin_product_repo/loyalty4-profiler-out`.

Known residual risk:

- `loyalty4` graph coverage is partial for analysis/stream modules in the available root/shard graphs.
- Cache key `all` is valid but semantically weak; richer Caffeine/cache identifier derivation may be a future evolution target.
