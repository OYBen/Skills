# DATA_MODEL_SQL Deprecated

## Problem

`DATA_MODEL_SQL` treated SQL over `data.*` model FQNs as a standalone endpoint
kind. CDP analysis showed this is misleading: SQL is the query language used by
a data proxy, client, stream call, or analytics engine. It is evidence about an
access mode, not an independent endpoint boundary.

## Evolution

- Stop emitting new `DATA_MODEL_SQL` endpoints.
- Reclassify ordinary DataAPI/model SQL execution as `DATA_API_CALL` with
  `query_language: SQL` and `access_mode: dataapi-sql`.
- Reclassify fetch/WebSocket/streaming SQL execution as `DATA_API_STREAM` with
  `query_language: SQL` and `access_mode: dataapi-stream-sql`.
- Keep `ANALYTICS_MODEL_QUERY` when OLAP/HTAP/bitmap/columnar/analytics-engine
  evidence is visible.
- Update quality audits so SQL evidence suggests `DATA_API_CALL` or
  `ANALYTICS_MODEL_QUERY`, not `DATA_MODEL_SQL`.

## Validation

- `python -m py_compile scripts/endpoint_profiler.py scripts/verify_endpoint_profiler.py scripts/generate_quality_audits.py`
- `tests/fixtures/datamodel_modes`: PASS
- `tests/fixtures/db_table`: PASS
- CDP output: `D:\kylin_product_repo\CDP\CDP-profile-out`
- CDP verifier: PASS

CDP endpoint distribution after this evolution:

```text
HTTP_API 425
HTTP_CALL 181
DB_TABLE 114
SCHEDULED_JOB 42
DATA_API_CALL 28
DATA_MODEL_SCHEMA 18
ANALYTICS_MODEL_QUERY 14
DATA_API_STREAM 6
DATA_EVENT_SCHEMA 4
EVENT_BUS_LISTENER 3
DATA_EVENT_PUBLISHER 3
FILE 1
```

Additional checks:

- `DATA_MODEL_SQL`: 0
- DataAPI endpoints carrying `query_language: SQL`: 26
- `ANALYTICS_MODEL_QUERY`: 14

