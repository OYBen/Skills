# v20260604_datamodel_sql_schema_event_modes

Endpoint Profiler now distinguishes semantic datamodel FQNs by access mode
instead of treating every unresolved `data.*` or `event.*` string as
`DATAMODEL`.

New egress kinds:

- `DATA_MODEL_SQL`: SQL over semantic `data.*` model FQNs.
- `ANALYTICS_MODEL_QUERY`: OLAP/HTAP/bitmap/streaming SQL model access.
- `DATA_MODEL_SCHEMA`: model create/update metadata and migrations.
- `DATA_EVENT_SCHEMA`: `event.*` event definitions.
- `DATA_EVENT_PUBLISHER`: `event.*` publish calls.

This version also excludes property-like `data.redis.*` / `spring.data.*`
configuration keys and prevents duplicate fallback `DATAMODEL` records when a
stronger access-specific kind is visible.
