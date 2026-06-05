---
name: endpoint_profiler
description: >-
  Use this skill to statically analyze source code and extract ingress and egress endpoint contracts for microservices. It scans code, graphify outputs, and configuration files to produce clean Endpoints JSON puzzle pieces, not service topology edges. It is for endpoint profiling, AST-level and pattern-assisted static analysis, endpoint metadata extraction, identifier normalization, and contract taxonomy classification.
trigger: /endpoint_profiler
---

# Endpoint Profiler

Use this skill to extract endpoint contracts from a software system. The output is a clean endpoint inventory for downstream graph engines; do not perform auto-wiring, dependency edge drawing, or topology inference beyond endpoint classification.

## Available Companion Skills

- `$graphify`: use this skill to create or refresh the source graph index before endpoint extraction. Invoke Graphify through the skill workflow, not through the endpoint profiler's wrapper script, when an index is missing or stale.

## Core Philosophy

- **Nodes are contracts, not facilities.** An endpoint represents a logical contract or semantic channel, not a database host, Kafka cluster, server name, or deployment unit.
- **Fingerprint and rule are separate.** `identifier` is a clean contract fingerprint. Prefer static values, but configurable SaaS systems often build runtime contract names from stable templates. Keep stable dynamic templates such as `topic.{tenantId}.{group}` or `data.cdp.{domain}.Tag` in `identifier`; put wildcard/fuzzy behavior, raw expressions, query parameters, and variable provenance in `match_rule`.
- **Endpoint JSON is a puzzle piece.** Produce ingress and egress endpoint records that another graph engine can join later.

## Endpoint Taxonomy

Ingress endpoint kinds:

- `HTTP_API`
- `RPC_ROUTE`
- `WebSocket`
- `MESSAGE_CONSUMER`
- `EVENT_BUS_LISTENER`
- `SCHEDULED_JOB`
- `CLI`

Egress endpoint kinds:

- `HTTP_CALL`
- `RPC_CALL`
- `DB_TABLE`
- `DISTRIBUTED_CACHE`
- `MESSAGE_PRODUCER`
- `EVENT_BUS_PUBLISHER`
- `DATAMODEL`
- `DATA_API_CALL`
- `DATA_API_STREAM`
- `ANALYTICS_MODEL_QUERY`
- `SDK`
- `FILE`

Normalize aliases in user text: `DB table` -> `DB_TABLE`, `Redis key` and
`distributed cache` -> `DISTRIBUTED_CACHE`. In-memory cache keys are not
endpoint contracts.

For kind-specific extraction boundaries, identifier policy, evidence, and
exclusions, use the per-kind rule files under `rules/types/`. These files are
the first place to update when one endpoint kind needs a new reusable rule.

## Data Priority

Use Graphify as the primary index. The normal flow is:
`graph.json` candidate node -> endpoint-family rule -> focused source/config
confirmation -> normalized endpoint JSON. Source scanning is supporting evidence
and fallback, not the first pass. If a project does not already have a usable
`graphify-out/graph.json`, invoke the `$graphify` skill first to generate one,
then run endpoint profiling against that graph index. If Graphify detects a
large corpus (>200 files or >2,000,000 words), do not treat that warning as a
hard stop for an explicit full-repository endpoint profiling request. Continue
through the `$graphify` skill's parallel semantic extraction workflow by using
subagents for the file chunks it defines, then run endpoint profiling against
the produced graph. Only skip Graphify generation when the user explicitly
disables it, the user declines full-corpus processing after the warning, no
subagent/Graphify execution path is available, or graphify installation/execution
fails; record the reason in `audit.warnings`.

Before endpoint emission, run a framework/dependency capability preflight. Treat
scaffolds, framework starters, annotations packages, and dependency packages as
candidate clues for possible ingress/egress families, not as endpoint evidence
by themselves. A capability such as Spring MVC, OpenFeign, Spring Cloud Stream,
Kafka, Redisson, MyBatis, JPA, XXL-Job, Shuyun EventService, or Shuyun DataAPI
should guide which source patterns to inspect. Each capability hint must carry
a scan plan, confirming features, evidence, confirmed endpoint samples, and a
candidate-only warning if no endpoint was confirmed. Emit endpoints only when
matching source/config usage confirms a concrete contract such as a route,
client call, topic, Redis key, scheduler, table, event, or data model access.
Record unconfirmed capabilities as audit hints, not endpoints.

