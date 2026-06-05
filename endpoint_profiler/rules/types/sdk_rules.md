# SDK Rules

## Purpose

`SDK` is an egress endpoint for an external or internal SDK operation when the
underlying concrete HTTP/RPC/message/file contract cannot be resolved from
available source. It should describe the semantic external operation.

## Evidence

- Calls into dependency modules or imported packages that represent external
  systems.
- SDK wrapper methods with operation objects, method names, or request DTOs
  that describe the remote action.
- Dependency-only APIs where source, jar, or class files are unavailable but
  import and call-site arguments reveal the contract.

## Identifier

- Prefer `Provider.Operation` or `Provider.RequestObject` when no lower-level
  endpoint can be resolved.
- Include meaningful operation objects or call arguments, for example
  `CDP.CdpQueryOccIdsByMemberIdsRequest`.
- If a concrete HTTP/RPC/message/file endpoint is resolved, emit that specific
  kind instead of `SDK`.

## Exclusions

- Do not emit bare client names such as `OkHttpClient`, `OSSClient`,
  `AdminBizClient`, or `ExecutorBizClient`.
- Constructor calls are not SDK endpoints unless the constructor itself performs
  an external operation.
