# Trace

Implemented endpoint taxonomy and extractor updates:

- Added egress kinds:
  - `DATA_MODEL_SQL`
  - `ANALYTICS_MODEL_QUERY`
  - `DATA_MODEL_SCHEMA`
  - `DATA_EVENT_SCHEMA`
  - `DATA_EVENT_PUBLISHER`
- DataAPI wrapper SQL calls such as `commonSqlExecute`, `queryByStream`,
  `streamGetSn`, and `executeSql` now emit SQL model access endpoints when the
  SQL contains `data.*` FQNs.
- Direct model write/read wrappers such as `batchMergeModel`, `batchInsertModel`,
  `importData`, and `mergeData` remain `DATA_API_CALL`.
- Model migration JSON under `dm/migration` emits `DATA_MODEL_SCHEMA` with
  `use_mode` metadata when visible.
- `event.*` metadata and publish wrappers such as `sendEvents`,
  `Event.of`, and `PublishOptions.of` emit data-event endpoints.
- `data.redis.*` and `spring.data.*` property-like keys are excluded from
  datamodel recognition.
- Literal FQN fallback was narrowed so a stronger DataAPI/SQL/schema context
  does not produce a duplicate unresolved `DATAMODEL`.
- Fixed partial FQN matching around SQL `insert into data.ModelName(...)`.

Validation:

- Added `tests/fixtures/datamodel_modes`.
- `datamodel_modes` fixture verifier: PASS.
- CDP rerun at `D:\kylin_product_repo\CDP\CDP-profile-out`: PASS.

Final CDP kind counts:

- `HTTP_API`: 436
- `HTTP_CALL`: 181
- `DB_TABLE`: 114
- `DATAMODEL`: 62
- `SCHEDULED_JOB`: 42
- `DATA_MODEL_SCHEMA`: 29
- `DATA_MODEL_SQL`: 20
- `ANALYTICS_MODEL_QUERY`: 14
- `DATA_API_CALL`: 9
- `DATA_EVENT_SCHEMA`: 5
- `EVENT_BUS_LISTENER`: 3
- `DATA_EVENT_PUBLISHER`: 3
- `FILE`: 1
