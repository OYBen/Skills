# Schema Suppressed And EventService Bus Reclassified

## Problem

CDP analysis showed schema endpoints were still visible even though model/event
schema creation is initialization/setup evidence rather than a runtime business
ingress or egress. Shuyun EventService publishes `event.*` contracts through
`EventProducer`, `Event.of`, and `publishBatchSync`, but these were previously
classified as `DATA_EVENT_PUBLISHER`, making the event bus publisher count look
too low.

## Evolution

- Suppress `DATA_MODEL_SCHEMA` and `DATA_EVENT_SCHEMA` from final
  `endpoints.json` output by default.
- Keep schema/migration/init evidence available to the scanner internally, but
  do not expose it as a business endpoint inventory item.
- Reclassify Shuyun EventService publish calls such as `sendEvents(eventFqn,
  ...)`, `Event.of(eventFqn, ...)`, and `publishBatchSync(...)` as
  `EVENT_BUS_PUBLISHER` with `bus: eventservice`.
- Update datamodel and event-bus rules to make EventService runtime
  publish/consume contracts first-class event bus endpoints.
- Update quality audits and regression expectations so schema kinds do not
  reappear in new profiles.

## Validation

- `python -m py_compile scripts/endpoint_profiler.py scripts/verify_endpoint_profiler.py scripts/generate_quality_audits.py`
- `tests/fixtures/datamodel_modes`: PASS
- CDP output: `D:\kylin_product_repo\CDP\CDP-profile-out`
- CDP verifier: PASS

CDP endpoint distribution after this evolution:

```text
HTTP_API 425
HTTP_CALL 181
DB_TABLE 114
SCHEDULED_JOB 42
DATA_API_CALL 28
ANALYTICS_MODEL_QUERY 14
DATA_API_STREAM 6
EVENT_BUS_LISTENER 3
EVENT_BUS_PUBLISHER 3
FILE 1
```

Additional checks:

- `DATA_MODEL_SCHEMA`: 0
- `DATA_EVENT_SCHEMA`: 0
- `DATA_EVENT_PUBLISHER`: 0
- EventService publishers: 3
- Explicit `event.cdp.*` EventService consumers found in CDP source: 0