1. **Graphify index**: locate `graphify-out/graph.json`; if it is absent, run the `$graphify` skill on `<input_dir>` to completion before broad source scanning. When Graphify's detect step reports more than 200 files or more than 2,000,000 words, keep the full input scope if the endpoint profiling request names the whole repository or otherwise asks for full coverage, and use Graphify's chunked subagent workflow to process the corpus in parallel. Use the graph file produced by that skill, normally `<input_dir>/graphify-out/graph.json`, and pass it explicitly to the endpoint scanner with `--graphify-index`. Do not use `scripts/ensure_graphify_index.py` as the primary invocation path; it is only a last-resort wrapper when skill invocation is unavailable. Read the graph first as an index of candidate source artifacts, symbols, locations, and relationships.
2. **Capability preflight**: inspect build files, dependency manifests, runtime configs, and framework imports to identify possible endpoint families. Keep these as audit hints until confirmed by code/config usage.
3. **Endpoint-kind rules**: select candidate nodes by `rules/types/<kind>_rules.md` and supporting family rules such as `rules/database_table_rules.md`; do not blindly convert every graph node or string literal into an endpoint.
4. **Focused source confirmation**: read the candidate node's `source_file`, nearby `source_location`, and directly associated files needed by the rule.
5. **Framework metadata**: OpenAPI specs, protobuf files, GraphQL schemas, AsyncAPI, routing configs, Spring annotations, FastAPI/Flask route declarations, Express routers, NestJS controllers, gRPC service definitions.
6. **AST-aware code scan**: use parsers or the bundled scanner when Graphify is incomplete, when candidate graph nodes need source confirmation, or when graph generation is explicitly unavailable.
7. **Pattern scan**: use regex only as a fallback and mark confidence accordingly.
8. **Config scan**: inspect YAML/properties/env templates for topic names, cron jobs, table mappings, distributed-cache prefixes, file paths, SDK clients, and data model names.

Follow `rules/graphify_index_workflow.md` for the graph-index-first analysis
sequence.

Follow `rules/analysis_scope_rules.md` before endpoint emission. Exclude unit
tests and generated/local artifacts by default; include production resources,
dependency modules, machine-readable contracts, and deployment metadata only
when they provide runtime contract evidence.

For every endpoint kind, first check its dedicated rule file in `rules/types/`.
Use the older family rule files below as cross-cutting elaboration and
compatibility references.

For `DB_TABLE` endpoints, follow `rules/types/db_table_rules.md` and
`rules/database_table_rules.md`. In Graphify
outputs, the table name itself is usually not a standalone node. Prefer nodes
that carry table semantics, such as model metadata JSON, production Mapper Java
nodes, mapper method or SQL annotation nodes, and mapper XML files paired from a
production Mapper node. Exclude test SQL, assertions, examples, docs, traces,
and resource file paths masquerading as `FILE` endpoints.

