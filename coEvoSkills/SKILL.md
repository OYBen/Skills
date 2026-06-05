---
name: coevoskills
description: >-
  Use this skill when creating, evaluating, or improving agent skills with a CoEvoSkills-style loop where an independent skill generator and surrogate verifier co-evolve a reusable skill package through deterministic proxy tests, structured failure diagnostics, opaque oracle feedback, and verifier test escalation. Especially useful for building multi-file Skills, auditing generated Skills, turning task instructions and public inputs into verifier tests, or diagnosing when a skill passes local checks but fails hidden evaluation.
trigger: /coevoskills
---
# CoEvoSkills

Use this skill to evolve agent Skills through verification-driven iteration. The core idea is simple: do not trust one-shot skill generation. Pair a Skill Generator with an information-isolated Surrogate Verifier, let the verifier produce deterministic proxy tests and actionable diagnostics, and use any hidden/oracle feedback only as an opaque signal that triggers verifier escalation.

## When to Use

Use this workflow when the user wants to:

- Create a new reusable agent Skill for a task family.
- Improve an existing Skill using failures from execution.
- Design a verifier for a generated Skill without leaking hidden answers.
- Build a multi-file Skill package with `SKILL.md`, scripts, references, templates, or examples.
- Compare self-generated, human-curated, and verifier-evolved Skills.
- Explain or implement a CoEvoSkills-style generation path.

Do not use this workflow when a task is one-off, subjective, or cannot produce inspectable artifacts or testable properties.

## Roles

Maintain separation between the two roles even if one agent performs both roles sequentially.

**Skill Generator**

- Reads the task instruction, public input files, available docs, and existing Skill if any.
- Creates or revises the Skill package.
- Executes the task using the Skill.
- Receives verifier diagnostics, but never hidden test content.

**Surrogate Verifier**

- Reads only the task instruction, public inputs if needed, current outputs/artifacts, and its own previous tests.
- Does not read the generator's private reasoning or hidden oracle tests.
- Generates deterministic assertions, runs them, and returns per-test failures, root cause analysis, and revision suggestions.
- Escalates tests when proxy tests pass but an external oracle still fails.

**Oracle**

- Optional but valuable.
- Runs in a fresh environment.
- Returns only pass/fail or a coarse score unless the user explicitly allows detailed feedback.
- Never exposes hidden expected outputs to the generator.

## Workflow

1. **Define the task contract**
   - Extract required output files, schemas, formats, precision, units, constraints, and edge cases from the instruction and public docs.
   - Record what is visible, what is hidden, and what must not be inferred from hidden tests.

2. **Generate an initial Skill**
   - Write a focused `SKILL.md` with when-to-use guidance and the minimal procedure.
   - Add scripts only for deterministic, repeated, or error-prone operations.
   - Keep task-instance constants out of the Skill.

3. **Execute with the Skill**
   - Use the Skill as a real dependency, not as background prose.
   - Produce the expected artifacts.
   - Keep logs of commands, outputs, and failures.

4. **Build surrogate tests**
   - Derive expected properties from the task instruction, public docs, public inputs, and independent computation.
   - Prefer deterministic assertions over qualitative judgment.
   - Test file presence, schema, parseability, units, ranges, invariants, round trips, boundary cases, and cross-checks.

5. **Diagnose failures**
   - For each failed assertion, report:
     - assertion name
     - observed value
     - expected property or derived expected value
     - likely root cause
     - concrete Skill revision

6. **Revise the Skill with tests fixed**
   - Keep the verifier test suite fixed while the generator repairs the Skill.
   - Patch the smallest relevant part of the Skill or script.
   - Re-run the same tests until they pass.

7. **Escalate only on surrogate-pass/oracle-fail**
   - If surrogate tests pass but oracle fails, do not guess hidden tests.
   - Treat the oracle result as: "the current verifier missed something."
   - Add broader, stricter, or more diverse surrogate assertions based on the instruction and current outputs.

8. **Finalize**
   - Select the best Skill version by oracle score if available, otherwise by surrogate pass rate plus generalization risk.
   - Document remaining assumptions and known verifier blind spots inside the Skill only if they affect future use.

## Verifier Test Sources

The Surrogate Verifier's expected values and checks should come from visible evidence only:

- **Instruction-derived**: required filenames, formats, schemas, precision, units, allowed values, ordering, and constraints.
- **Document-derived**: public reference docs, API specs, formula definitions, style guides, or task rubrics.
- **Input-derived**: independent calculations from public input files, data invariants, sanity ranges, conservation laws, schema validation, or reproducible algorithms.
- **Metamorphic**: properties that should remain true under transformations, such as sorting, unit conversion, round-trip parsing, duplicate removal, or idempotent re-runs.
- **Cross-check**: compare two independent implementations or algorithms when no single exact answer is available.
- **Regression**: preserve tests for bugs caught in earlier rounds.

Never derive expected values from hidden answer files, hidden test code, generator private notes, or an output file that may simply encode the generator's mistake.

## Escalation Patterns

When proxy tests pass but the oracle fails, strengthen the verifier along one or more axes:

- Add boundary cases from the instruction.
- Tighten precision, formatting, and type checks when the task mentions exactness.
- Add independent algorithmic cross-validation.
- Add negative tests for aliases, duplicates, missing rows, wrong units, or off-by-one errors.
- Validate intermediate artifacts, not only final output.
- Add regression tests for previous fixes.
- Check that scripts are called through the Skill and can run from a clean environment.

## Failure Modes

Watch for these common problems:

- The verifier tests only formatting and misses semantic correctness.
- The verifier's independent calculation is less accurate than the generator's output.
- The generator overfits to surrogate tests.
- The Skill hardcodes task-instance constants.
- Scripts work only in the author's environment.
- The Skill is valid but not surfaced where the consuming agent will load it.
- The verifier inherits the generator's assumptions because isolation was broken.

## Output Pattern

When reporting a CoEvoSkills run, use this compact structure:

```text
Skill version: vN
Surrogate tests: passed/total
Oracle result: pass/fail or score, if available
Main verifier failures:
- test_name: root cause -> revision
Test escalation:
- new assertion or stricter check
Skill changes:
- changed guidance/script/resource
Residual risk:
- what the surrogate verifier may still miss
```

## Optional Reference

For concrete verifier templates, test categories, and prompt skeletons, read `references/verifier-patterns.md`.
