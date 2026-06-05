# Version: v20260603_feign_source_trace_contracts

## Goal

Eliminate source-audit unresolved rows for visible source and fix Feign client endpoint direction.

## Skill Changes

- `scripts/endpoint_profiler.py`
  - Generalized Feign detection from only `@FeignClient` to `@*FeignClient`, including `@SpectrumFeignClient`.
  - Extracts Spring `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`, and `@RequestMapping` inside Java HTTP client contracts as egress `HTTP_CALL`.
  - Normalizes concatenated message topics like `"PREFIX_" + env` to `PREFIX_${env}`.
  - Writes per-service split files and manifest entries for every discovered service, including services with zero endpoint records.
- `scripts/generate_trace_audit.py`
  - Parses interface method declarations with `throws`.
  - Emits `MISSING_ENDPOINT_IN_JSON` when visible endpoint-like calls are found but no endpoint record is reached.
- `scripts/verify_endpoint_profiler.py`
  - Counts trace quality statuses from sample rows only.

## Validation

- Python syntax check: PASS.
- MA target endpoint profiling: PASS.
- Required source and graph-skip audits: PASS.
- Endpoint profiler verifier: PASS.

## Results

- `HTTP_CALL` endpoints increased from 0 to 294.
- Source audit sample rows now have `NEEDS_SOURCE_EXPANSION=0`.
- Remaining source-audit issues are explicit `MISSING_ENDPOINT_IN_JSON` extraction gaps.

## Next Iteration Trigger

Reopen when `MISSING_ENDPOINT_IN_JSON` should become a hard verifier failure, or when Java data/cache extraction is evolved to cover FQN constants, repository generic models, and cache invalidation regions.
