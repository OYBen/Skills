# Task

Evolve endpoint_profiler after CDP still had 62 fallback `DATAMODEL` endpoints.
Sampling showed these were literal FQN constants, prefixes, DTO annotations,
mock/example data, config keys, error codes, and wrapper calls whose concrete
access mode was not being followed.

Goals:

- Resolve literal FQNs carried through constants and wrapper calls.
- Classify metadata enum/schema operations as `DATA_MODEL_SCHEMA`.
- Classify DataApiSupport/sqlSupport/doClean/default-target model paths as
  `DATA_MODEL_SQL` or `ANALYTICS_MODEL_QUERY`.
- Exclude mock/example data, error codes, config keys, plain DTO/model fields,
  and `@DataModel` row-mapping annotations.
- Drive CDP fallback `DATAMODEL` count to zero without breaking verifier.
