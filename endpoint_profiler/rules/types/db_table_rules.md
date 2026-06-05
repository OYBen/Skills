# DB_TABLE Rules

## Purpose

`DB_TABLE` is an egress endpoint for a physical database table contract used by
production runtime code.

## Evidence

- ORM annotations such as `@TableName`, `@Table`, or equivalent metadata.
- Production mapper interfaces and mapper XML paired by namespace or method.
- SQL annotations or SQL builder calls in production code.
- Graphify nodes that carry table semantics through model metadata, mapper
  methods, or mapper XML paired to production mappers.

## Identifier

- Use the physical table name, for example `member_profile`.
- Preserve visible schema qualification only when it is part of the contract.
- Dynamic table names should keep the stable prefix or named configuration and
  mark uncertainty in `match_rule`.

## Exclusions

- Test SQL, assertions, docs, trace logs, and example strings are out of scope.
- Do not infer a table from DTO, repository, DAO, or entity class names without
  table evidence.
- `data.*` semantic model FQNs are `DATAMODEL`, not `DB_TABLE`.
