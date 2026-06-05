# Contrast Analysis R1

## Failure Pattern

- Previous skill text said Graphify was primary "when it exists".
- When no graph index existed, runs could go straight to source scanning and produce a graph skip audit.
- The bundled scanner recorded `graphify_used=false` but had no executable preflight to generate a graph.

## Success Pattern

- The skill now requires Graphify generation when no usable graph exists, unless explicitly disabled or blocked by scope/install issues.
- `scripts/ensure_graphify_index.py` locates existing graph indexes or runs Graphify.
- `scripts/endpoint_profiler.py --ensure-graphify` invokes the preflight.
- When a graph exists, the scanner reads graph nodes first, extracts endpoint-looking source candidates, scans those candidate files first, then falls back to the rest of source.
