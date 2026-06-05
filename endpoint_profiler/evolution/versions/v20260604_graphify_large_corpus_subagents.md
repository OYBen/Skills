# Version: v20260604_graphify_large_corpus_subagents

## Summary

Endpoint profiler now documents a large-corpus Graphify path for explicit
full-repository profiling requests. When Graphify detects more than 200 files or
more than 2,000,000 words, the workflow should continue with the full corpus and
use Graphify's chunked subagent extraction path instead of treating the warning
as an automatic blocker.

## Changed

- `SKILL.md`
  - Replaced the previous "skip when corpus is too large" condition with a
    full-repository continuation rule.
  - Added explicit subagent-parallel Graphify guidance.
- `rules/graphify_index_workflow.md`
  - Clarified large-corpus handling and fallback conditions.
- `references/verifier.md`
  - Updated verification expectations so large corpus alone does not justify a
    Graphify skip for full-repository endpoint profiling.

## Residual Risk

Actual subagent availability is platform-dependent. If no subagent or Graphify
execution path is available, the run must record that reason in
`audit.warnings` and fall back to source scanning.

