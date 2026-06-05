# endpoint_profiler v20260603_config_base_url_http_call

## Summary

Evolved HTTP_CALL extraction for configuration base URL plus static path
contracts.

## Changed Files

- `scripts/endpoint_profiler.py`
- `scripts/verify_endpoint_profiler.py`
- `tests/fixtures/endpoint_taxonomy/source/src/main/java/com/example/ConfigBaseUrlClient.java`
- `tests/fixtures/endpoint_taxonomy/out/endpoints.json`
- `tests/fixtures/endpoint_taxonomy/out/endpoints_result.html`

## SkillEvolver/metaSkill Elements

- Understand:
  - `configKey` is parametric and must be preserved as `{owner.property}`.
  - Static operation path is recoverable from Java constants.
- Trace:
  - Real siyu output exposed base-only HTTP_CALL identifiers.
- Contrast:
  - Fixture constants were simple; real constants were nested and sometimes
    leaf-ambiguous.
- Surgical patch:
  - Added getter-argument parsing and qualified constant fallback without
    rewriting extractor architecture.
- Verifier:
  - Added regression expectations for synthetic and public-source cases.

## Verification

- Python compile: PASS.
- `endpoint_taxonomy` fixture verifier: PASS.
- Full siyu-develop verifier: PASS.

## Residual Risk

- Further evolution may be needed for `getApiUrl(CONST + runtimeValue)` and
  `String.format(getApiUrl(CONST), ...)` path-template normalization.
