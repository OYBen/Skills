# Endpoint Chain Completeness Audit

- Input source root: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\endpoint_taxonomy\source`
- Endpoint JSON path: `C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\endpoint_taxonomy\out\endpoints.json`
- Graphify index path: `not available`
- Audit date: 2026-06-04T18:24:43
- Audit Verdict: PASS
- Chain sample count: 6
- Chain traced/internal ratio: 1.00

## Chain Completeness Audit

Random, deterministic 10% per direction/kind endpoint samples are traced to an opposite-direction endpoint. Egress samples trace upstream to ingress; ingress samples trace downstream to egress. Evidence may come from Graphify file edges, direct source references, or explicit same-service semantic flow; unmatched samples must be classified as internal capability or fail.

## Graph Trace Summary

- Graph node count: 0
- Graph edge count: 0

| # | sampled direction | kind | service | sampled endpoint | trace target direction | linked endpoint | trace status | verdict | source | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | egress | EVENT_BUS_PUBLISHER | unassigned | `OrderChangedEvent` | ingress | `RefreshReportJob` | TRACE_TO_INGRESS | PASS | src/main/java/com/example/EndpointTaxonomySamples.java:47 | graph/source-file reachability: com/example/endpointtaxonomysamples.java -> com/example/endpointtaxonomysamples.java |
| 2 | egress | HTTP_CALL | unassigned | `POST /data/query/occIds` | ingress | `OrderChangedEvent` | SEMANTIC_SERVICE_FLOW | PASS | src/main/java/com/example/CdpDataService.java:11 | same-service semantic flow candidate among 3 opposite-direction endpoints; graph/source path not explicit |
| 3 | egress | MESSAGE_PRODUCER | unassigned | `orders.sync.key` | ingress | `RefreshReportJob` | TRACE_TO_INGRESS | PASS | src/main/java/com/example/EndpointTaxonomySamples.java:30 | graph/source-file reachability: com/example/endpointtaxonomysamples.java -> com/example/endpointtaxonomysamples.java |
| 4 | ingress | EVENT_BUS_LISTENER | unassigned | `OrderChangedEvent` | egress | `OrderChangedEvent` | TRACE_TO_EGRESS | PASS | src/main/java/com/example/EndpointTaxonomySamples.java:10 | graph/source-file reachability: com/example/endpointtaxonomysamples.java -> com/example/endpointtaxonomysamples.java |
| 5 | ingress | MESSAGE_CONSUMER | unassigned | `orders.created` | egress | `OrderChangedEvent` | TRACE_TO_EGRESS | PASS | src/main/java/com/example/EndpointTaxonomySamples.java:13 | graph/source-file reachability: com/example/endpointtaxonomysamples.java -> com/example/endpointtaxonomysamples.java |
| 6 | ingress | SCHEDULED_JOB | unassigned | `RefreshReportJob` | egress | `OrderChangedEvent` | TRACE_TO_EGRESS | PASS | src/main/java/com/example/EndpointTaxonomySamples.java:33 | graph/source-file reachability: com/example/endpointtaxonomysamples.java -> com/example/endpointtaxonomysamples.java |

## Rule-Gap Candidate Scan

| # | candidate family | source file | verdict | notes |
|---|---|---|---|---|
| 1 | none | none | PASS | no framework-specific missing-family candidates detected |

## Capability-Driven Audit

Dependency/framework capability hints are checked against targeted source/config scans. Candidate-only rows identify a possible missing endpoint family or an unused dependency.

| # | capability | status | potential kinds | targeted scan plan | confirmed kinds | confirmed samples | audit action |
|---|---|---|---|---|---|---|---|
| 1 | OkHttp | confirmed_by_source | HTTP_CALL | scan source/config features that can confirm HTTP_CALL; emit endpoints only after a concrete runtime contract identifier is visible or template-resolvable | HTTP_CALL:4 | src/main/java/com/example/CdpDataService.java:11; src/main/java/com/example/ConfigBaseUrlClient.java:9; src/main/java/com/example/ConfigBaseUrlClient.java:14 | targeted_scan_confirmed |
| 2 | OpenAPI | candidate_only | HTTP_API, HTTP_CALL | scan source/config features that can confirm HTTP_API, HTTP_CALL; emit endpoints only after a concrete runtime contract identifier is visible or template-resolvable | - | - | targeted_scan_no_confirming_contract |
| 3 | RabbitMQ | confirmed_by_source | MESSAGE_CONSUMER, MESSAGE_PRODUCER | scan @RabbitListener, RabbitTemplate.convertAndSend, and project producer annotations; resolve queue, exchange, and routing key constants before endpoint emission | MESSAGE_CONSUMER:1, MESSAGE_PRODUCER:2 | src/main/java/com/example/EndpointTaxonomySamples.java:13; src/main/java/com/example/EndpointTaxonomySamples.java:21; src/main/java/com/example/EndpointTaxonomySamples.java:30 | targeted_scan_confirmed |
| 4 | Retrofit | confirmed_by_source | HTTP_CALL | scan source/config features that can confirm HTTP_CALL; emit endpoints only after a concrete runtime contract identifier is visible or template-resolvable | HTTP_CALL:1 | src/main/java/com/example/BossFeignClient.java:9 | targeted_scan_confirmed |
| 5 | Spring MVC | candidate_only | HTTP_API | scan controller annotations and class/method mapping combinations; confirm each route with HTTP method and normalized path template | - | - | targeted_scan_no_confirming_contract |
| 6 | Spring OpenFeign | confirmed_by_source | HTTP_CALL | scan @FeignClient interfaces and inherited mapping annotations; classify client mappings as HTTP_CALL rather than HTTP_API | HTTP_CALL:1 | src/main/java/com/example/BossFeignClient.java:9 | targeted_scan_confirmed |
| 7 | XXL-Job | confirmed_by_source | SCHEDULED_JOB | scan @XxlJob declarations and scheduler metadata; emit scheduled entry contracts with executeClass/job handler identifiers | SCHEDULED_JOB:1 | src/main/java/com/example/EndpointTaxonomySamples.java:33 | targeted_scan_confirmed |

## Rule Gap Discovery

- Chain trace status counts: {'TRACE_TO_INGRESS': 2, 'PASS': 6, 'SEMANTIC_SERVICE_FLOW': 1, 'TRACE_TO_EGRESS': 3}
- Rule-gap candidate verdict counts: {}
- MISSING_ENDPOINT_RULE review: chain rows with FAIL identify sampled endpoints that could not be linked to an opposite-direction endpoint and were not classified as internal capability.

## Findings

- Chain completeness gaps: none in sampled endpoints
- Internal capability classifications: 0
- Upstream/downstream traced samples: 6
