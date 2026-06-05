# MESSAGE_CONSUMER Rules

## Purpose

`MESSAGE_CONSUMER` is an ingress endpoint where the service consumes messages
from an external broker or integration queue/topic.

## Evidence

- `@RabbitListener`, Kafka listener annotations, JMS listener annotations, or
  equivalent consumer bindings.
- Spring Cloud Stream consumer bindings:
  - `@Input(CHANNEL)` methods on binding interfaces define inbound semantic
    channels.
  - `@StreamListener(value = Binding.CHANNEL)` handler methods are ingress
    message consumers and should resolve the channel constant when visible.
- Project-specific consumer annotations that bind a handler to a queue, topic,
  routing key, or exchange.
- Consumer configuration paired with a handler method or class.
- Kafka `consumer.subscribe(topicVariable)` where the variable or collection is
  built from `System.getProperty(...)` or Java string concatenation.

## Identifier

- Prefer the resolved queue or topic name.
- For dynamic Kafka topics, keep the stable template as the identifier, for
  example `calc.service.scheduler.jobEvent.topic.{tenantId}.{group}`.
- If both exchange and routing key define the contract, use
  `exchange:routingKey`.
- Keep unresolved configuration references as `{config.key}` when the runtime
  value is unavailable.
- For Spring Cloud Stream, use the binding/channel constant value such as
  `LOYALTY_EVENT_CHANNEL_INPUT`, not the Java method name or broker host.
- If `spring.cloud.stream.bindings.<binding>.destination` is visible in
  production configuration, prefer the destination value over the binding name.
  Preserve unresolved placeholders such as `{system.environment}`.

## Exclusions

- Broker hosts, cluster names, connection factory names, and container factory
  names are infrastructure, not endpoint identifiers.
- Test consumers and sample queues are out of scope.
