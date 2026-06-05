# Verifier Patterns for CoEvoSkills

Use this reference when designing surrogate verifier tests or verifier prompts.

## Minimal Verifier Prompt Skeleton

```text
You are an independent Surrogate Verifier.

You may read:
- task instruction
- public input files and public docs
- current output artifacts
- your previous verifier script, if any

You must not use:
- hidden tests
- hidden expected answers
- the Skill Generator's private reasoning
- task-instance constants not derivable from public inputs

Your job:
1. Derive deterministic checks from visible evidence.
2. Run or describe assertions against current artifacts.
3. Return per-assertion pass/fail.
4. For failures, give root cause and actionable Skill revisions.
5. If prior surrogate tests passed but oracle failed, escalate coverage without guessing hidden tests.
```

## Assertion Categories

**Presence and structure**

- Required files exist.
- File names match the instruction exactly.
- Output directories are correct.
- Artifacts are non-empty and parseable.
- Required columns, fields, sheets, slides, or sections exist.

**Format and type**

- JSON/YAML/CSV/XLSX/PDF/image parses cleanly.
- Numeric fields are numeric, not strings.
- Dates, units, encodings, and precision match the instruction.
- Sorting, naming, and casing follow the spec.

**Instruction constraints**

- All requested items are included.
- No forbidden items are included.
- Required thresholds, filters, or categories are applied.
- All sub-tasks have corresponding outputs.

**Input-derived invariants**

- Counts reconcile with source data.
- Totals, percentages, balances, or conservation constraints hold.
- IDs remain unique and stable.
- Every output row traces back to a valid input row.

**Independent recomputation**

- Recompute key metrics from public inputs.
- Use a simpler baseline implementation for sanity checking.
- Compare against an alternate library or algorithm when feasible.
- Check tolerances explicitly and justify them from the task.

**Metamorphic tests**

- Re-running the script is idempotent.
- Changing row order does not change aggregate results.
- Unit conversions preserve values.
- Round-trip parse/write/parse preserves required fields.

**Clean-environment tests**

- Run the main script from a clean working directory.
- Ensure relative paths resolve correctly.
- Check that required dependencies are declared or handled.
- Confirm no local absolute paths or private files are required.

## Diagnostic Format

```text
Test: short_name
Status: PASS | FAIL
Evidence: observed value or artifact path
Expected: visible requirement or derived value
Root cause: why the Skill or script likely failed
Revision: concrete change to SKILL.md, script, or resource
```

## Test Escalation After Oracle Failure

If all surrogate tests pass but oracle fails:

1. Keep hidden details hidden.
2. Re-read the instruction for exactness words: "exact", "all", "must", "precision", "valid", "canonical", "schema", "round", "unit".
3. Add checks for overlooked output components.
4. Validate intermediate outputs.
5. Add stricter tolerance or formatting checks only if justified by visible text.
6. Add cross-validation with an independent method.
7. Add alias, duplicate, boundary, and negative tests.
8. Preserve all old tests as regressions unless they were invalid.

## Example: Scientific Numeric Output

Visible task: detect a period from public lightcurve data and output a value with fixed decimal precision.

Verifier sources:

- Instruction says the output must be one period value with a specific precision.
- Public lightcurve data can be analyzed independently.
- Public domain knowledge suggests alias risks such as `P/2` and `2P`.

Possible surrogate tests:

- Output file exists and contains exactly one parseable float.
- Decimal precision matches the instruction.
- Period is within physically plausible bounds derived from the time span.
- Independent baseline periodogram finds a nearby candidate within a declared tolerance.
- Alias checks compare `P`, `P/2`, and `2P`.
- Re-run from clean environment produces the same value.

Residual risk:

- The surrogate's baseline algorithm may be less precise than the final method.
- Hidden oracle may require a tolerance stricter than visible docs imply.
- A more realistic model may be correct even when the surrogate baseline disagrees.

## Example: Data Transformation Output

Visible task: transform an input table and produce a normalized CSV.

Possible surrogate tests:

- Required columns exist in exact order.
- Row count equals the number of valid input records after visible filters.
- Primary key uniqueness holds.
- Numeric columns sum to recomputed totals.
- Invalid rows from public inputs are excluded for visible reasons.
- Output is stable across repeated runs.
- No hardcoded source filenames beyond those specified by the task.

## Example: Skill Package Audit

Use these checks when the artifact is a Skill itself:

- `SKILL.md` has valid YAML frontmatter with `name` and `description`.
- Description clearly states trigger conditions.
- The body contains a concise workflow, not a task-specific solution.
- Scripts are referenced from `SKILL.md` and have stable command examples.
- References are linked only when needed.
- No hidden answer, benchmark-specific constant, or local absolute path is embedded.
- A fresh agent could load the Skill and know when and how to use it.
