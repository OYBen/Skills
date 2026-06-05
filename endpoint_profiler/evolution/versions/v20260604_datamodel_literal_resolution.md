# v20260604_datamodel_literal_resolution

Endpoint Profiler now resolves or excludes fallback datamodel literals more
aggressively.

Highlights:

- Constants and multiline SQL strings containing `data.*` FQNs are propagated to
  DataAPI/sqlSupport/DataApiSupport wrapper calls.
- Metadata enum and schema operations emit `DATA_MODEL_SCHEMA`.
- Configurable default target FQNs and cleanup wrappers emit SQL/model-schema
  modes when visible.
- `@DataModel` annotations, DTO/default fields, config keys, error codes, and
  mock/example literals are excluded from endpoint output.

On CDP this reduced fallback `DATAMODEL` endpoints from 62 to 0 while preserving
verifier PASS.
