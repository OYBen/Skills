# SCHEDULED_JOB Rules

## Purpose

`SCHEDULED_JOB` is an ingress endpoint where time or scheduler infrastructure
invokes service behavior.

## Evidence

- `@Scheduled` methods.
- `@XxlJob` or equivalent job executor annotations.
- Scheduler configuration that names a concrete job handler.

## Identifier

- Prefer explicit job name, for example the `@XxlJob` value.
- Otherwise use `ClassName.methodName`.
- Put cron expressions and fixed-rate metadata in `match_rule`, not in
  `identifier`.
- In Java/Kotlin files with multiple classes or objects, `ClassName` must be
  the nearest enclosing type around the annotated method, not the first type in
  the file.
- Kotlin functions are valid scheduled handlers; parse `fun methodName(...)`
  the same way as Java methods.

## Exclusions

- Scheduler setup classes, executors, and thread pools are infrastructure.
- `CommandLineRunner` bootstrap logic is not a scheduled job.
