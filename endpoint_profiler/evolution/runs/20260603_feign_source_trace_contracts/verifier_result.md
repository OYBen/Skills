# Verifier Result

- Input: `D:/kylin_product_repo/MA/marketing-automation-develop-profile-out`
- Result: PASS

## Observed Endpoint Distribution

- `HTTP_API`: 680
- `HTTP_CALL`: 294
- `DB_TABLE`: 137
- `SCHEDULED_JOB`: 59
- `DATAMODEL`: 16
- Other integration kinds: present as before.

## Source Audit Row Status Distribution

- `TERMINAL_NO_INGRESS`: 24
- `TERMINAL_NO_EGRESS`: 17
- `TRACE_TO_INGRESS`: 10
- `TRACE_TO_EGRESS`: 6
- `MISSING_ENDPOINT_IN_JSON`: 9
- `NEEDS_SOURCE_EXPANSION`: 0

## Remaining Extraction Targets

- Java `*.FQN` datamodel constants used in YAQL/SQL strings.
- SQL field names incorrectly classified as DB table identifiers.
- Cache invalidation operations such as Caffeine `invalidateAll()` where cache region evidence is visible but not emitted as a `CACHE_KEY`.
