# Version: v20260603_graphify_preflight_first

## Goal

Make endpoint profiling Graphify-first even when a project does not already have `graphify-out`.

## Skill Changes

- `SKILL.md`
  - Requires `/graphify <input_dir> --no-viz` or bundled preflight before broad source scanning.
  - Makes `python scripts/endpoint_profiler.py <input_dir> --ensure-graphify --out <output_dir>` the first-pass scanner command.
  - Clarifies that source scanning is fallback/confirmation after graph candidate selection.
- `scripts/ensure_graphify_index.py`
  - Locates existing graph indexes.
  - Runs Graphify when no usable graph exists.
  - Prints the resolved `graph.json` path for scanner use.
- `scripts/endpoint_profiler.py`
  - Adds `--ensure-graphify` and `--graphify-mode`.
  - Reads graph nodes before source scanning.
  - Extracts endpoint-looking source candidates from graph node metadata/properties/path evidence.
  - Scans graph candidate files first, then scans remaining files as fallback coverage.
  - Records `audit.graphify_summary` and `graphify-candidate-scan` mode.
- `references/verifier.md`
  - Documents Graphify preflight as part of verification expectations.

## Validation

- Syntax check: PASS.
- Existing MA profiler output verifier: PASS.

## Residual Risk

Graphify can be incomplete or blocked by scope selection; in those cases endpoint profiler should record the fallback reason and continue with source confirmation only after the Graphify step has been attempted.
