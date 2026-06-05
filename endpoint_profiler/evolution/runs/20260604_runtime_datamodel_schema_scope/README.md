# Runtime Data Model Schema Scope

## Problem

CDP analysis showed that many `DATA_MODEL_SCHEMA` endpoints came from static
install/upgrade model inventory files, especially `dm/migration/**`,
`META-INF/scripts/**/model/**`, and `src/main/resources/json/init*.json`.
These files describe bootstrap or upgrade initialization, not typical runtime
business links. The same model families often reappear through concrete
DataAPI, SQL, analytics, or metadata API exits.

## Evolution

- Do not emit `DATA_MODEL_SCHEMA` or fallback `DATAMODEL` from static
  install/upgrade model JSON by default.
- Keep parsing those JSON files for `physicalMeta.tables` so they can still
  contribute `DB_TABLE` evidence.
- Keep `DATA_EVENT_SCHEMA` for event metadata such as `initEvents.json`.
- Keep `DATA_MODEL_SCHEMA` for runtime metadata operations such as
  `metaDataApiService.createModel`, `createEnumModel`, `cleanEnumModel`, and
  enum-model add/delete operations.
- Improve dynamic `String.format("data...%s...")` extraction, including nested
  format calls, so the identifier remains the full normalized datamodel FQN
  template instead of a partial prefix.

## Validation

- `python -m py_compile scripts/endpoint_profiler.py`
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
DATA_MODEL_SQL 26
DATA_MODEL_SCHEMA 18
ANALYTICS_MODEL_QUERY 14
DATA_API_CALL 9
DATA_EVENT_SCHEMA 4
EVENT_BUS_LISTENER 3
DATA_EVENT_PUBLISHER 3
FILE 1
```

Additional checks:

- `DATAMODEL`: 0
- Static `DATA_MODEL_SCHEMA` hits from migration/init paths: 0
- Partial `data.mdm.publicenum.cdp` schema prefix: absent