For `DATAMODEL`, `DATA_API_CALL`, `DATA_API_STREAM`, and
`ANALYTICS_MODEL_QUERY` endpoints, follow
`rules/types/datamodel_rules.md` and `rules/datamodel_rules.md`. In systems
where a datamodel FQN is exposed primarily through a data proxy, prefer
`DATA_API_CALL` for ordinary DataAPI SDK calls and `DATA_API_STREAM` for
DataAPI WebSocket/fetch-style access, using the datamodel FQN as the
identifier. Treat SQL as query-language evidence on `DATA_API_CALL` or
`DATA_API_STREAM` when a `data.*` model FQN is reached through SQL executed by
a data proxy or model SQL support layer. Use `ANALYTICS_MODEL_QUERY` when that
SQL path is visibly OLAP/HTAP, bitmap/columnar-analysis oriented, or routed to
an analytics engine. Treat model/event schema creation and migration/init files
as setup evidence, not business endpoints. For Shuyun EventService or other
event buses, emit runtime event publish/consume contracts as
`EVENT_BUS_PUBLISHER` / `EVENT_BUS_LISTENER`. Keep `DATAMODEL` only for
unresolved semantic FQN evidence that
cannot yet be tied to a concrete access/schema/event mode. Do not classify
`*Repository`, `*Mapper`, DAO, or ORM entity names as data models by naming
convention alone. A `DATAMODEL` requires explicit semantic model evidence such
as model metadata `fqn`, data API/data client abstractions, openapi FQN model
resolution, or visible Java constants such as `TaskLog.FQN` whose resolved
string is a `data.*` model FQN. Exclude configuration keys such as
`spring.data.redis.ssl.enabled` and `data.redis.ssl.enabled`; they are runtime
configuration, not datamodel FQNs.

For `HTTP_API` endpoints, follow `rules/types/http_api_rules.md` and
`rules/http_endpoint_rules.md`. The identifier
must be `METHOD /full/path`. For Spring controllers, class-level
`@RequestMapping` is a path prefix and must be combined with method-level
mapping; it is not a standalone API endpoint.

For message, HTTP egress, distributed cache, event bus, and scheduled integration endpoints,
follow their dedicated files under `rules/types/` plus
`rules/integration_endpoint_rules.md`. In this Java/Spring codebase,
important runtime contracts include `@RabbitListener`, project Rabbit producer
annotations, Feign, Retrofit, RestTemplate wrapper calls, Spring application
events, Redis/distributed-cache key contracts, and `@XxlJob`. Do not treat
`CommandLineRunner` bootstrap classes or WebSocket infrastructure as endpoint
contracts unless there is explicit user-facing command or route/channel
evidence.

When a source file is a Feign or Retrofit client contract, mapping annotations
inside it are outbound `HTTP_CALL` endpoints, not ingress `HTTP_API` endpoints.
HTTP identifiers must exclude query strings; store query parameters in
`match_rule.query_params`. Resolve Java constants for queue names, routing keys,
Redis key names, datamodel `*.FQN` constants, and `@TableName` values whenever
visible. Preserve stable dynamic templates when source combines fixed contract
prefixes with runtime dimensions such as tenant, client, group, shard, or
domain; the unresolved parts belong in `{placeholder}` form in `identifier` and
the raw expression belongs in `match_rule`. Do not treat SQL column assignments such as `UPDATE costCount = ...`
as `DB_TABLE`; the table must come from table-position SQL, ORM table metadata,
or model/datamodel FQN evidence. Do not emit `FILE`
endpoints for import/export templates, browser downloads, local classpath
resources, response filenames, or process-local memory caches such as Caffeine.
Do not emit `DISTRIBUTED_CACHE` for `MemoryCacheKeyEnum`, `CaffeineCache`, or
Spring Cache annotations unless there is explicit Redis/distributed backend
evidence.

## Output Schema

Write a JSON object with this shape:

```json
{
  "schema_version": "endpoint-profiler.v1",
  "source_root": "...",
  "generated_at": "ISO-8601 timestamp",
  "services": [
    {
      "name": "checkout-service",
      "root": "apps/checkout",
      "runtime_evidence": ["SpringBootApplication", "runtime application config"],
      "dependencies": ["shared-domain", "data-client"],
      "scope_roots": ["apps/checkout", "libs/shared-domain", "libs/data-client"]
    }
  ],
  "endpoints": [
    {
      "id": "stable hash or readable id",
      "direction": "ingress",
      "kind": "HTTP_API",
      "identifier": "GET /api/orders/{id}",
      "match_rule": {
        "type": "path_template",
        "method": "GET",
        "path": "/api/orders/{id}"
      },
      "owner": {
        "service": "checkout-service",
        "module": "optional module or package",
        "service_scope": "runtime or dependency"
      },
      "source": {
        "file": "relative/path",
        "line": 123,
        "symbol": "optional function/class"
      },
      "metadata": {
        "framework": "optional framework",
        "operation": "optional operation name",
        "confidence": 0.9,
        "evidence": ["short visible evidence strings"]
      }
    }
  ],
  "audit": {
    "graphify_used": true,
    "scan_modes": ["graphify", "ast", "pattern"],
    "warnings": []
  }
}
```

