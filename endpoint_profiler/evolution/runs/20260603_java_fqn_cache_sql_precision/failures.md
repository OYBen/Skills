# Failures and Residual Risks

## Resolved

- Java FQN constants now produce datamodel endpoints.
- SQL lower-camel update-field false positives are filtered.
- Cache invalidation receiver regions are emitted as cache endpoints.

## Residual Risks

- Remaining `MISSING_ENDPOINT_IN_JSON` rows are source-trace findings for deeper service/repository paths and may require broader call graph expansion or additional project-specific data/cache rules.
- Cache receiver names are normalized heuristically from variable names; ambiguous generic names are skipped only for the literal `cache`.
- The scanner still confirms graph candidates with source; Graphify remains an index, not an endpoint source of truth.
