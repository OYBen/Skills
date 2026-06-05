# Failures and Residual Risks

## Resolved

- Placeholder audit reports with mostly `NEEDS_SOURCE_EXPANSION` now fail verification.
- Source trace audit generation now follows bounded Java/Kotlin local call chains.
- Interface-to-implementation dispatch and interface method declarations are handled.

## Residual Risks

- The helper is not a full Java compiler and may miss dynamic dispatch, lambda-heavy chains, reflection, framework-generated wiring, or calls hidden behind generic utilities.
- Terminal statuses mean no profiled opposite-side endpoint was reached in the bounded local graph; they are audit classifications, not topology edges.
- Future targets with non-Java stacks may need additional parser branches before the 30% unresolved threshold is appropriate.
