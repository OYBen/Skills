# 2026-06-04 Project Kafka Wrapper Consumers

## Trigger

CDP `QwMessageHandler` used `KafkaConsumeService.consume(message -> ...)` to
consume QW tag synchronization messages. The previous Kafka rules recognized
direct Kafka APIs such as `KafkaConsumer.subscribe` and `ProducerRecord`, but
missed project wrapper classes.

## Changes

- Added `KafkaConsumeService(topics, group...)` constructor parsing.
- Added `consume(...)` and `batchConsume(...)` wrapper consumer support.
- Added `KafkaProduceService.produce(...)` and `produceAsync(...)` producer
  support.
- Resolved topic values through `Arrays.asList(...)`, `List.of(...)`,
  `Collections.singleton(...)`, local topic variables, map values, and map keys.
- Preserved stable dynamic templates such as `{tenantId}.cdp.qw.tag`.
- Added branch narrowing for `key.contains(CONST)` / `else` patterns so a
  `map.keySet().forEach(key -> ...)` loop can split multiple topic templates
  accurately.

## CDP Validation

- `MESSAGE_CONSUMER {tenantId}.cdp.qw.tag.group` from
  `QwMessageHandler.java:67`.
- `MESSAGE_CONSUMER {tenantId}.cdp.qw.tag` from `QwMessageHandler.java:85`.
- `MESSAGE_PRODUCER {tenantId}.cdp.qw.tag` from `QwMessageHandler.java:106`.
- `MESSAGE_PRODUCER {tenantId}.cdp.qw.tag.group` from
  `QwMessageHandler.java:111`.
- Wrapper consumers for manual no-value tag/cohort topics were also detected.

## Verification

- CDP endpoint count increased from 819 to 828.
- Message counts: `MESSAGE_CONSUMER:5`, `MESSAGE_PRODUCER:6`.
- Quality audit regenerated.
- Endpoint profiler verifier passed.
