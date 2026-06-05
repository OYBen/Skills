# Verifier Result

Status: FAIL, by design for the current profiled output.

Reason:

```text
required_audit.source_trace.verdict: observed='FAIL'; expected=PASS; audit quality gate failed
```

The verifier now treats either required audit's `Audit Verdict: FAIL` as a hard failure. This matches the user-provided semantics: incomplete, incorrect, or redundant sampled endpoint coverage must not pass.

The endpoint trace sampling audit passed on the sampled endpoints. The source sampling audit failed because sampled source files contain endpoint-looking evidence that is missing from `endpoints.json`.