Rules:

- `direction` must be `ingress` or `egress`.
- `kind` must be one of the taxonomy values.
- `identifier` must be stable, semantic, and free of regex syntax.
- `match_rule` carries method/path matching, topic semantics, table name matching, cache prefix matching, cron expression, file glob, or SDK client package.
- Use relative paths from the analyzed root.
- Include confidence and evidence for every endpoint.
- Within the same owning service, the same `direction + kind + identifier`
  represents one endpoint node. Merge repeated source hits into one endpoint and
  keep extra evidence in metadata rather than emitting duplicate nodes.
- `services` lists discovered microservices and the dependency-closure scan scope used for each one.
- `owner.service` must name the discovered microservice when the endpoint was found in a service-scoped scan.
- `owner.service_scope` should be `runtime` when the endpoint source is under the service runtime module and `dependency` when it comes from a dependency module included in that service's closure.

## Extraction Workflow

1. **Resolve inputs**
   - Accept an input directory and optional output directory.
   - Default output path: `<input>/endpoint-profiler-out/endpoints.json`.
   - If the user gives no path, use the current working directory.

2. **Discover microservices before endpoint extraction**
   - First identify the microservices contained in the target directory.
   - A microservice is a runtime or deployment boundary, not merely a child folder. Use evidence such as Spring Boot application classes, runtime application configs, service manifests, Docker/package descriptors, OpenAPI server modules, worker/event consumer bootstraps, and scheduler executors.
   - Build each microservice's analysis scope as a dependency closure. For Maven projects, parse `pom.xml` module declarations and internal dependencies; for other stacks, use package/workspace manifests and import/dependency evidence.
   - Record each microservice in `services` with `name`, runtime `root`, `dependencies`, and `scope_roots`.
   - When a service depends on shared modules, scan those dependency directories as part of that service. Do not equate "one subfolder" with "one microservice".

3. **Build the Graphify index**
   - Locate `graphify-out/graph.json` from the input, sibling output directory, parent directory, or explicit user path.
   - If no usable `graph.json` exists, invoke the `$graphify` skill on the input directory before endpoint extraction. After the skill writes `graphify-out/graph.json`, pass that file explicitly as `--graphify-index <input_dir>/graphify-out/graph.json` to the bundled endpoint scanner. If the `$graphify` skill warns that the corpus has more than 200 files or 2,000,000 words, treat it as a scope confirmation and scheduling signal, not an automatic blocker. For an explicit full-repository endpoint profiling request, proceed with the full corpus, use Graphify's subagent chunking to run semantic extraction in parallel, and record the large-corpus decision in `audit.warnings`. Ask for a narrower scope only when the user did not request full coverage or when subagents/Graphify execution are unavailable.
   - Treat `graph.json` as the source-artifact index for endpoint extraction.
   - Select candidate graph nodes by endpoint-family rules before reading broad source content.
   - Treat Graphify nodes as pointers to evidence, not final endpoints.

4. **Apply analysis scope rules**
   - Apply `rules/analysis_scope_rules.md` before reading or emitting candidate endpoints.
   - Exclude test directories, examples, mocks, local artifacts, build outputs, traces, logs, and natural-language docs by default.
   - Include production source, runtime resources, dependency-closure modules, and machine-readable contracts when they carry endpoint evidence.
   - Use deployment/ops files only as service-boundary or configuration evidence, not endpoint contracts by themselves.

5. **Confirm candidates with source/config**
   - For each candidate node, read its `source_file`, nearby `source_location`, and directly associated files required by the rule.
   - Preserve only endpoints supported by visible code/config evidence.
   - When Graphify is incomplete after generation, fall back to direct source scanning and record the fallback in `audit.warnings`.

