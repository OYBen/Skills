# Contrast Analysis R1

## Failure Pattern

- The previous audit generator created fresh Markdown files but did not trace source chains.
- Rows used `NEEDS_SOURCE_EXPANSION` even when the source method existed and could be classified as terminal or followed through local method calls.
- The verifier accepted the report because it only checked freshness and section markers.

## Success Pattern

- The new audit helper indexes production Java/Kotlin source methods.
- It follows same-class calls, injected collaborator calls, and interface-to-implementation mappings.
- It parses interface method declarations so Feign/client contracts and listener declarations do not become unresolved merely because they lack method bodies.
- The verifier now rejects audits where unresolved statuses dominate the report.

## Root Cause Classification

- Script gap: no reusable source trace audit generator existed.
- Verifier gap: no semantic quality check on trace status distribution.
- Instruction gap: scanner docs did not make the trace helper the default post-processing step.
