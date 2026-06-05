# v20260604 Capability-Driven Audit and Shuyun Dependency Clues

Endpoint profiler now treats capability preflight as an active audit driver:
each framework/dependency hint carries a targeted scan plan, confirmed endpoint
samples, and a rule-gap warning when no concrete endpoint is confirmed.

Notable behavior:

- Stable SaaS dynamic templates are valid endpoint identifiers when they name a
  real runtime contract family. Raw expressions stay in `match_rule`.
- Kafka capability clues now include direct client APIs and dynamic topic
  templates, not just annotations or `KafkaTemplate`.
- Shuyun EventService is a first-class capability hint for runtime
  `EVENT_BUS_PUBLISHER` / `EVENT_BUS_LISTENER` scans.
- Shuyun DataAPI is a first-class capability hint for `DATA_API_CALL`,
  `DATA_API_STREAM`, and `ANALYTICS_MODEL_QUERY` scans.
- Generated quality audits include a `Capability-Driven Audit` table.
- Verifier requires capability scan plans and confirmed samples.
