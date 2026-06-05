# Data Model Endpoint Rules

These rules define when to emit semantic data-model and data-event endpoints.

## Purpose

`DATAMODEL` is a semantic data contract above physical tables. In this codebase,
it represents a logical model operated through data APIs, data clients, openapi
FQN resolution, or model metadata. Prefer more specific endpoint kinds whenever
the access mode is visible:

- `DATA_API_CALL` for direct DataAPI ordinary model calls.
- `DATA_API_STREAM` for DataAPI fetch/WebSocket/streaming model calls.
- `ANALYTICS_MODEL_QUERY` for OLAP/HTAP/bitmap/streaming SQL model access.

`DATAMODEL` remains the fallback for semantic model FQN evidence whose access
mode is unresolved. It is not the same as an ORM entity class, repository class,
mapper class, DAO class, physical table, or runtime configuration property.
Model/event schema creation, migration, and init files are setup evidence rather
than business ingress/egress endpoints. Runtime event publish/consume contracts
belong to `EVENT_BUS_PUBLISHER` / `EVENT_BUS_LISTENER`.

## Positive Evidence

Emit `DATAMODEL` only when visible evidence shows one of these patterns:

- Runtime model metadata calls or non-static machine-readable schema contracts
  with `scriptContent.model.fqn`; keep these as schema/setup evidence unless
  the user explicitly asks for schema inventory.
- Explicit model FQN resolution, such as
  `FetchCacheService.fetchOpenapiFqn(... ModelNameEnum.ORDER.name())`.
  Resolve `ModelNameEnum.ORDER` through `ModelNameEnum`'s template and emit the
  FQN, for example `data.prctvmkt.${memberProgramCode}.Order`.
- Explicit data abstraction API usage, such as `DataModel<T>`,
  `DataClient<T>`, `DataApi<T>`, or project-specific data API clients that
  operate semantic models rather than tables. If no FQN can be recovered, keep
  it as candidate evidence and do not emit a `DATAMODEL` endpoint.
- Machine-readable model contract files whose fields define a logical model
  namespace, FQN, or semantic data object.
- SQL strings or table-adapter declarations containing `data.*` model FQNs;
  emit `DATA_API_CALL` or `DATA_API_STREAM` with `query_language: SQL`, or
  `ANALYTICS_MODEL_QUERY` when analytics/OLAP/columnar evidence is visible.
- `event.*` metadata is setup evidence. EventService producer/consumer calls
  should emit `EVENT_BUS_PUBLISHER` / `EVENT_BUS_LISTENER`, not `DATAMODEL`.
- Metadata enum-model operations and `enumModelFqn` config fields are schema
  evidence, not business endpoints.
- Model FQNs passed through constants, `System.getProperty` /
  `SysEnvUtils.getSysOrEnv`, `DataApiSupport`, `sqlSupport()`, or cleanup
  wrappers; emit `DATA_API_CALL` / `DATA_API_STREAM` with SQL evidence, or
  `ANALYTICS_MODEL_QUERY` when the runtime analytical SQL/data path is visible.
- Static install/upgrade model inventory, including `dm/migration/**`,
  `META-INF/scripts/**/model/**`, and `src/main/resources/json/init*.json`, is
  setup evidence rather than a business endpoint. Do not emit
  `DATA_MODEL_SCHEMA` or fallback `DATAMODEL` from these files by default.
  Continue to use their `physicalMeta.tables` sections as `DB_TABLE` evidence
  when present.

## Negative Evidence

Do not emit `DATAMODEL` solely because of:

- `*Repository` class names.
- `*Mapper` class names.
- `*Dao` class names.
- ORM entity classes.
- `@TableName` annotations.
- MyBatis XML files.
- Generic service/helper class names.
- Configuration keys such as `spring.data.redis.ssl.enabled`,
  `data.redis.ssl.enabled`, or `redis.ssl`.
- Error codes such as `data.insert.failed`.
- Mock/example/demo model FQNs.
- Plain DTO/request/response/model fields and `@DataModel` row-mapping
  annotations unless a runtime endpoint operation uses the FQN.

These may provide `DB_TABLE` evidence, SDK/client evidence, or internal
implementation evidence, but they are not semantic data model endpoints by
themselves.

## FQN Identifier Format

For model metadata contracts, keep the full semantic FQN as the `identifier`.
Do not collapse it to the Java class name or terminal model name.

Correct:

```text
DATAMODEL data.prctvmkt.${memberProgramCode}.Guide
DATAMODEL data.prctvmkt.${memberProgramCode}.GuideDepartmentRelation
```

Incorrect:

```text
DATAMODEL Guide
DATAMODEL ORDER
DATAMODEL PRODUCT
DATAMODEL GuideRepository
DATAMODEL GuideMapper
```

## RedPacketCallBack Example

`RedPacketCallBackRepository` is a Spring repository/DAO wrapper:

```java
@Repository
public class RedPacketCallBackRepository {
    private final RedPacketCallBackMapper mapper;
    public Long save(RedPacketCallBack entity) {
        mapper.insert(entity);
        return entity.getId();
    }
}
```

`RedPacketCallBack` is an ORM entity:

```java
@TableName("red_packet_call_back")
public class RedPacketCallBack { ... }
```

The correct endpoint evidence here is `DB_TABLE red_packet_call_back`, not
`DATAMODEL RedPacketCallBack`.

## Confidence Guidelines

- `0.90`: model metadata JSON with explicit `model.fqn`.
- `0.76`: explicit `FetchCacheService.fetchOpenapiFqn` model enum resolution.
- `0.70`: explicit `DataModel<T>`, `DataClient<T>`, or `DataApi<T>` generic
  usage with semantic model evidence.
- Do not emit a low-confidence `DATAMODEL` for repository/mapper/entity naming
  conventions alone.
