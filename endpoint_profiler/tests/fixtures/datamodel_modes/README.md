# Datamodel Modes Fixture

This fixture covers semantic data-model access modes beyond plain `DATAMODEL`:

- SQL over `data.*` models should emit `DATA_MODEL_SQL`.
- OLAP/bitmap/streaming SQL should emit `ANALYTICS_MODEL_QUERY`.
- Migration JSON should emit `DATA_MODEL_SCHEMA`.
- `event.*` metadata and publish calls should emit data-event endpoint kinds.
- `data.redis.*` configuration keys must not be emitted as datamodels.
