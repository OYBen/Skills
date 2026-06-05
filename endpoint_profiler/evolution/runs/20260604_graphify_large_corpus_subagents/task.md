# Task

Optimize endpoint profiler behavior when the required `/graphify` preflight
detects a large corpus.

## Requirement

When Graphify reports more than 200 files during endpoint profiling, an explicit
full-repository profiling request should not stop automatically for subfolder
selection. The profiler workflow may use Graphify's chunked subagent extraction
path to process the large corpus in parallel and continue to endpoint extraction.

## Scope

- `SKILL.md`
- `rules/graphify_index_workflow.md`
- `references/verifier.md`

