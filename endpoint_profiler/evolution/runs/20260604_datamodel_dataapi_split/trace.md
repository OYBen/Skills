# Trace

1. Added `DATA_API_CALL` and `DATA_API_STREAM` to the endpoint taxonomy,
   schema, verifier, and datamodel rules.
2. Added DataAPI source detection for `DataapiHttpSdk`, `DataapiWebSocketSdk`,
   `DataApiSupport`, `dataapiSdk`, and `dataApiService`.
3. Emitted `DATA_API_CALL` for visible ordinary DataAPI operations such as
   `execute` and `importData`.
4. Emitted `DATA_API_STREAM` only when the current call line uses `fetch` or a
   visible WebSocket client call.
5. Kept unresolved model metadata and plain FQN references as `DATAMODEL` so the
   run can measure whether the concept fully collapses into DataAPI access.

## CDP Validation

```powershell
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\endpoint_profiler.py D:\kylin_product_repo\CDP\CDP --out D:\kylin_product_repo\CDP\CDP-profile-out
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\generate_quality_audits.py D:\kylin_product_repo\CDP\CDP-profile-out --source-root D:\kylin_product_repo\CDP\CDP
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\verify_endpoint_profiler.py D:\kylin_product_repo\CDP\CDP-profile-out
```

Verifier result: PASS.

CDP produced 932 endpoints:

- `DATA_API_CALL`: 8
- `DATA_API_STREAM`: 4
- `DATAMODEL`: 124

Remaining `DATAMODEL` endpoints not paired with a `DATA_API_*` endpoint:

- 112 records
- 85 unique FQNs
- Source kinds: 100 `literal_fqn`, 12 `table_adapter`

Conclusion: `DATAMODEL` cannot yet be fully collapsed into only
`DATA_API_CALL` and `DATA_API_STREAM`. CDP contains model metadata, rule/schema
configuration, event FQNs, table-adapter semantic FQNs, and dynamic model
references that do not expose a concrete DataAPI access mode in the local source
evidence.

