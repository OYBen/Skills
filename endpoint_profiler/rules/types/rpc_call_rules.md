# RPC_CALL Rules

## Purpose

`RPC_CALL` is an egress endpoint where the service invokes another system
through RPC-style protocols.

## Evidence

- gRPC stubs and generated service clients.
- Dubbo, Thrift, RMI, or project RPC client calls.
- Source calls to an imported RPC contract when no HTTP implementation is
  present.

## Identifier

- Prefer `ServiceName.methodName`.
- For gRPC, use `package.Service/method` when available.
- If the remote service name is only available through configuration, use
  `{configKey}.methodName`.

## Exclusions

- Plain internal Java method calls are not RPC calls.
- Do not use registry names, hostnames, or dependency artifact names alone as
  endpoint identifiers.
