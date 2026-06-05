# DATAMODEL / DATA_API Rules

## Purpose

`DATAMODEL`, `DATA_API_CALL`, `DATA_API_STREAM`, and
`ANALYTICS_MODEL_QUERY` describe semantic data model FQNs exposed
through a data API, data client, model repository, metadata-driven data layer,
or analytical data service. They are logical contracts above physical tables.

Prefer the access-specific kinds when visible evidence shows the data proxy
access mode:

- `DATA_API_CALL`: ordinary DataAPI/data-proxy read or write such as `execute`,
  SQL execute/query, `importData`, or `mergeData` when the call directly names
  or queries the model FQN.
- `DATA_API_STREAM`: DataAPI WebSocket, `fetch`, `queryByStream`, or streaming
  SQL access.
- `ANALYTICS_MODEL_QUERY`: a SQL model access path that is visibly analytical,
  for example `OLAP`, `HTAP`, `olapForce(true)`, bitmap/columnar functions such
  as `bitmap_iterate`, or stream/fetch calls that are paired with analytical
  engine evidence.
- `DATAMODEL`: model metadata or semantic FQN evidence whose concrete access
  mode is not visible.

Model schema creation/update, event schema definitions, migration JSON, and
init JSON are setup evidence, not business endpoints. Do not emit schema
endpoint kinds for them by default. Runtime EventService publish/consume
contracts belong to `EVENT_BUS_PUBLISHER` / `EVENT_BUS_LISTENER`.

## Evidence

- Explicit model FQN strings in the form `data.xxxx.xxxx...`.
- Metadata fields named `fqn`, model FQN, or equivalent semantic model keys.
- Data API or data client calls whose arguments resolve to a full `data.*` FQN;
  these should normally emit `DATA_API_CALL` or `DATA_API_STREAM`.
- SQL strings containing `data.*` FQNs that are passed to DataAPI wrappers,
  calculation job SQL support, or tenant SQL support; these should normally
  emit `DATA_API_CALL` or `DATA_API_STREAM` with `query_language: SQL`, or
  `ANALYTICS_MODEL_QUERY` when analytical engine evidence is visible.
- Runtime `CREATE_MODEL` / `UPDATE_MODEL`, `useMode`, or
  `metaDataApiService.createModel`; keep these as setup/schema evidence unless
  the user explicitly asks for schema inventory.
  Static install/upgrade model migration or init JSON is setup inventory and
  should not emit model schema endpoints by default, although its
  `physicalMeta.tables` can still contribute `DB_TABLE` evidence.
- Metadata API enum-model operations such as `createEnumModel`, `cleanEnumModel`,
  `add`, and config fields such as `enumModelFqn` are schema/setup evidence.
- SQL model FQNs carried through constants, `System.getProperty` /
  `SysEnvUtils.getSysOrEnv` defaults, `DataApiSupport`, `sqlSupport()`, or
  cleanup wrappers such as `doClean`; these should emit `DATA_API_CALL` /
  `DATA_API_STREAM` with SQL evidence, or `ANALYTICS_MODEL_QUERY` when the
  downstream analytical SQL path is visible.
- `event.*` FQNs in event metadata are setup evidence. `event.*` FQNs in
  EventService producer/consumer calls should emit `EVENT_BUS_PUBLISHER` or
  `EVENT_BUS_LISTENER`, not `DATAMODEL`.
- Request/response objects that carry a model FQN and are used in runtime data
  client operations.

## Identifier

- The identifier must be the full model FQN, for example
  `data.prctvmkt.${memberProgramCode}.Guide`.
- If the FQN contains a runtime placeholder, keep the placeholder when it is
  semantically part of the model path.
- Do not replace the FQN with repository, mapper, DTO, or entity names.

## Exclusions

- `*Repository`, `*Mapper`, DAO, ORM entity, and request class names are not
  data model identifiers by naming convention alone.
- DTO/request/response/plain model classes with a model FQN field default are
  not endpoint evidence unless a runtime read/write/schema call uses that FQN.
- `@DataModel` row-mapping annotations are metadata only; do not emit endpoint
  records from the annotation alone.
- Static install/upgrade scripts such as `dm/migration/**`,
  `META-INF/scripts/**/model/**`, and `src/main/resources/json/init*.json`
  should not emit `DATA_MODEL_SCHEMA` unless the user explicitly asks for an
  installation/upgrade model inventory.
- Physical database tables are `DB_TABLE`.
- Configuration keys are not data models. Exclude `spring.data.*`,
  `data.redis.*`, `redis.*`, and similar property names even if a substring
  looks like `data.x.y`.
- Error code strings such as `data.insert.failed` and mock/example model FQNs
  are not endpoint evidence.
