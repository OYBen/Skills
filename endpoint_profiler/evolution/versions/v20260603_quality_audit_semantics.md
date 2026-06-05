# Version: v20260603_quality_audit_semantics

Date: 2026-06-03

Summary:

- Reframed the two required endpoint-profiler audits as quality gates for `endpoints.json`, matching the user's corrected semantics.
- Added `scripts/generate_quality_audits.py` to generate:
  - Source Sampling Audit: 10% source sampling by code layer, Graphify-first, source fallback, expected endpoint kinds compared with `endpoints.json`.
  - Endpoint Trace Sampling Audit: sampled extracted endpoints validated for evidence, completeness, correctness, and redundancy.
- Updated verifier behavior so required audit reports must contain explicit markers and `Audit Verdict: PASS`.
- Updated skill and reference docs so future runs do not treat these reports as topology trace reports.

Validation:

- Audit generation completed on `D:\kylin_product_repo\MA\marketing-automation-develop-profile-out`.
- Endpoint Trace Sampling Audit passed.
- Source Sampling Audit failed and verifier failed accordingly, proving the hard quality gate is active.

Known remaining work:

- Current MA output has extraction gaps surfaced by the source sampling audit.
- Next evolution should improve extraction rules for client wrappers, producer configuration, event publication, and datamodel classification, then re-run the profiler and both audits.
