# MESSAGE_PRODUCER Rules

## Purpose

`MESSAGE_PRODUCER` is an egress endpoint where the service publishes messages
to an external broker queue, topic, exchange, or routing key.

## Evidence

- RabbitTemplate `convertAndSend` and project producer wrappers.
- Kafka producer `send` calls.
- Kafka `ProducerRecord(topic, ...)` calls, including topic variables built by
  `System.getProperty(...)` or Java string concatenation.
- Spring Cloud Stream producer bindings:
  - `@Output(CHANNEL)` methods on binding interfaces define outbound semantic
    channels.
  - Calls such as `kafkaSource.someOutput().send(message)` publish to the
    `@Output` channel behind `someOutput`.
- Messaging annotations or config that bind a producer to a concrete channel.

## Identifier

- Prefer resolved topic or queue name.
- For dynamic Kafka topics, keep the stable template as the identifier, for
  example `calc.service.scheduler.jobEvent.topic.{tenantId}.{client}`.
- If exchange plus routing key defines the contract, use
  `exchange:routingKey`.
- Keep unresolved configuration references as `{config.key}`.
- For Spring Cloud Stream, use the resolved binding/channel constant value such
  as `LOYALTY_HTTP_REQUEST_ASYNC_PROCESS_OUTPUT`, not the method name
  `requestSyncProcessOutput` by itself.
- If `spring.cloud.stream.bindings.<binding>.destination` is visible in
  production configuration, prefer the destination value over the binding name.
  Preserve unresolved placeholders such as `{system.environment}`.

## Exclusions

- Broker infrastructure names are not endpoint identifiers.
- Local application events are `EVENT_BUS_PUBLISHER`, not message producers.
