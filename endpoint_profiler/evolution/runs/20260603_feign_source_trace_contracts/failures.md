# Failures and Residual Risks

## Resolved

- Feign/SpectrumFeignClient contracts are no longer misclassified as ingress HTTP APIs.
- Source audit sample rows no longer contain `NEEDS_SOURCE_EXPANSION`.
- Zero-endpoint services are represented in service split outputs.
- Dynamic Kafka topic prefix was normalized to a topic template.

## Residual Risks

- `MISSING_ENDPOINT_IN_JSON` remains for visible source chains that reach data/cache operations not yet extracted as endpoints.
- The next focused extractor evolution should cover Java FQN constants and cache invalidation regions.
- Without Graphify, the audit depends on bounded source analysis and cannot prove every dynamic framework edge.
