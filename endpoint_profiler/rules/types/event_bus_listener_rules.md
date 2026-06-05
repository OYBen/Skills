# EVENT_BUS_LISTENER Rules

## Purpose

`EVENT_BUS_LISTENER` is an ingress endpoint for local or application event bus
contracts, such as Spring application events.

## Evidence

- `@EventListener` methods.
- `ApplicationListener<EventType>` implementations.
- Framework event subscription declarations with an explicit event type.

## Identifier

- Use the event class or semantic event name.
- Prefer fully qualified event type when multiple services define same simple
  name.
- For Spring/Kotlin listeners such as `@EventListener(ApplicationReadyEvent::class)`,
  use the `::class` event type (`ApplicationReadyEvent`), not a generic label
  like `spring-event-listener`.
- For Java listeners such as `@EventListener(SomeEvent.class)`, use
  `SomeEvent`.
- If the annotation does not name a class, derive the event type from the
  listener method parameter, including Kotlin `fun handle(event: SomeEvent)`.
- If no event type can be derived, use `NearestEnclosingType.methodName` as a
  low-confidence fallback and record the unresolved evidence in metadata.

## Exclusions

- Brokered messages are `MESSAGE_CONSUMER`, not local event bus listeners.
- Lifecycle hooks such as startup/shutdown events are only endpoints when they
  represent a business integration contract.
- Do not emit `spring-event-listener` as an identifier; it is a framework
  family, not a contract.
