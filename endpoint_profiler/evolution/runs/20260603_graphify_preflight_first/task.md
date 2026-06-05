# Task Contract

- Skill: endpoint_profiler
- Meta workflow: metaSkill
- Objective: make Graphify the mandatory first index for endpoint profiling.
- Requirement: if `graphify-out` / `graph.json` exists, read it before source scanning; if it does not exist, run the `graphify` skill to generate it before endpoint extraction.
- Constraint: if Graphify asks for a narrower scope for a large corpus, pause for user scope selection rather than silently scanning all source.

## Success Criteria

- Endpoint profiler instructions say Graphify is generated before broad source scanning.
- Bundled scanner supports an executable `--ensure-graphify` preflight.
- Existing `graph.json` is parsed for endpoint-looking source candidates and those files are scanned first.
- Fallback source scanning remains available when Graphify is incomplete.
