# Task Contract

- Skill: endpoint_profiler
- Meta workflow: metaSkill
- Objective: evolve endpoint extraction using previous audit TODOs.
- Inputs: previous MA profiling output and source audit rows with `MISSING_ENDPOINT_IN_JSON`.
- Focused targets:
  - Java `*.FQN` datamodel constants.
  - SQL field names misclassified as `DB_TABLE`.
  - Cache invalidation calls lacking `CACHE_KEY` records.

## Control Parameters

- Iterations: 1 focused patch.
- Strategies K: 4.
- Validation trials V: 5.
- Audit required: true.

## Success Criteria

- Visible Java `Class.FQN` constants resolving to `data.*` emit `DATAMODEL`.
- Lower-camel SQL field assignments such as `UPDATE costCount = ...` do not emit `DB_TABLE`.
- `receiverCache.invalidateAll()` emits a cache-region `CACHE_KEY`.
- Full verifier passes on the MA target output.
