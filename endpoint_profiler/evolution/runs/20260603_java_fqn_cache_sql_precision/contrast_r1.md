# Contrast Analysis R1

## Failure Pattern

- Source trace could reach repository/data/cache-looking calls, but endpoint inventory missed some concrete egress contracts.
- `TaskLog.FQN` / `ActionTask.FQN` style constants were visible in YAQL strings but not emitted as datamodel endpoints.
- SQL snippets with `UPDATE costCount = ...` could be interpreted as a table endpoint named `costCount`.
- Cache invalidation via Caffeine receiver names such as `marketingTargetCache.invalidateAll()` did not produce cache-region endpoints.

## Success Pattern

- Java string constant resolver is reused for `Class.FQN` evidence.
- `Class.FQN` values matching `data.*` model FQNs emit `DATAMODEL` with `source_kind=java_fqn_constant`.
- SQL table validation rejects lower-camel field assignment identifiers in `UPDATE <field> = ...`.
- Cache receiver invalidation emits `CACHE_KEY` using a normalized cache region.
