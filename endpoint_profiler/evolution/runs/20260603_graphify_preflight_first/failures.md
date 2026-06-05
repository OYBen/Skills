# Failures and Residual Risks

## Resolved

- Graphify is no longer optional-by-default in the skill workflow.
- The scanner has an executable Graphify preflight and graph-first candidate scan.

## Residual Risks

- Graphify generation may pause for user scope selection on very large corpora per the Graphify skill rules.
- Graph source-candidate extraction supports common graph node schemas; unusual Graphify schema variants may still require source fallback.
- The scanner still uses source confirmation for endpoint emission. Graph nodes are evidence pointers, not final endpoints.
