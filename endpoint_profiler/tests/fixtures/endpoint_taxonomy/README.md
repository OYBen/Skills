# Endpoint Taxonomy Fixture

This fixture covers endpoint families that were under-extracted in the
`siyu-develop` run:

- `@RabbitListener` should produce `MESSAGE_CONSUMER`.
- commented-out listeners must not produce endpoints.
- `@RabbitMqProducerAnnotation` and `RabbitTemplate.convertAndSend` should
  produce `MESSAGE_PRODUCER`.
- `@XxlJob` should produce `SCHEDULED_JOB`.
- Feign, Retrofit, and `restGet/restPost/...` wrappers should produce
  `HTTP_CALL`.
- Spring Cache annotations should produce `CACHE_KEY`.
- Spring `publishEvent`, `@EventListener`, and `ApplicationListener<T>` should
  produce event bus publisher/listener endpoints.
- `CommandLineRunner` is bootstrap evidence only and should not produce `CLI`
  unless an explicit user-invokable command exists.

Run:

```powershell
python scripts/endpoint_profiler.py tests/fixtures/endpoint_taxonomy/source --out tests/fixtures/endpoint_taxonomy/out
python scripts/verify_endpoint_profiler.py tests/fixtures/endpoint_taxonomy/out
```
