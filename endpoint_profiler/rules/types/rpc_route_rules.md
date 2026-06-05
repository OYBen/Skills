# RPC_ROUTE Rules

## Purpose

`RPC_ROUTE` is an ingress endpoint exposed through RPC-style protocols such as
gRPC, Dubbo, Thrift, RMI, or framework-specific service contracts.

## Evidence

- Service implementation annotations or declarations that register an RPC
  service.
- Protobuf or IDL service definitions paired with runtime service ownership.
- Framework metadata that binds a service method to an externally callable RPC
  route.

## Identifier

- Prefer `ServiceName.methodName`.
- For gRPC, use `package.Service/method` when the fully qualified service name
  is available.
- Keep transport addresses, registries, and provider names out of
  `identifier`; store those in metadata when useful.

## Exclusions

- Plain Java interface implementations are not RPC routes without framework
  exposure evidence.
- Outbound RPC stubs are `RPC_CALL`.
- Do not use service registry names as endpoint identifiers.
