# Endpoint Trace Sampling Audit

Run this audit after every endpoint profiler execution. Despite the historical
filename, its primary purpose is not graph tracing. It validates endpoint
profiler correctness, completeness, and redundancy by sampling endpoints and
checking the evidence reachable from those samples.

## Purpose

The audit samples endpoint records from `endpoints.json`, follows Graphify
evidence first and source evidence when needed, and checks whether the sampled
endpoint and any endpoint evidence reached during confirmation are correctly
represented in `endpoints.json`.

The question is:

```text
For sampled endpoint records and endpoint evidence reached from them, is
endpoints.json correct, complete, and free of unsupported redundancy?
```

## Evidence Priority

1. Use `graphify-out/graph.json` first for endpoint-to-source mapping,
   source-file coverage, candidate call/data-flow paths, and endpoint-looking
   graph nodes.
2. If graph evidence is incomplete, ambiguous, or lacks the needed relation,
   read the relevant source files.
3. Trace paths are evidence-gathering tools only; the audit verdict is about
   endpoint inventory quality.

## Sampling Rules

1. For each endpoint kind present in `endpoints.json`, sample up to 10 diverse
   endpoint records.
2. Prefer distinct services, source files/classes, identifiers, and endpoint
   families.
3. If a kind has fewer than 10 records, audit all available records.

## Required Checks

For every sampled endpoint:

1. Confirm the endpoint has visible graph/source evidence.
2. Confirm direction, kind, identifier, source, and match rule are correct.
3. Follow graph/source evidence far enough to detect adjacent endpoint evidence
   relevant to completeness.
4. Confirm every reached endpoint contract exists in `endpoints.json`.
5. Confirm sampled endpoint records are not duplicates or unsupported by
   evidence.
6. Mark `PASS` only when the sampled endpoint and reached endpoint evidence are
   correct, complete, and non-redundant. Mark `FAIL` otherwise.

If graph/source evidence reaches only framework facilities, generic wrappers,
DTO fields, dynamic data-access helpers, or infrastructure retry/error paths,
do not treat those reached nodes as missing business endpoints. Follow callers
or callees far enough to find a concrete business contract; if no stable
contract can be identified, record the path as insufficient semantic evidence
rather than an endpoint gap.

## Graph Rule Gap Discovery

Include a section named exactly `Graph Rule Gap Discovery`.

Compare endpoint-looking graph/source evidence against `endpoints.json`.
Rows where reached evidence is absent or misclassified are
`MISSING_ENDPOINT_RULE` or `NEEDS_SOURCE_CONFIRMATION` candidates.

## Required Report

Write:

```text
<output_dir>/endpoint_graph_edge_trace_audit_<YYYYMMDD>.md
```

The report must include:

- input source root, endpoint JSON path, graphify index path, and audit date
- `Audit Verdict: PASS` or `Audit Verdict: FAIL`
- graph summary and graph coverage summary
- `Endpoint Trace Sampling Audit`
- one row per sampled endpoint with graph/source evidence status, verdict, and
  notes
- `Graph Rule Gap Discovery`
- findings grouped by completeness gaps, correctness issues, redundancy issues,
  graph coverage gaps, and source confirmation needed

## Boundaries

- Do not treat graph paths as topology output.
- Do not add edges to `endpoints.json`.
- Prefer Graphify for token efficiency, but read source whenever graph evidence
  is not enough to judge correctness, completeness, or redundancy.
