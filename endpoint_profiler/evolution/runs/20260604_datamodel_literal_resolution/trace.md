# Trace

Implemented:

- Added multiline Java string FQN binding so constants such as SQL templates can
  be resolved at wrapper call sites.
- Added `DataApiSupport`, `sqlSupport()`, `ThreadLocalSqlSupport`,
  `jobTaskSupport`, `metaDataApiService`, and `MetadataSupport` as data/model
  capability contexts.
- Added schema-call extraction for `createModel`, `createEnumModel`,
  `cleanEnumModel`, `add`, `deleteModel`, and `getModel`.
- Expanded model metadata JSON detection to `dm/migration` and
  `src/main/resources/json/init*.json`.
- Added `enumModelFqn` handling as model schema evidence.
- Classified configurable model defaults and cleanup wrappers such as
  `System.getProperty(..., "data.*")`, `SysEnvUtils.getSysOrEnv(..., "data.*")`,
  and `doClean(..., "data.*")` when they carry target/model FQNs.
- Excluded mock/example/stub fixtures, error-code strings, config-like
  `data.*` keys, plain DTO/model/request/response FQN fields, and `@DataModel`
  annotation-only evidence from fallback `DATAMODEL`.

Validation:

- `datamodel_modes` fixture: PASS.
- `db_table` fixture: PASS.
- `endpoint_taxonomy` fixture: PASS.
- CDP rerun at `D:\kylin_product_repo\CDP\CDP-profile-out`: PASS.

Final CDP kind counts:

- `HTTP_API`: 425
- `HTTP_CALL`: 181
- `DB_TABLE`: 114
- `DATA_MODEL_SCHEMA`: 57
- `SCHEDULED_JOB`: 42
- `DATA_MODEL_SQL`: 26
- `ANALYTICS_MODEL_QUERY`: 14
- `DATA_API_CALL`: 9
- `DATA_EVENT_SCHEMA`: 4
- `EVENT_BUS_LISTENER`: 3
- `DATA_EVENT_PUBLISHER`: 3
- `FILE`: 1
- `DATAMODEL`: 0
