# Contrast Analysis

Previous behavior:

- The required reports were framed as trace audits.
- This encouraged judging whether paths could be traced, while the user clarified that both audits are quality gates for `endpoints.json`.
- The old reports could understate extraction gaps because a trace-oriented result does not necessarily compare sampled source evidence against the endpoint inventory.

Required behavior:

- Source sample first: sample 10% by layer, derive expected endpoint kinds from source evidence, and compare with `endpoints.json`.
- Endpoint sample second: sample extracted endpoints, validate sampled and reached endpoint evidence against `endpoints.json`.
- Use Graphify as a cost-saving evidence index, but fall back to source code whenever graph evidence is insufficient.

Patch decision:

- Add a dedicated quality audit generator rather than stretching the older trace helper.
- Update reference docs and `SKILL.md` so future runs preserve the user's corrected definitions.
- Update the verifier to require explicit audit markers and fail on `Audit Verdict: FAIL`.
