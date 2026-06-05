# Execution Trace

1. Confirmed the target output had no Graphify index; unresolved audit rows were from the source-reading audit.
2. Inspected remaining source audit unresolved rows.
3. Patched `endpoint_profiler.py`:
   - generalized Feign annotation matching to project-specific `*FeignClient` annotations;
   - added Spring mapping extraction in Java HTTP client contracts;
   - normalized concatenated message topics as templates;
   - emitted service splits for every discovered service, including zero-endpoint services.
4. Patched `generate_trace_audit.py`:
   - `throws` clauses in interface declarations are now parsed;
   - visible endpoint-like calls that do not reach an endpoint record become `MISSING_ENDPOINT_IN_JSON`.
5. Patched `verify_endpoint_profiler.py`:
   - source trace quality counts only sample-row statuses.
6. Re-ran the MA target profile, source audit, graph skip audit, and verifier.

## Commands

```powershell
python scripts/endpoint_profiler.py D:/kylin_product_repo/MA/marketing-automation-develop --out D:/kylin_product_repo/MA/marketing-automation-develop-profile-out
python scripts/generate_trace_audit.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out --source-root D:/kylin_product_repo/MA/marketing-automation-develop --graph-skip-if-missing
python scripts/verify_endpoint_profiler.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out
```
