# Verifier Result

- Python syntax check: PASS.
- MA target endpoint profiling: PASS.
- Source trace audit generation: PASS.
- Endpoint profiler verifier: PASS.

## Observed MA Output

- Endpoint count: 1255.
- `DATAMODEL`: 73.
- `DB_TABLE`: 126.
- `CACHE_KEY`: 9.
- `data.mc.action.TaskLog`: present as `DATAMODEL`.
- `costCount`: absent as `DB_TABLE`.
- `marketing_target`: present as cache invalidation `CACHE_KEY`.

## Source Audit Row Status

- `TRACE_TO_EGRESS`: 10.
- `TRACE_TO_INGRESS`: 7.
- `MISSING_ENDPOINT_IN_JSON`: 7.
- `NEEDS_SOURCE_EXPANSION`: 0.
