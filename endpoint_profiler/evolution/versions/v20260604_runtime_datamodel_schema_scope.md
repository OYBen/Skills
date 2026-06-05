# v20260604 Runtime Data Model Schema Scope

`DATA_MODEL_SCHEMA` now represents runtime or non-static schema contracts, not
static install/upgrade model inventory. Static migration/init model JSON is
treated as setup evidence and no longer emitted as a business endpoint by
default, while `physicalMeta.tables` in those files remains valid `DB_TABLE`
evidence.

The scanner also resolves nested `String.format("data...%s...")` expressions
to full normalized datamodel FQN templates and filters shorter prefixes from
the same expression.

