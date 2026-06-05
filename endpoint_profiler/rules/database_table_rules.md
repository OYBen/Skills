# Database Table Endpoint Rules

These rules define how `endpoint_profiler` should extract `DB_TABLE` endpoints from
Graphify output and source code. They are intentionally stricter than generic SQL
literal scanning because source repositories may not contain table definitions or
direct table references in the same module that owns the runtime service.

## Purpose

`DB_TABLE` represents a logical database table contract used by a service. It is
an egress endpoint because the service reads or writes the table through mapper,
DAO, ORM, model metadata, data clients, or generated data access layers.

Do not treat database hosts, schemas, mapper files, migration files, or test SQL
strings as endpoints. The endpoint is the logical table contract.

## Core Graphify Interpretation

Do not expect `graph.json` to contain a literal node whose label or id is the
table name, such as `t_user` or `customer_info`.

In Graphify output, table names are usually not standalone nodes. The useful
nodes are source artifacts that carry table semantics. Extract the carrier node
from `graph.json`, then read the referenced source file and source location to
derive the table endpoint.

This rule is part of the graph-index-first workflow. Start from Graphify
candidate nodes, then confirm by reading source. Do not start with a whole-repo
table-name regex scan when a usable `graph.json` exists.

## Source Node Priority

Use this priority order when selecting Graphify candidate nodes for `DB_TABLE`
endpoints, then confirm each candidate against source content.

1. Model or metadata JSON nodes under paths such as:
   - `META-INF/scripts/**/model/*.json`
   - `META-INF/scripts/**/tenant/**/model/*.json`
   - `META-INF/scripts/**/guidepackage/**/model/*.json`

   These are authoritative table/model definitions when they contain fields such
   as `scriptOperation`, `scriptContent.physicalMeta.tables`, `tableName`, or
   `model.fqn`.

   Extract:
   - `DB_TABLE.identifier` from `physicalMeta.tables.*.tableName`.
   - `DATAMODEL.identifier` from `model.fqn` when present.
   - Dynamic template fragments, such as `{tenantCode_}`, into `match_rule`.

2. Production Mapper Java nodes:
   - `src/main/java/**/*Mapper.java`
   - mapper interface nodes, mapper method nodes, and SQL annotation nodes such
     as `Select`, `Insert`, `Update`, and `Delete`.

   Read the source near `source_file` and `source_location`. Extract table names
   from annotations such as `@Select`, `@Insert`, `@Update`, `@Delete`, and ORM
   table annotations such as `@TableName` or `@Table(name = ...)`.

3. Mapper XML files associated with production Mapper Java nodes.

   Graphify may not include XML resource files as nodes. When a production
   mapper Java node is present, pair it with mapper XML by namespace or filename,
   for example `CustomerInfoMapper.java` -> `resources/mapper/**/CustomerInfoMapper.xml`.
   Parse SQL statements in the XML for `FROM`, `JOIN`, `INSERT INTO`, `UPDATE`,
   `DELETE FROM`, and ORM mapping table attributes.

4. Production DAO, repository, or service code nodes with visible SQL evidence.

   These are lower confidence and must be restricted to production sources. Use
   them only when they show real data access behavior, not assertions, examples,
   logs, or generated traces.

5. Entity or model class nodes.

   Use entity classes only when they contain explicit table metadata or can be
   tied to mapper/model metadata. Naming convention alone is weak evidence and
   should have lower confidence.

## Normalization

Keep `identifier` clean and stable.

Examples:

- Raw table template: `{tenantCode_}customer_info`
- `identifier`: `customer_info`
- `match_rule`:

```json
{
  "type": "table",
  "name": "customer_info",
  "template": "{tenantCode_}customer_info",
  "template_variables": ["tenantCode_"]
}
```

For schema-qualified names, keep the semantic table fingerprint in `identifier`
and put schema or tenant matching in `match_rule`.

Examples:

- Raw SQL: `FROM data_guide.customer_info`
- `identifier`: `customer_info`
- `match_rule.schema`: `data_guide`

## Confidence Guidelines

- `0.95`: metadata/model JSON table definition with `tableName`.
- `0.90`: explicit ORM table annotation in production source.
- `0.85`: Mapper XML or SQL annotation in production mapper source.
- `0.75`: production DAO/service SQL string with clear data-access context.
- `0.60`: entity/model naming convention supported by mapper generic or model
  metadata, but without explicit table name.

Lower the confidence when SQL is dynamic, assembled across methods, or depends on
runtime model names.

## Exclusions

Do not emit `DB_TABLE` endpoints from:

- `src/test/**`
- `*Test.java`
- unit-test assertions such as `Assertions.assertEquals("SELECT ... FROM t_user", ...)`
- fixtures, examples, documentation, trace files, debug logs, or generated audit
  reports
- SQL strings that are expected-output text rather than runtime data access
- XML comment blocks, including commented mapper SQL
- inactive/archive mapper resources such as `src/main/resources/back/**` unless
  explicit runtime evidence proves the mapper is active
- database catalog/system metadata tables such as `information_schema.TABLES`,
  `information_schema.PARTITIONS`, `mysql.*`, or similar facility tables
- unresolved constants such as `TABLE_NAME`; resolve visible Java constants
  first, otherwise skip the candidate
- SQL functions and pseudo-columns such as `CURRENT_TIMESTAMP`, `CURRENT_DATE`,
  or `NOW`
- SQL template variables/placeholders such as `p_table_name`, `#query_model#`,
  or other unresolved model/table placeholders
- mapper XML file paths themselves as `FILE` endpoints
- migration/model JSON file paths themselves as `FILE` endpoints

The same artifact may be a source of table evidence, but the artifact file path
is not the endpoint.

## Expected Endpoint Shape

```json
{
  "direction": "egress",
  "kind": "DB_TABLE",
  "identifier": "customer_info",
  "match_rule": {
    "type": "table",
    "name": "customer_info",
    "template": "{tenantCode_}customer_info",
    "source_kind": "model_metadata"
  },
  "metadata": {
    "confidence": 0.95,
    "evidence": [
      "physicalMeta.tables tableName {tenantCode_}customer_info"
    ]
  }
}
```

## Verifier Expectations

Verifier tests should include both positive and negative cases:

- Positive: model JSON containing `physicalMeta.tables.*.tableName` produces a
  `DB_TABLE` endpoint.
- Positive: production mapper annotation or mapper XML SQL produces a
  `DB_TABLE` endpoint.
- Negative: `src/test/**` SQL literals do not produce `DB_TABLE` endpoints.
- Negative: mapper XML or model JSON file paths do not produce `FILE` endpoints.
- Negative: a table-looking word in docs, logs, or assertion expected strings is
  ignored.
- Negative: SQL functions and placeholders such as `CURRENT_TIMESTAMP`,
  `p_table_name`, and `#query_model#` are ignored.
