# Graphify Index Workflow

Endpoint Profiler should treat Graphify output as the analysis index whenever it
is available.

The intended flow is:

1. Read `graphify-out/graph.json` as the primary index of source artifacts.
2. Select candidate nodes by endpoint-family rules.
3. Use each candidate node's `source_file`, `source_location`, label, id, and
   graph relationships to locate evidence.
4. Read the referenced source file only for the selected candidate node or its
   local neighborhood.
5. Emit endpoints only when the graph candidate and visible source/config
   evidence agree.

Source scanning is supporting evidence and fallback. It should not be the first
operation when a usable Graphify graph exists.

## Why Graphify Is the Index

Large repositories often contain many files that look endpoint-like but are not
runtime contracts: tests, examples, logs, docs, generated reports, migration
artifacts, and implementation resources. Graphify provides a structured index of
code artifacts, symbols, locations, and relationships, which lets the skill apply
endpoint rules to likely carriers instead of blindly scanning every string.

Graphify is an index, not an oracle. A node is a pointer to evidence. The
endpoint still must be derived from source or config content that can be shown.

## Input Resolution

Accept either:

- a project source root that contains or is near `graphify-out/graph.json`; or
- a Graphify output root that contains `graphify-out/graph.json`.

Search for the graph index in this order:

1. `<input>/graphify-out/graph.json`
2. `<input>/graph.json`
3. sibling or parent paths whose name indicates Graphify output, such as
   `<input>-graphify-out/graphify-out/graph.json`
4. explicit graph path supplied by the user

If no graph index exists, invoke the `$graphify` skill for the input root first
and use the `graphify-out/graph.json` produced by that skill. When Graphify's
detect step reports a large corpus (>200 files or >2,000,000 words), keep the
full input scope for an explicit full-repository endpoint profiling request and
use Graphify's chunked subagent workflow for parallel semantic extraction. Treat
the large-corpus warning as a scheduling/scope audit event, not as a blocker by
itself. Fall back to source scanning only when the user explicitly disables
Graphify, the user does not request full coverage and no narrower scope decision
is available, no subagent/Graphify execution path is available, or skill
execution fails; record the reason in `audit.warnings`.

## Candidate Node Selection

Rules choose candidate nodes before reading broad source content.

Examples:

- HTTP ingress: controller/router files, route annotation nodes, framework route
  symbols, OpenAPI/spec files.
- DB table: model metadata JSON nodes, production Mapper Java nodes, mapper
  method nodes, SQL annotation nodes, associated mapper XML files.
- Message endpoints: listener/producer annotations, consumer classes, topic
  config files.
- Scheduled jobs: scheduler annotation nodes, job bootstrap classes, cron config.
- File integration: OSS/S3/SFTP/shared-directory integration classes and batch
  import/export jobs, not arbitrary file names.

## Source Confirmation

For each selected node:

- Read only the referenced `source_file`, nearby lines around
  `source_location`, and directly associated files required by the rule.
- Normalize endpoint identifiers from source evidence.
- Put fuzzy or dynamic matching in `match_rule`.
- Preserve the graph node as provenance when possible.

Suggested provenance fields in `metadata`:

```json
{
  "graphify_node_id": "optional graph node id",
  "graphify_node_label": "optional graph node label",
  "source_kind": "mapper_java"
}
```

## Fallback Source Scan

Use broad source scanning only when:

- Graphify output is missing or unreadable.
- A rule explicitly requires source files that Graphify did not index, such as a
  mapper XML paired from a Mapper Java node.
- The candidate node points to generated metadata that needs source expansion.

Fallback results should generally have lower confidence than graph-indexed
results unless the source evidence is authoritative.

## Audit Requirements

When Graphify is used, include audit evidence such as:

- `audit.graphify_used = true`
- `audit.graphify_index_path`
- `audit.scan_modes` including `graphify-index`
- warnings for unreadable graph files or fallback-only endpoint families
