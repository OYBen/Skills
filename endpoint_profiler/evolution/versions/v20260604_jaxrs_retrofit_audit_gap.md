# Version: v20260604_jaxrs_retrofit_audit_gap

## Summary

Endpoint profiler now extracts JAX-RS server APIs and standard Retrofit client
contracts, and the audit can detect source-rule gaps for both families. This
addresses the CDP case where `cdp-mgmt` appeared to have no APIs and only a
single HTTP call.

## Changed

- `scripts/endpoint_profiler.py`
  - Added JAX-RS server route extraction.
  - Added standard Retrofit contract recognition.
  - Filtered non-URL generic HTTP call literals.
  - Fixed Retrofit parameter-path false overrides.
  - Preserved JAX-RS colon action route suffixes.
- `scripts/generate_quality_audits.py`
  - Added JAX-RS server API source-gap checks.
  - Added standard Retrofit HTTP call source-gap checks.
  - Removed block comments before candidate detection.

## Validation

CDP profile output now contains 920 endpoints. `cdp-mgmt` includes HTTP API and
HTTP call inventory, and `verify_endpoint_profiler.py` reports PASS.

## Residual Risk

Dependency-scoped client contracts can be attributed to the owning service when
they are part of the service dependency closure. Consumers should check
`metadata.service_scope` when distinguishing directly-owned APIs from dependency
contracts.

