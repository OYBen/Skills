# Task Contract

- Skill: endpoint_profiler
- Meta workflow: metaSkill
- Objective: continue reducing untraceable audit samples and answer whether the unresolved audit rows came from graph.json or source analysis.
- Finding: the target project had no `graphify-out/graph.json`; the unresolved rows came from source-reading audit output. The graph audit was a documented skip report.
- Iterations: 1 focused patch.
- Strategies K: 4.
- Validation trials V: 5.
- Audit required: true.

## Success Criteria

- Source audit sample rows should have no blanket `NEEDS_SOURCE_EXPANSION` when source is visible.
- Feign-like client contracts should be emitted as egress `HTTP_CALL`, not ingress `HTTP_API`.
- Service split outputs must include services with zero endpoints.
- Dynamic message topic templates should not be unresolved Java constant prefixes.
