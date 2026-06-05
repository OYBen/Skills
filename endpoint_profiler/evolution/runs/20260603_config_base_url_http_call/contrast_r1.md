# Contrast Analysis r1

## Success Patterns

- The synthetic fixture passed because constants were unique leaf names and
  could be resolved by the existing root-level constant map.
- The scanner correctly propagated `String url = configGetter(PATH_CONST)` to
  later `responseContentByPost(url, ...)` / `responseContentByGet(url, ...)`
  calls when the path was available.

## Failure Patterns

- Real siyu source contains nested constants:
  `Outer.Inner.CONST`.
- Real siyu source also contains duplicate leaf constant names across constant
  classes, for example `MEMBER_POST_REGISTER_WECHAT`.
- The first patch did not resolve full nested constant expressions. It emitted
  some base-only identifiers such as `POST {kyLinApiConfig.mbspApiUrl}`.

## Skill Gaps

- The extractor needed runtime derivation for qualified nested Java constants,
  not only leaf constants.
- The verifier initially reused fixture expected paths for real source, which
  was too fixture-shaped.

## Patch Targets

- `scripts/endpoint_profiler.py`
  - Add qualified owner-head fallback in `resolve_java_expr(...)`.
- `scripts/verify_endpoint_profiler.py`
  - Separate synthetic fixture expectations from real public-source
    regression expectations.

## Generalization Risk

- Java expressions with string concatenation after `getApiUrl(CONST)`, such as
  `CONST + id`, may still require future endpoint template normalization.
  This was not changed in this iteration.
