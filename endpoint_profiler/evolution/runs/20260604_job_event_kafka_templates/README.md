# Job Event Kafka Templates

## Problem

CDP calc scheduler uses `JobEventService` as an outbox/persistence layer for
job status events. The actual cross-process contract is Kafka:

- `JobEventScheduler` publishes `JobEventBean` to
  `calc.service.scheduler.jobEvent.topic.{tenantId}.{client}` through
  `new ProducerRecord<>(topic, value)`.
- `CalcJobTask` / `JobCalculatorHttpClient` subscribe to
  `calc.service.scheduler.jobEvent.topic.{tenantId}.{group}` through
  `consumer.subscribe(topics)`.

The previous scanner only recognized literal Kafka topics or simpler send
calls, so this dynamic topic chain was missing.

## Evolution

- Added Java topic-template extraction for concatenated topic expressions.
- Resolve `System.getProperty(topicVar, topicVar)` back to the topic template.
- Track local topic variables and topic collections such as `topics.add(...)`.
- Detect Kafka `consumer.subscribe(topicVariable)` as `MESSAGE_CONSUMER`.
- Detect Kafka `new ProducerRecord<>(topicVariable, ...)` as
  `MESSAGE_PRODUCER`.
- Added regression checks for CDP job event producer and consumer templates.

## Validation

- `python -m py_compile scripts/endpoint_profiler.py scripts/verify_endpoint_profiler.py`
- calc-service focused profile: producer and consumer detected.
- CDP output: `D:\kylin_product_repo\CDP\CDP-profile-out`
- CDP verifier: PASS

CDP message endpoints after this evolution:

```text
MESSAGE_PRODUCER calc.service.scheduler.jobEvent.topic.{tenantId}.{client}
MESSAGE_CONSUMER calc.service.scheduler.jobEvent.topic.{tenantId}.{group}
```

These are Kafka brokered message endpoints, not Shuyun EventService
`EVENT_BUS_*` endpoints.

