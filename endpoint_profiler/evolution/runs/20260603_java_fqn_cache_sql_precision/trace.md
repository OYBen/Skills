# Execution Trace

1. Loaded metaSkill instructions.
2. Inspected existing endpoint profiler rules and MA source audit `MISSING_ENDPOINT_IN_JSON` rows.
3. Patched `scripts/endpoint_profiler.py`:
   - added `JAVA_FQN_CONSTANT_ACCESS_RE`;
   - added `CACHE_INVALIDATE_RE`;
   - tightened SQL table regex and table identifier validation;
   - emitted datamodel endpoints from resolved Java `*.FQN` constants;
   - emitted cache-region endpoints from `invalidateAll()` receivers.
4. Patched `scripts/verify_endpoint_profiler.py`:
   - rejects `DB_TABLE` from `UPDATE <field> = ...` evidence;
   - adds regression checks for `@SpectrumFeignClient` HTTP calls and `TaskLog.FQN`.
5. Updated `SKILL.md` rules for datamodel FQN constants, SQL field assignments, and cache invalidation.
6. Re-ran MA profile, source audit, and verifier.

## Commands

```powershell
python -m py_compile scripts/endpoint_profiler.py scripts/generate_trace_audit.py scripts/verify_endpoint_profiler.py
python scripts/endpoint_profiler.py D:/kylin_product_repo/MA/marketing-automation-develop --out D:/kylin_product_repo/MA/marketing-automation-develop-profile-out
python scripts/generate_trace_audit.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out --source-root D:/kylin_product_repo/MA/marketing-automation-develop --graph-skip-if-missing
python scripts/verify_endpoint_profiler.py D:/kylin_product_repo/MA/marketing-automation-develop-profile-out
```
