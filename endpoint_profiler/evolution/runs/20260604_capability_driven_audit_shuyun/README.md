# 2026-06-04 Capability-Driven Audit and Shuyun Dependencies

## Trigger

CDP analysis showed dependency/framework capabilities were detected, but capability
hints did not visibly drive endpoint analysis or audit. Kafka existed in the
toolchain preflight while Kafka producer/consumer contracts were underreported
until dedicated rules were added. Shuyun EventService and DataAPI are business
dependency packages and should also seed targeted endpoint scans.

## Changes

- Allowed stable SaaS dynamic templates in `identifier`, such as
  `calc.service.scheduler.jobEvent.topic.{tenantId}.{group}`, while keeping raw
  expressions and fuzzy behavior in `match_rule`.
- Added per-capability scan plans, audit actions, `scan_plan_executed`, confirmed
  endpoint samples, and candidate-only rule-gap warnings.
- Expanded Kafka capability clues to include `KafkaConsumer`, `KafkaProducer`,
  `ProducerRecord`, and `consumer.subscribe`.
- Added Shuyun EventService capability clues for `com.shuyun.air.es`,
  `EventProducer`, `PublishOptions`, `Event.of`, `publishBatchSync`, and project
  `sendEvents` wrappers.
- Added Shuyun DataAPI capability clues for `DataapiHttpSdk`,
  `DataapiWebSocketSdk`, `DataapiSdkFactory`, `DataApiService`, `DataApiSupport`,
  `commonSqlExecute`, and `queryByStream`.
- Added a `Capability-Driven Audit` section to generated quality reports.
- Updated verifier regressions so capability hints must include scan plans and
  confirmed hints must include endpoint samples.

## CDP Validation

- Endpoint count: 819.
- Kafka capability: `confirmed_by_source`, with `MESSAGE_PRODUCER:1` and
  `MESSAGE_CONSUMER:1`.
- Shuyun DataAPI capability: `confirmed_by_source`, with `DATA_API_CALL:28`,
  `DATA_API_STREAM:6`, and `ANALYTICS_MODEL_QUERY:14`.
- Shuyun EventService capability: `confirmed_by_source`, with
  `EVENT_BUS_PUBLISHER:3`.
- Candidate-only warnings are now emitted for detected capabilities without
  confirmed contracts, for example OkHttp and Redis/Redisson in CDP.

## Verification

- `python -m py_compile` passed for profiler, audit generator, and verifier.
- Fixture scans and verifier passed for `datamodel_modes`, `endpoint_taxonomy`,
  and `db_table`.
- CDP scan, quality audit generation, and verifier passed.
