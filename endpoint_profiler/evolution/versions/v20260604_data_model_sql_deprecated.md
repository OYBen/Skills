# v20260604 DATA_MODEL_SQL Deprecated

`DATA_MODEL_SQL` is no longer emitted for new endpoint profiles. SQL over a
`data.*` model FQN is represented as query-language evidence on
`DATA_API_CALL` or `DATA_API_STREAM`, while analytical SQL paths remain
`ANALYTICS_MODEL_QUERY`.

