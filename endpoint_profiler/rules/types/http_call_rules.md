# HTTP_CALL Rules

## Purpose

`HTTP_CALL` is an egress endpoint where the service calls another system over
HTTP. It should describe the remote API operation, not the HTTP client class.

## Evidence

- Feign or Retrofit client method mappings.
- Feign clients may use JAX-RS annotations instead of Spring mapping
  annotations. Treat `@FeignClient` plus class-level `@Path` plus method-level
  `@Path` and `@GET`/`@POST`/`@PUT`/`@DELETE` as outbound HTTP contracts.
- Project Retrofit wrappers such as `@RetrofitService("service", "version")`
  plus `retrofit2.http.@GET/@POST/...` are outbound HTTP contracts.
- `RestTemplate`, `WebClient`, OkHttp, Apache HttpClient, or project wrapper
  calls with recoverable method and path.
- SDK wrapper methods whose implementation resolves to HTTP calls.

## Identifier

- Prefer `METHOD /path` when the base service is known by code context.
- For configuration base URL plus static path, use `METHOD {configKey}/path`.
- For logical service annotations where the runtime URL is resolved by service
  discovery, use the service key as the unresolved base, for example
  `POST /{risk-control}/v1/api/checklist/checkExist4Cache`, and record the
  logical service in `match_rule.target_service`.
- If the path comes from a named constant, resolve the constant value.
- If only a configuration value is visible and no path can be found, use
  `METHOD {configKey}` and mark `metadata.resolved=false`.
- Include semantic operation names or request DTO names in metadata, not as a
  substitute for a resolvable path.

## Exclusions

- Do not emit bare client classes such as `OkHttpClient`, `FeignClient`, or
  `RestTemplate`.
- Do not classify inbound controller mappings as HTTP calls.
- Do not use query strings in `identifier`; store query evidence separately.
