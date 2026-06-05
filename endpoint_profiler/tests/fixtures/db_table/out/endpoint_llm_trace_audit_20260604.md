# Endpoint Chain Completeness Audit

- Input source root: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\db_table\source`
- Endpoint JSON path: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\db_table\out\endpoints.json`
- Graphify index path: `not available`
- Audit date: 2026-06-04T18:24:43
- Audit Verdict: PASS
- Chain sample count: 2
- Chain traced/internal ratio: 1.00

## Chain Completeness Audit

Random, deterministic 10% per direction/kind endpoint samples are traced to an opposite-direction endpoint. Egress samples trace upstream to ingress; ingress samples trace downstream to egress. Evidence may come from Graphify file edges, direct source references, or explicit same-service semantic flow; unmatched samples must be classified as internal capability or fail.

## Graph Trace Summary

- Graph node count: 0
- Graph edge count: 0

| # | sampled direction | kind | service | sampled endpoint | trace target direction | linked endpoint | trace status | verdict | source | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | egress | DB_TABLE | unassigned | `red_packet_call_back` | ingress | `-` | INTERNAL_CAPABILITY | PASS | src/main/java/com/example/RedPacketCallBack.java:5 | no explicit upstream/downstream opposite endpoint found; treated as endpoint inventory evidence without topology linkage |
| 2 | ingress | HTTP_API | unassigned | `POST /cem/event` | egress | `customer_info` | SEMANTIC_SERVICE_FLOW | PASS | src/main/java/com/example/CemController.java:11 | same-service semantic flow candidate among 4 opposite-direction endpoints; graph/source path not explicit |

## Rule-Gap Candidate Scan

| # | candidate family | source file | verdict | notes |
|---|---|---|---|---|
| 1 | none | none | PASS | no framework-specific missing-family candidates detected |

## Capability-Driven Audit

Dependency/framework capability hints are checked against targeted source/config scans. Candidate-only rows identify a possible missing endpoint family or an unused dependency.

| # | capability | status | potential kinds | targeted scan plan | confirmed kinds | confirmed samples | audit action |
|---|---|---|---|---|---|---|---|
| 1 | MyBatis | confirmed_by_source | DB_TABLE | scan @TableName, mapper interfaces, mapper XML, and table-position SQL; exclude tests, migrations, comments, and unresolved generic table constants | DB_TABLE:3 | META-INF/scripts/tenant/model/20260110160000__create_customer_info.json:1; src/main/java/com/example/RedPacketCallBack.java:5; src/main/java/com/example/UserMapper.java:6 | targeted_scan_confirmed |
| 2 | Spring MVC | confirmed_by_source | HTTP_API | scan controller annotations and class/method mapping combinations; confirm each route with HTTP method and normalized path template | HTTP_API:1 | src/main/java/com/example/CemController.java:11 | targeted_scan_confirmed |

## Rule Gap Discovery

- Chain trace status counts: {'INTERNAL_CAPABILITY': 1, 'PASS': 2, 'SEMANTIC_SERVICE_FLOW': 1}
- Rule-gap candidate verdict counts: {}
- MISSING_ENDPOINT_RULE review: chain rows with FAIL identify sampled endpoints that could not be linked to an opposite-direction endpoint and were not classified as internal capability.

## Findings

- Chain completeness gaps: none in sampled endpoints
- Internal capability classifications: 1
- Upstream/downstream traced samples: 1
