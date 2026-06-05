# Task

Evolve endpoint_profiler after CDP sampling showed that remaining `DATAMODEL`
records do not fully collapse into `DATA_API_CALL` and `DATA_API_STREAM`.

Required improvements:

- Split SQL-over-datamodel access from direct DataAPI model calls.
- Identify analytical/OLAP/HTAP/bitmap/streaming model query paths.
- Classify model migration/metadata as schema endpoints.
- Classify `event.*` metadata and publish calls separately from datamodels.
- Exclude configuration keys such as `data.redis.ssl.enabled`.
