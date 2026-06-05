# Endpoint Profiler Directory Structure

This skill should keep runtime instructions, extractor code, verifier code,
domain rules, schemas, and tests separate so each part can evolve without
turning `SKILL.md` into a large implementation file.

## Current Target Layout

```text
endpoint_profiler/
  SKILL.md
  rules/
    graphify_index_workflow.md
    analysis_scope_rules.md
    database_table_rules.md
    datamodel_rules.md
    http_endpoint_rules.md
    integration_endpoint_rules.md
    types/
      http_api_rules.md
      rpc_route_rules.md
      websocket_rules.md
      message_consumer_rules.md
      event_bus_listener_rules.md
      scheduled_job_rules.md
      cli_rules.md
      http_call_rules.md
      rpc_call_rules.md
      db_table_rules.md
      distributed_cache_rules.md
      message_producer_rules.md
      event_bus_publisher_rules.md
      datamodel_rules.md
      sdk_rules.md
      file_rules.md
  references/
    output-schema.json
    verifier.md
    directory-structure.md
    llm-trace-audit.md
    graph-edge-trace-audit.md
  scripts/
    endpoint_profiler.py
    verify_endpoint_profiler.py
  tests/
    fixtures/
      db_table/
      endpoint_taxonomy/
```

## Responsibilities

- `SKILL.md`
  - Short trigger-facing instructions.
  - Taxonomy, execution workflow, and links to detailed rule files.
  - Should stay concise enough to be read on every skill invocation.

- `rules/`
  - Domain-specific extraction policy.
  - Cross-cutting rule sets plus `types/` files for each endpoint kind.
  - Examples: `database_table_rules.md`, `file_endpoint_rules.md`,
    `microservice_scope_rules.md`, `datamodel_rules.md`.
  - `graphify_index_workflow.md` defines the cross-cutting graph-index-first
    analysis order used by all endpoint families.
  - `analysis_scope_rules.md` defines which directories and graph nodes are in
    scope before endpoint-family extraction runs.
  - `types/<kind>_rules.md` defines the authoritative extraction boundary,
    identifier policy, evidence, and exclusions for one endpoint kind.

- `references/`
  - Stable reference material that is not executable.
  - Output schemas, verifier contract, report formats, and architecture notes.
  - `llm-trace-audit.md` defines the required source-reading audit for tracing
    sampled ingress endpoints to egress endpoints and sampled egress endpoints
    back to ingress endpoints.
  - `graph-edge-trace-audit.md` defines the required Graphify edge audit for
    tracing sampled ingress endpoints downstream to egress endpoints and sampled
    egress endpoints upstream to ingress endpoints through `graph.json`.

- `scripts/`
  - Deterministic executable tools bundled with the skill.
  - Scanner, verifier, report generators, and small utilities.
  - Scripts should read rule intent from code comments or rule files but must
    remain executable without an LLM.
  - `endpoint_profiler.py` owns the standard JSON and HTML outputs, including
    `endpoints_result.html`.

- `tests/fixtures/`
  - Small synthetic projects for verifier and extractor regression tests.
  - Fixture names should describe the behavior being tested, not the customer
    project that revealed it.

## Evolution Rules

1. Add a rule file when an endpoint family starts accumulating special cases.
2. Add a verifier fixture whenever a false positive or false negative is fixed.
3. Keep project-specific observations out of generic rules unless they express a
   reusable extraction principle.
4. Prefer additive structure over moving files that external instructions may
   already reference.
5. Sync the skill to every active Codex skill root when this environment has both
   `.agents/skills` and `.codex/skills` copies.
