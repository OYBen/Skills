# v20260604 Job Event Kafka Templates

The profiler now resolves dynamic Kafka topic templates built from Java string
concatenation and `System.getProperty(...)`, and emits `MESSAGE_PRODUCER` /
`MESSAGE_CONSUMER` for job event Kafka contracts such as
`calc.service.scheduler.jobEvent.topic.{tenantId}.{client}` and
`calc.service.scheduler.jobEvent.topic.{tenantId}.{group}`.