6. **Extract ingress per microservice scope**
   - HTTP route decorators and router registrations.
   - RPC service/method definitions.
   - WebSocket handlers and channel paths.
   - Message consumers and event listeners.
   - Cron/scheduled jobs.
   - CLI commands and subcommands.

7. **Extract egress per microservice scope**
   - HTTP client calls and URL templates.
   - RPC clients and stubs.
   - Database tables and ORM mappings.
   - Cache key prefixes and named cache regions.
   - Message producers and event publishers.
   - Data API/data client/data model abstractions.
   - SDK clients and file-based integration paths.

8. **Normalize**
   - Convert framework-specific syntax into taxonomy kinds.
   - Move dynamic matching details to `match_rule`.
   - Keep identifiers clean: `/users/{id}` is OK; `/users/:*`, `/users/.*`, or `/users?id=*` is not.
   - If the same dependency endpoint is relevant to multiple microservices, emit one record per owning microservice rather than collapsing service ownership.

9. **Verify**
   - Validate JSON parseability and schema fields.
   - Check all kinds are legal.
   - Check identifiers contain no obvious regex/wildcard syntax.
   - Check endpoints have source evidence.
   - Check that discovered microservices are runtime boundaries and that dependency `scope_roots` can span multiple directories.
   - Report warnings rather than inventing missing data.

10. **Run required source sampling audit**
   - After every endpoint profiling run, run the procedure in
     `references/llm-trace-audit.md` as a required quality gate.
   - This step is mandatory, not optional smoke QA. The run is incomplete until
     the audit file exists, is non-empty, is newer than the current
     `endpoints.json`, includes the documented rule-gap discovery review, and
     states `Audit Verdict: PASS` or `Audit Verdict: FAIL`.
   - Group production source/config files by layer, such as controller,
     listener, scheduler, client, service, repository/mapper, and config.
   - Sample 10% of endpoint-looking files per layer, with at least one file per
     layer.
   - Prefer Graphify node/source metadata to choose and inspect samples; read
     source directly when graph evidence is absent or insufficient.
   - For each sampled source file, derive visible ingress/egress endpoint
     evidence and compare it with `endpoints.json`.
   - Mark the audit `PASS` only when sampled source evidence is represented
     correctly and completely in `endpoints.json` with no unsupported
     redundancy.
   - Save the audit as
     `<output_dir>/endpoint_llm_trace_audit_<YYYYMMDD>.md`.
   - This audit may use trace/call paths as evidence, but its purpose is to
     validate correctness, completeness, and no redundancy.

11. **Run required endpoint trace sampling audit**
   - Run the procedure in `references/graph-edge-trace-audit.md` as the second
     required quality gate.
   - This audit samples endpoint records from `endpoints.json`, uses Graphify
     evidence first and source evidence when needed, and checks whether sampled
     endpoints plus endpoint evidence reached during confirmation are complete,
     correct, and non-redundant in `endpoints.json`.
   - This step is mandatory, not optional smoke QA. The run is incomplete until
     the audit file exists, is non-empty, is newer than the current
     `endpoints.json`, includes graph rule-gap discovery, and states
     `Audit Verdict: PASS` or `Audit Verdict: FAIL`.
   - For each endpoint kind, sample up to 10 diverse endpoint records, or all
     records when fewer than 10 exist.
   - Prefer Graphify mapping and graph/source-file evidence to reduce token
     cost. If graph evidence is incomplete, ambiguous, or lacks needed
     relations, read source directly.
   - Save the audit as
     `<output_dir>/endpoint_graph_edge_trace_audit_<YYYYMMDD>.md`.
   - This audit may describe graph/source paths for QA, but the purpose is
     endpoint inventory validation, not topology reconstruction.

## Bundled Scanner

For a first pass after `$graphify` has produced a graph index, run:

