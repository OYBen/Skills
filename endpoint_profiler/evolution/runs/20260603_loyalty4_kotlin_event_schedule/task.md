# Task

Evolve `endpoint_profiler` using `metaSkill` on a new project target.

Target:

- Source root: `D:/kylin_product_repo/loyalty4`
- Output dir: `D:/kylin_product_repo/loyalty4-profiler-out`
- Graph index: `D:/kylin_product_repo/loyalty4/graphify-out/graph.json`

Resolved metaSkill parameters:

- iterations / R = 3
- strategies / K = 4
- validation_trials / V = 5
- audit_required = true

Contract:

- Run endpoint analysis on the new `loyalty4` project.
- Preserve endpoint JSON as endpoint inventory only.
- Fix reusable extraction failures exposed by the new Kotlin/Java codebase.
- Produce fresh required source and graph audit reports.
- Sync `.agents` and `.codex` skill copies.
