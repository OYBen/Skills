# Task

Split explicit DataAPI datamodel access into access-specific endpoint kinds.

## Requirement

CDP datamodel FQNs represent data-proxy model contracts. Try classifying
visible DataAPI access as two endpoint kinds while preserving the datamodel FQN
as the identifier:

- `DATA_API_CALL`
- `DATA_API_STREAM`

Then determine whether remaining `DATAMODEL` endpoints can fully collapse into
those two kinds.

## Scope

- `scripts/endpoint_profiler.py`
- `scripts/generate_quality_audits.py`
- `scripts/verify_endpoint_profiler.py`
- `references/output-schema.json`
- `SKILL.md`
- `rules/types/datamodel_rules.md`

