# Task

Fix endpoint profiler and audit gaps found during CDP profiling.

## Requirement

The CDP result showed `cdp-mgmt` with no HTTP APIs and only one HTTP call.
Investigation found that the service uses JAX-RS resources and standard
Retrofit contracts that were not fully covered by extraction or source-gap
audit rules.

## Scope

- `scripts/endpoint_profiler.py`
- `scripts/generate_quality_audits.py`

