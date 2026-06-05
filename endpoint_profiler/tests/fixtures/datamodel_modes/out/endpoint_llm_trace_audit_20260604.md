# Endpoint Chain Completeness Audit

- Input source root: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\datamodel_modes\source`
- Endpoint JSON path: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\datamodel_modes\out\endpoints.json`
- Graphify index path: `not available`
- Audit date: 2026-06-04T18:24:43
- Audit Verdict: PASS
- Chain sample count: 4
- Chain traced/internal ratio: 1.00

## Chain Completeness Audit

Random, deterministic 10% per direction/kind endpoint samples are traced to an opposite-direction endpoint. Egress samples trace upstream to ingress; ingress samples trace downstream to egress. Evidence may come from Graphify file edges, direct source references, or explicit same-service semantic flow; unmatched samples must be classified as internal capability or fail.

## Graph Trace Summary

- Graph node count: 0
- Graph edge count: 0

| # | sampled direction | kind | service | sampled endpoint | trace target direction | linked endpoint | trace status | verdict | source | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | egress | ANALYTICS_MODEL_QUERY | unassigned | `data.cdp.calc.SegmentTaskTarget` | ingress | `-` | INTERNAL_CAPABILITY | PASS | src/main/java/com/example/CdpModelAccess.java:14 | no ingress endpoint inventory for service unassigned; endpoint source is still sampled for inventory evidence |
| 2 | egress | DATA_API_CALL | unassigned | `data.mdm.TagCategory` | ingress | `-` | INTERNAL_CAPABILITY | PASS | src/main/java/com/example/CdpModelAccess.java:19 | no ingress endpoint inventory for service unassigned; endpoint source is still sampled for inventory evidence |
| 3 | egress | DATA_API_STREAM | unassigned | `data.cdp.calc.SegmentTaskTarget` | ingress | `-` | INTERNAL_CAPABILITY | PASS | src/main/java/com/example/CdpModelAccess.java:15 | no ingress endpoint inventory for service unassigned; endpoint source is still sampled for inventory evidence |
| 4 | egress | EVENT_BUS_PUBLISHER | unassigned | `event.cdp.ImportExportNotify` | ingress | `-` | INTERNAL_CAPABILITY | PASS | src/main/java/com/example/CdpModelAccess.java:23 | no ingress endpoint inventory for service unassigned; endpoint source is still sampled for inventory evidence |

## Rule-Gap Candidate Scan

| # | candidate family | source file | verdict | notes |
|---|---|---|---|---|
| 1 | none | none | PASS | no framework-specific missing-family candidates detected |

## Capability-Driven Audit

Dependency/framework capability hints are checked against targeted source/config scans. Candidate-only rows identify a possible missing endpoint family or an unused dependency.

| # | capability | status | potential kinds | targeted scan plan | confirmed kinds | confirmed samples | audit action |
|---|---|---|---|---|---|---|---|
| 1 | Redis/Redisson | candidate_only | DISTRIBUTED_CACHE | scan RedisTemplate/StringRedisTemplate operations, Redisson locks, and distributed cache enums; confirm a stable distributed key namespace or prefix before emitting DISTRIBUTED_CACHE | - | - | targeted_scan_no_confirming_contract |
| 2 | Shuyun DataAPI | confirmed_by_source | DATA_API_CALL, DATA_API_STREAM, ANALYTICS_MODEL_QUERY | scan DataapiHttpSdk, DataapiWebSocketSdk, DataapiSdkFactory, DataApiService, and SQL/query wrapper calls; resolve data.* model FQNs and classify ordinary calls as DATA_API_CALL, streaming/fetch paths as DATA_API_STREAM, and OLAP/columnar paths as ANALYTICS_MODEL_QUERY | DATA_API_CALL:2, ANALYTICS_MODEL_QUERY:1, DATA_API_STREAM:1 | src/main/java/com/example/CdpModelAccess.java:10; src/main/java/com/example/CdpModelAccess.java:14; src/main/java/com/example/CdpModelAccess.java:15 | targeted_scan_confirmed |
| 3 | Shuyun EventService | confirmed_by_source | EVENT_BUS_PUBLISHER, EVENT_BUS_LISTENER | scan com.shuyun.air.es/EventService wrappers, Event.of, EventProducer, PublishOptions, and publish calls; resolve event FQN constants/templates into EVENT_BUS_PUBLISHER or EVENT_BUS_LISTENER contracts | EVENT_BUS_PUBLISHER:1 | src/main/java/com/example/CdpModelAccess.java:23 | targeted_scan_confirmed |

## Rule Gap Discovery

- Chain trace status counts: {'INTERNAL_CAPABILITY': 4, 'PASS': 4}
- Rule-gap candidate verdict counts: {}
- MISSING_ENDPOINT_RULE review: chain rows with FAIL identify sampled endpoints that could not be linked to an opposite-direction endpoint and were not classified as internal capability.

## Findings

- Chain completeness gaps: none in sampled endpoints
- Internal capability classifications: 4
- Upstream/downstream traced samples: 0
