# Endpoint Profiler Verifier

Use this reference to validate endpoint profiler output.

## Required Checks

1. JSON parses successfully.
2. Top-level keys include `schema_version`, `source_root`, `generated_at`, `endpoints`, and `audit`.
3. Every endpoint has `id`, `direction`, `kind`, `identifier`, `match_rule`, `source`, and `metadata`.
4. `direction` is exactly `ingress` or `egress`.
5. `kind` is one of:
   - `HTTP_API`
   - `RPC_ROUTE`
   - `WebSocket`
   - `MESSAGE_CONSUMER`
   - `EVENT_BUS_LISTENER`
   - `SCHEDULED_JOB`
   - `CLI`
   - `HTTP_CALL`
   - `RPC_CALL`
   - `DB_TABLE`
   - `DISTRIBUTED_CACHE`
   - `MESSAGE_PRODUCER`
   - `EVENT_BUS_PUBLISHER`
   - `DATAMODEL`
   - `DATA_API_CALL`
   - `DATA_API_STREAM`
   - `DATA_MODEL_SQL`
   - `ANALYTICS_MODEL_QUERY`
   - `DATA_MODEL_SCHEMA`
   - `DATA_EVENT_SCHEMA`
   - `DATA_EVENT_PUBLISHER`
   - `SDK`
   - `FILE`
6. `identifier` is non-empty and does not contain regex-only syntax such as `.*`, `:*`, `(?`, `[` character classes, or trailing `*` wildcards.
7. HTTP identifiers use `METHOD /path` for ingress APIs and URL or host/path contracts for egress calls.
8. `match_rule` carries method/path/topic/table/distributed-cache/file matching details.
9. Every endpoint has a relative source file path where possible.
10. Every endpoint has `metadata.confidence` between `0` and `1`.
11. `FILE` endpoints are allowed only when the evidence shows file-based system integration: a shared file contract used to exchange data between systems through OSS/S3/bucket storage, FTP/SFTP, shared directories, batch import/export integration, partner feeds, or similar file-transfer channels.
12. `FILE` endpoints must not be emitted for internal implementation files or user-facing downloads, including `mapper.xml`, migration scripts, classpath resources, static templates, trace/verification files, unit-test fixtures, local developer paths, log files, or controller response filenames.
13. For every `FILE` endpoint, `match_rule` should include `integration: true` or an equivalent visible file-exchange channel such as `channel: "oss"`, `channel: "sftp"`, `channel: "shared_directory"`, `channel: "partner_feed"`, or `channel: "batch_exchange"`.
14. If the target contains multiple runtime services, top-level `services` should be present and each service should include `name`, `root`, `dependencies`, and `scope_roots`.
15. Service detection must use runtime/deployment evidence, not raw child-folder count. Maven aggregators or shared libraries without bootstraps should not be treated as microservices merely because they are folders.
16. A service's `scope_roots` may span multiple directories through dependency closure. At least one test fixture should prove that an endpoint in a shared dependency module is attributed to the runtime service with `owner.service_scope = "dependency"`.
17. Endpoints produced during service-scoped scans should include `owner.service`. Endpoints from the service runtime module should use `owner.service_scope = "runtime"`; endpoints from dependency modules should use `owner.service_scope = "dependency"`.
18. When microservices are discovered, the output directory must contain per-service files at `services/<service-name>/endpoints.json` and a `services/manifest.json`.
19. Each per-service file must contain only endpoints whose `owner.service` equals that service, and its endpoint count must match the corresponding manifest count.
20. The aggregate `endpoints.json` remains the full inventory; per-service files are projections, not replacements.
21. `DB_TABLE` endpoints must be `egress` endpoints with `match_rule.type = "table"`.
22. `DB_TABLE` endpoints must not be emitted from `src/test/**`, `*Test.java`, assertion expected strings, docs, logs, trace files, or examples.
23. For database tables, Graphify table names are usually not standalone nodes. Verifier fixtures should prove extraction from table-carrying source nodes such as model metadata JSON, production Mapper Java nodes, SQL annotation nodes, and mapper XML associated with production Mapper nodes.
24. `DISTRIBUTED_CACHE` endpoints must be `egress` endpoints with `match_rule.type = "distributed_cache"` and explicit backend evidence such as `match_rule.backend = "redis"`.
25. In-memory caches such as Caffeine, Guava Cache, local maps, `MemoryCacheKeyEnum`, and Spring Cache annotations without distributed-backend evidence must not be emitted as endpoints.
24. When Graphify is available, `audit.graphify_used` should be `true`, `audit.graphify_index_path` should identify the graph index, and `audit.scan_modes` should include `graphify-index`.
25. Endpoint extraction must apply `rules/analysis_scope_rules.md`: unit tests, examples, mocks, logs, traces, build outputs, and natural-language docs should not be endpoint sources unless a documented exception applies.
26. Production resource/config files may be endpoint evidence only for allowed families, such as mapper XML for `DB_TABLE`, model JSON for `DB_TABLE`/`DATAMODEL`/`DATA_MODEL_SCHEMA`/`DATA_EVENT_SCHEMA`, and runtime config for service/topic/cache/job evidence.
27. Shared modules should be included only through a discovered service dependency closure and should emit endpoints with `owner.service_scope = "dependency"`.
28. Standard output must include aggregate `endpoints_result.html`; when per-service splits are generated, each `services/<service-name>/` directory must also include `endpoints_result.html`.
29. The HTML report should include kind-level statistics, service-by-kind matrix, clusters for each endpoint kind, and lowest-confidence samples per kind.
30. Within the same owning service, `direction + kind + identifier` should be a single endpoint node. Repeated source hits should be merged into evidence/source references, not emitted as duplicate endpoint rows.
31. Lowest-confidence sample tables in HTML should include a `Kind` column.
32. `DATAMODEL` and data-model-specific endpoints must require explicit semantic model evidence. `*Repository`, `*Mapper`, DAO, and ORM entity names must not be classified as data models by naming convention alone. `data.redis.*` and `spring.data.*` configuration keys must not be emitted as datamodel endpoints.
33. `HTTP_API.identifier` must be `METHOD /full/path`. Spring class-level `@RequestMapping` prefixes must not be emitted as standalone `ANY prefix` endpoints.
34. The HTML report should include collapsible all-detail tables grouped by endpoint kind.
35. Every endpoint kind should have a dedicated rule file under `rules/types/`; when a kind-specific rule changes, add or update a verifier fixture/assertion that exercises that rule.
36. A complete endpoint profiler run must include a source sampling audit following `references/llm-trace-audit.md`: sample 10% of source files from each code layer, use Graphify evidence first and source fallback when needed, infer visible endpoint kinds from sampled source, and verify those sampled endpoints are present, correct, complete, and non-redundant in `endpoints.json`.
37. A complete endpoint profiler run must include an endpoint trace sampling audit following `references/graph-edge-trace-audit.md`: sample extracted endpoints by kind, use Graphify evidence first and source fallback when needed, and verify sampled endpoint evidence plus any reached endpoint evidence are present, correct, complete, and non-redundant in `endpoints.json`. Its purpose is endpoint inventory quality validation, not topology generation.

