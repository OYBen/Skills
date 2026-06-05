# v20260604 Project Kafka Wrapper Consumers

Endpoint profiler now recognizes project Kafka wrapper contracts:

- `KafkaConsumeService(...).consume(...)`
- `KafkaConsumeService(...).batchConsume(...)`
- `KafkaProduceService.produce(...)`
- `KafkaProduceService.produceAsync(...)`

The scanner resolves topics from local variables, Java concatenation templates,
collection wrappers, map values, map keys, and simple `key.contains(CONST)`
branch filters. Stable runtime templates remain in `identifier`, for example
`{tenantId}.cdp.qw.tag`.
