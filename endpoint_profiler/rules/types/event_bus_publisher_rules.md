# EVENT_BUS_PUBLISHER Rules

## Purpose

`EVENT_BUS_PUBLISHER` is an egress endpoint where the service publishes a local
or application event bus contract.

## Evidence

- `ApplicationEventPublisher.publishEvent(...)`.
- Framework event publisher abstractions with an explicit event type.
- Project event bus emitters when they carry a semantic event class/name.
- Shuyun EventService / ES event bus publishers such as `EventProducer`,
  `EsFactory.create().createProducer()`, `Event.of(eventFqn, ...)`,
  `publishBatchSync(...)`, `sendEvents(eventFqn, ...)`, or wrapper methods that
  resolve to an `event.*` FQN.

## Identifier

- Use the event class or semantic event name.
- For Shuyun EventService events, use the full `event.*` FQN.
- Prefer fully qualified event type when simple names collide.

## Exclusions

- Brokered messages are `MESSAGE_PRODUCER`.
- Logging, metrics, lifecycle callbacks, and observer notifications are not
  endpoints unless they are business event contracts.