```powershell
python scripts/endpoint_profiler.py <input_dir> --graphify-index <input_dir>/graphify-out/graph.json --out <output_dir>
```

When Graphify output is outside the source root, pass it explicitly:

```powershell
python scripts/endpoint_profiler.py <input_dir> --graphify-index <graphify-out/graph.json> --out <output_dir>
```

If skill invocation is unavailable, the legacy wrapper can be used as a
last-resort fallback, but it is not the preferred Graphify invocation path:

```powershell
python scripts/ensure_graphify_index.py <input_dir>
```

The scanner reads `graph.json` before source scanning, extracts endpoint-looking
source candidates from graph nodes, scans those candidate files first, and only
then scans remaining source files as fallback coverage.

The scanner writes a full aggregate inventory to `<output_dir>/endpoints.json`.
After the aggregate inventory is written, it must derive service-specific JSON
files from that aggregate inventory. When microservices are discovered, it also
writes per-service inventories to
`<output_dir>/services/<service-name>/endpoints.json`, flat root-level
inventories named `<output_dir>/<microservice-name>_endpoints.json`, and
`<output_dir>/services/manifest.json`.

The scanner also writes a human-readable aggregate report to
`<output_dir>/endpoints_result.html`. When per-service inventories are
generated, each service directory also gets its own `endpoints_result.html`.
Reports must include kind-level statistics, a service-by-kind matrix, clusters
for every endpoint kind, lowest-confidence samples per kind, and collapsible
all-detail tables grouped by endpoint kind.

The scanner is deterministic and graph-index aware, with pattern-assisted source
confirmation. It is not a complete semantic compiler; use its output as a draft
inventory. A complete endpoint profiler run is not finished until the required
source sampling audit and the required endpoint trace sampling audit have also
been written.

After writing `endpoints.json`, generate the required source-reading audit with
the bundled quality audit helper:

```powershell
python scripts/generate_quality_audits.py <output_dir> --source-root <input_dir>
```

The helper writes both required audit reports. The first report performs
layered source-file sampling. The second report performs endpoint-record
sampling with Graphify-first evidence and source fallback.

## Verifier Loop

When evolving this skill or using it on a target project, apply a CoEvoSkills-style loop:

1. Generate endpoint JSON with the scanner and manual review.
2. Run verifier checks from `references/verifier.md`.
3. Run the required source sampling audit from `references/llm-trace-audit.md`.
4. Run the required endpoint trace sampling audit from
   `references/graph-edge-trace-audit.md`.
5. If verifier or audit fails, patch the smallest extractor rule, instruction
   section, fixture, or verifier check.
6. If local verifier passes but a downstream/oracle consumer rejects the inventory, do not hardcode the rejected case. Add a general visible-rule check to the verifier and rerun.

See also:

- `rules/analysis_scope_rules.md` for in-scope and out-of-scope path rules.
- `rules/database_table_rules.md` for `DB_TABLE` extraction policy.
- `rules/datamodel_rules.md` for `DATAMODEL` extraction policy.
- `rules/http_endpoint_rules.md` for `HTTP_API` identifier and route rules.
- `rules/integration_endpoint_rules.md` for message, HTTP egress, cache, event,
  and scheduled integration endpoint policy.
- `rules/graphify_index_workflow.md` for the graph-index-first extraction flow.
- `references/directory-structure.md` for the intended skill package layout.
- `references/llm-trace-audit.md` for the source sampling audit quality gate.
- `references/graph-edge-trace-audit.md` for the endpoint trace sampling audit
  quality gate.

## What Not to Do

- Do not draw edges between ingress and egress endpoints.
- Do not treat either audit as a topology report; both audits validate
  correctness, completeness, and redundancy of `endpoints.json`.
- Do not add graph paths or trace chains into `endpoints.json`.
- Do not infer that two endpoints are connected just because names are similar.
- Do not emit infrastructure nodes as endpoints.
- Do not leak hidden benchmark answers into identifiers.
- Do not convert every string literal into an endpoint.
- Do not use broad regex identifiers; put matching looseness in `match_rule`.
