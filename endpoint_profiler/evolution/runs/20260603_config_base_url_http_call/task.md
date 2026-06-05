# Task

Evolve `endpoint_profiler` using `metaSkill`.

## Target

- Source root: `D:\kylin_product_repo\Kylin导购\siyu-develop`
- Graphify index: `D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\graphify-out\graph.json`
- Endpoint output: `D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\endpoints-out`

## Contract

- Preserve the original endpoint profiler skill boundary: extract endpoint
  contracts only, do not write topology edges into `endpoints.json`.
- Use Graphify as the first index when available.
- Keep endpoint identifiers semantic and stable.
- For HTTP calls whose base URL comes from a configuration getter and whose
  operation path is a static path constant, emit `METHOD {configKey}/path`.
- Add verifier/regression coverage for any changed rule.
