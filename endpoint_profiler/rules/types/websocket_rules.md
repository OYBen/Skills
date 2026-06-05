# WebSocket Rules

## Purpose

`WebSocket` is an ingress endpoint for a WebSocket route, STOMP destination, or
semantic bidirectional channel exposed by the service.

## Evidence

- Explicit WebSocket route registration.
- STOMP endpoint declarations and message mapping annotations.
- Framework metadata that exposes a concrete channel or route.

## Identifier

- Use the route or channel template, for example `/ws/member` or
  `MESSAGE /topic/order`.
- Include the semantic channel name when route-only evidence is too generic.

## Exclusions

- WebSocket configuration infrastructure, interceptors, serializers, and
  session handlers are not endpoints by themselves.
- Do not emit generic client or server implementation class names.
