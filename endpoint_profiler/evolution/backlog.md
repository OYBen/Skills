# Endpoint Profiler Backlog

## Candidate Endpoint Families

- `DATA_EVENT_CONSUMER` / `DATA_EVENT_PUBLISHER`
  - Detect `dm.data.event`, `LogicalDataEvent`, `DataEventConsumer`,
    `DefaultDataEventDispatcher`, and event producer SDK usage.
  - Preserve event FQN identifiers such as `event.cdp.TagCustomerChange`.
- `OBJECT_STORAGE`
  - Detect OSS/S3/COS/OBS/Blob/easy-file-storage clients and distinguish them
    from local `FILE` endpoints.
- `KAFKA_PRODUCER` / `KAFKA_CONSUMER`
  - Detect `KafkaProducer`, `ProducerRecord`, listener annotations, topic
    constants, and config-bound topics.
- `DATA_API_CALL` / `DATA_API_STREAM`
  - Detect `dm-dataapi-sdk`, `DataapiHttpSdk`, `DataapiWebSocketSdk`,
    `execute`, `fetch`, `importData`, and `mergeData`.
- `EXTERNAL_SAAS_API`
  - Detect SDK/client boundaries for OneID, customer-merge, EBOSS, marketing,
    BI/newbi, API management, ES/event service, and CBA.
- `SEARCH_INDEX` / `ANALYTICS_STORE`
  - Detect ES/search SDKs, ClickHouse, Doris/StarRocks/Hive/HBase/Trino/Presto,
    and other analytical stores separately from transactional DB tables.
- `DATA_SOURCE`
  - Detect dynamic datasource definitions and runtime datasource management,
    including datasource registry tables, JDBC URLs, driver classes, and pool
    creation.
- `DISTRIBUTED_LOCK`
  - Detect Redisson locks/semaphores separately from Redis cache keys or
    JetCache cache regions.

## Analytical Store Classification

CDP-style projects can depend on both transactional stores and analytical or
columnar stores. Endpoint Profiler should classify DB evidence with store
metadata such as:

- `store_role`: `transactional`, `analytical`, `columnar`, `search`, or
  `dynamic_datasource`.
- `store_engine`: for example `mysql`, `postgresql`, `clickhouse`,
  `ReplacingMergeTree`, `elasticsearch`, or `dataapi`.
- `access_mode`: `jdbc`, `repository`, `dataapi-http`, `dataapi-websocket`,
  `event-stream`, `object-storage`, or `sdk`.

For analytical stores, avoid flattening everything into generic `DB_TABLE`.
Preserve whether a table/model is read for computation, written as a derived
result, or dynamically mapped through tenant/database/space configuration.

## Scope Rule Enforcement Gaps

- **High priority: exclude natural-language design/docs endpoint-looking text
  before emission**
  - Observed on 2026-06-05 while building the siyu-develop microservice
    integration graph from `D:/kylin_product_repo/Kylin导购/siyu-develop-profile-out/endpoints.json`.
  - Symptom: `unknown-service` appeared in the integration graph because
    endpoint-looking strings from natural-language docs were emitted as real
    ingress endpoints without a runtime owner.
  - Concrete false-positive sources:
    - `a提示词与设计/私域系统外部依赖设计文档.md:68`
      emitted `HTTP_API GET /order-management/v1/entp/wechat/api/info/{appId}`.
    - `a提示词与设计/私域系统外部依赖设计文档.md:72`
      emitted `HTTP_API GET /order-management/v1/wechat/sns/oauth2/component/access_token`.
    - `a提示词与设计/私域系统外部依赖设计文档.md:77`
      emitted `HTTP_API GET /order-management/v1/entp/wechat-miniapp/api/sns/component/jscode2session`.
    - `docss/missoion/mission-risk-verification.md:22`
      emitted `MESSAGE_CONSUMER wg.publish.mission.sub.queue`.
    - Additional examples include `DESIGN.md`, `docss/**`, and
      `a提示词与设计/**` producing `XXX`, `XXX_QUEUE`, example HTTP routes,
      and scheduled-job placeholders.
  - Desired rule: natural-language documentation paths must be excluded as
    endpoint evidence by default, including variant names such as `docss/**`,
    `docs*/**`, `design*/**`, `a提示词与设计/**`, `**/*设计文档*.md`, and
    top-level `DESIGN.md`, unless the user explicitly requests design-doc
    contract extraction.
  - Desired implementation: enforce `analysis_scope_rules.md` before graph
    candidate conversion and before fallback pattern scans. Machine-readable
    specs such as OpenAPI, AsyncAPI, protobuf, GraphQL, and explicit contract
    JSON remain allowed.
  - Desired verifier: add a fixture where documentation contains endpoint-like
    HTTP paths, queue names, `XXX_QUEUE`, and cron expressions; expected output
    should exclude them unless the fixture marks the file as machine-readable
    contract evidence.
