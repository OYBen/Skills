# Trace

1. Confirmed existing endpoint profiler instructions treated Graphify
   large-corpus warnings as a possible reason to skip or pause Graphify.
2. Updated the main skill workflow so explicit full-repository endpoint profiling
   continues through Graphify even after the >200 file warning.
3. Added guidance to use Graphify's chunked subagent workflow for parallel
   semantic extraction when the large-corpus threshold is hit.
4. Updated the graph-index workflow rule so the warning is treated as a
   scheduling/scope audit event rather than an automatic blocker.
5. Updated verifier guidance so a large-corpus warning alone is not an
   acceptable reason to skip Graphify for explicit full-repository profiling.

## Validation

```powershell
rg -n "large corpus|subagent|200 files|2,000,000" C:\Users\apoll\.agents\skills\endpoint_profiler\SKILL.md C:\Users\apoll\.agents\skills\endpoint_profiler\rules\graphify_index_workflow.md C:\Users\apoll\.agents\skills\endpoint_profiler\references\verifier.md
```

