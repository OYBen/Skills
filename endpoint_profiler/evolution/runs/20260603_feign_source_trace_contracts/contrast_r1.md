# Contrast Analysis R1

## Failure Pattern

- `@SpectrumFeignClient` was not recognized by the Feign detector.
- Spring mapping annotations inside those client interfaces were emitted as ingress `HTTP_API`.
- `HTTP_CALL` count was zero in the MA target output, and the source audit reported missing or unresolved downstream calls.
- Service split generation iterated only over services with endpoint records, omitting zero-endpoint services from `services/manifest.json`.
- Source trace quality counted status names in prose, not only sample rows.

## Success Pattern

- Feign detector now accepts project-specific annotations ending in `FeignClient`.
- Java HTTP client contract scanner now recognizes Spring mapping annotations in Feign interfaces.
- The MA target output now includes 294 `HTTP_CALL` endpoints and fewer ingress `HTTP_API` records.
- Source audit sample rows now have `NEEDS_SOURCE_EXPANSION=0`.
- Remaining problematic rows are explicit `MISSING_ENDPOINT_IN_JSON`, which is an extraction-rule gap rather than untraceable source.