## Executable Verifier

Run the bundled deterministic verifier against any output directory:

```powershell
python scripts/verify_endpoint_profiler.py <output_dir>
```

The verifier checks:

- Aggregate `endpoints.json` parseability and endpoint schema.
- Legal endpoint kinds, directions, confidence range, relative source paths, and clean identifiers.
- `FILE` endpoint integration/channel semantics.
- `DB_TABLE` endpoint direction, table match-rule semantics, and test-source exclusion.
- Graphify index audit fields when a graph index is available. Endpoint
  profiling should use an existing `graphify-out/graph.json`, or invoke the
  `$graphify` skill to generate one before broad source scanning unless the
  user explicitly disables it or Graphify execution is unavailable. A Graphify
  large-corpus warning (>200 files or >2,000,000 words) is not by itself a
  verifier-acceptable reason to skip Graphify for an explicit full-repository
  endpoint profiling request; the run should proceed through Graphify's
  subagent chunk workflow and record the scope decision in audit warnings.
  `scripts/ensure_graphify_index.py` is a last-resort wrapper only when skill
  invocation is unavailable, not the preferred call path.
- Analysis scope filtering: test/example/build/log/doc paths are excluded, while production resources and dependency closures are handled according to `rules/analysis_scope_rules.md`.
- Microservice metadata shape.
- Per-service split files and `services/manifest.json`.
- Split-file consistency: all endpoints in `services/<service>/endpoints.json` must have `owner.service == <service>`.
- Dependency-closure regression: if a service has multiple `scope_roots`, at least one endpoint should be attributable to `owner.service_scope = "dependency"` in suitable multi-module outputs.
- Standard HTML report presence for aggregate and per-service outputs.
- Required audit report presence, non-empty content, freshness, and verdict are
  checked by `scripts/verify_endpoint_profiler.py`.
