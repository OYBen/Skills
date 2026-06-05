# Version: v20260603_java_fqn_cache_sql_precision

## Goal

Resolve the previous endpoint profiler TODOs for Java datamodel constants, SQL table precision, and cache invalidation egress contracts.

## Skill Changes

- `scripts/endpoint_profiler.py`
  - Extracts `DATAMODEL` from resolved Java `Class.FQN` constants whose value is a `data.*` FQN.
  - Rejects lower-camel SQL field assignments as `DB_TABLE` endpoints.
  - Extracts cache-region `CACHE_KEY` endpoints from `receiverCache.invalidateAll()`.
- `scripts/verify_endpoint_profiler.py`
  - Adds a regression guard against `UPDATE <field> = ...` table false positives.
  - Adds visible-source regression checks for `@SpectrumFeignClient` HTTP calls and `TaskLog.FQN` datamodel extraction.
- `SKILL.md`
  - Documents Java `*.FQN` datamodel evidence.
  - Documents SQL field assignment exclusions.
  - Documents cache invalidation region extraction.

## Validation

- Syntax check: PASS.
- MA target profile generation: PASS.
- Required source audit generation: PASS.
- Endpoint profiler verifier: PASS.

## Results

- MA endpoint count: 1255.
- `DATAMODEL` count increased to 73.
- `CACHE_KEY` count increased to 9.
- `DB_TABLE` count reduced to 126 after removing field false positives.
- `NEEDS_SOURCE_EXPANSION` sample rows remain 0.

## Next Iteration Trigger

Reopen for remaining `MISSING_ENDPOINT_IN_JSON` rows, especially deeper service/repository traces not yet matched to emitted egress endpoints.