- The first audit file, `endpoint_llm_trace_audit_<YYYYMMDD>.md`, is a source
  sampling audit. It must include `Source Sampling Audit`, `Rule Gap
  Discovery`, and `Audit Verdict: PASS` or `Audit Verdict: FAIL`.
- The second audit file, `endpoint_graph_edge_trace_audit_<YYYYMMDD>.md`, is an
  endpoint trace sampling audit. It must include `Endpoint Trace Sampling
  Audit`, `Graph Rule Gap Discovery`, and `Audit Verdict: PASS` or
  `Audit Verdict: FAIL`.
- Either audit verdict `FAIL` fails verification. Trace paths are evidence
  gathering tools; the verdict is about correctness, completeness, and
  redundancy of `endpoints.json`.
- For current reports, the source sampling audit must compare sampled source
  evidence against `endpoints.json` and state `Audit Verdict: PASS` or
  `Audit Verdict: FAIL`. Legacy source trace reports are still checked for
  excessive unresolved trace statuses only when the new `Source Sampling Audit`
  marker is absent.

## Surrogate Test Sources

Derive expected checks only from visible inputs:

- Task instruction.
- Public source code and config.
- Graphify outputs, if present.
- Public API specs or schemas.
- Deterministic scanner behavior.

Do not derive expected endpoints from hidden answers or downstream graph engine output.

## Common Failure Diagnostics

**Infrastructure identifier**

- Symptom: `identifier` is `mysql-prod:3306`, `kafka-cluster`, or a microservice name.
- Fix: replace with logical table, topic, event type, data model, API route, or SDK contract.

**Regex leaked into identifier**

- Symptom: `GET /orders/:*` or `topic.order.*`.
- Fix: normalize to a clean fingerprint and express fuzzy matching in `match_rule`.

**Direction confusion**

- Symptom: HTTP client calls classified as `HTTP_API`.
- Fix: route declarations are ingress; client calls are egress.

**Topology leakage**

- Symptom: output contains edges such as `serviceA -> serviceB`.
- Fix: remove edges; keep only endpoint records.

**Over-extraction**

- Symptom: every URL-looking string is emitted.
- Fix: require framework/client usage evidence and lower confidence for config-only clues.

**FILE endpoint over-extraction**

- Symptom: `mapper.xml`, trace verification `.txt`, classpath template files, local test files, migration JSON, or browser download filenames are classified as `FILE`.
- Fix: remove these records. `FILE` means a logical file-sharing integration contract between systems, not an arbitrary file path or downloadable response attachment.
- Valid evidence examples: OSS/S3 object keys used for cross-service transfer, SFTP/FTP paths, partner feed file names, shared import/export directories, batch exchange files, or data files consumed/produced by an integration job.
- Invalid evidence examples: `DownloadUtils.downloadExcel(response, "...xlsx")`, `@GetMapping("/MP_verify_{content}.txt")`, `ClassPathResource("...xlsx")`, `src/main/resources/mapper/*.xml`, `src/test/...`, local `C:\Users\...` paths, trace/debug/log files.

**Microservice boundary mistaken for folder boundary**

- Symptom: every child directory is emitted as a service, including aggregators, shared libraries, mapper-only modules, or SDK modules with no runtime bootstrap.
- Fix: require runtime/deployment evidence and build dependency closure from manifests before scanning endpoints.

**Dependency endpoints missing from service scope**

- Symptom: endpoints/tables/cache keys in `core`, `service`, `sdk`, or shared modules are absent from a runtime service's inventory even though the service depends on them.
- Fix: expand `scope_roots` using internal dependencies and attribute those endpoints to the owning runtime service with `owner.service_scope = "dependency"`.

**Out-of-scope source emitted as endpoint**

- Symptom: endpoints are emitted from `src/test`, examples, mocks, generated reports, logs, traces, build outputs, or natural-language docs.
- Fix: apply `rules/analysis_scope_rules.md` before endpoint-family extraction. Keep only production runtime, dependency-closure, resource/config, or machine-readable contract evidence.

## Verifier Report Format

```text
Endpoint profiler verifier
Input: path/to/endpoints.json
Result: PASS | FAIL
Counts:
- total endpoints:
- ingress:
- egress:
Failures:
- endpoint id: check name -> observed -> expected -> suggested fix
Warnings:
- low-confidence or ambiguous evidence
```
