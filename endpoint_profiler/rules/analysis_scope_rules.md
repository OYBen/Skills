# Analysis Scope Rules

These rules define which files and directories belong to the endpoint analysis
scope. The goal is to extract runtime endpoint contracts, not every endpoint-like
string in a repository.

Use these rules together with `rules/graphify_index_workflow.md`: start from
Graphify candidate nodes, then decide whether each node is in scope before
reading source evidence and emitting endpoints.

## Core Principle

The analysis scope is the production runtime and dependency closure of each
discovered microservice.

A file or directory is in scope only when it can carry one of these forms of
evidence:

- runtime service boundary evidence
- ingress endpoint contract evidence
- egress endpoint contract evidence
- configuration or metadata used by runtime endpoint behavior
- production dependency code used by a runtime service
- machine-readable API or integration contract

Do not treat all repository files as equal source evidence.

## Always Exclude

Exclude these by default, even if they contain endpoint-looking strings:

```text
src/test/**
test/**
tests/**
__tests__/**
*Test.java
*Tests.java
*_test.py
*.spec.ts
*.test.ts
*.spec.js
*.test.js
coverage/**
```

Reason: tests commonly contain expected SQL, mock URLs, fake topics, sample file
names, and assertion text. These are not runtime system contracts.

Also exclude generated or local-only artifacts:

```text
target/**
build/**
dist/**
out/**
node_modules/**
.git/**
.idea/**
.vscode/**
logs/**
log/**
trace/**
tmp/**
temp/**
cache/**
```

## Production Runtime Code

Include production runtime code when it is inside a microservice runtime module
or its dependency closure:

```text
src/main/**
app/**
apps/**
service/**
services/**
server/**
worker/**
consumer/**
job/**
scheduler/**
controller/**
handler/**
router/**
mapper/**
repository/**
dao/**
client/**
sdk/**
```

Typical evidence:

- Spring Boot or equivalent application bootstrap
- controllers, routers, handlers
- message listeners and producers
- scheduled jobs and workers
- mappers, repositories, DAOs
- HTTP/RPC/data clients
- SDK usage

## Production Resource and Config Files

Include runtime resource/config directories when they are part of a service
runtime module or dependency closure:

```text
src/main/resources/**
resources/**
config/**
conf/**
META-INF/scripts/**/model/**
META-INF/scripts/**/tenant/**/model/**
META-INF/scripts/**/guidepackage/**/model/**
resources/mapper/**
```

Allowed endpoint evidence:

- `application.yml`, `application.yaml`, `application.properties`,
  `bootstrap.yml`, `bootstrap.yaml`, `bootstrap.properties` for service identity,
  runtime config, topics, cache regions, cron expressions, and integration
  settings.
- Mapper XML files for `DB_TABLE` evidence.
- Model metadata JSON for `DB_TABLE` and `DATAMODEL` evidence.
- AsyncAPI/OpenAPI/protobuf/GraphQL specs when they are machine-readable
  contracts.

Important distinction:

- A mapper XML file may provide `DB_TABLE` evidence.
- A model JSON file may provide `DB_TABLE` or `DATAMODEL` evidence.
- The file path itself is not a `FILE` endpoint.

## Dependency Closure

Include shared modules only when they are in the discovered microservice's
dependency closure.

Examples:

```text
core/**
common/**
shared/**
domain/**
infra/**
data-client/**
service-client/**
sdk/**
```

These modules are not microservices by themselves unless they have runtime
bootstrap evidence. Their endpoints should be attributed to the owning runtime
service:

```json
{
  "owner": {
    "service": "checkout-service",
    "service_scope": "dependency"
  }
}
```

Do not analyze unrelated sibling modules merely because they are under the same
repository root.

## Interface Contract Directories

Include machine-readable contract directories:

```text
openapi/**
swagger/**
api/**
proto/**
graphql/**
asyncapi/**
idl/**
```

These may define ingress or egress contracts even when they are not under
`src/main`. Prefer structured parsing over natural-language interpretation.

## Deployment and Operations Directories

Include these directories only as supporting evidence:

```text
docker/**
k8s/**
kubernetes/**
helm/**
deploy/**
deployment/**
ci/**
.github/workflows/**
```

Allowed uses:

- service boundary detection
- application name and runtime command evidence
- environment variable names
- config mount discovery
- port/context-path hints

Not allowed:

- emitting infrastructure hosts as endpoints
- treating Kafka/MySQL/Redis cluster addresses as endpoint identifiers
- treating container, pod, database, or broker names as logical contracts

## Documentation Directories

Exclude natural-language documentation by default:

```text
docs/**
doc/**
design/**
README.md
CHANGELOG.md
```

Exceptions:

- OpenAPI/Swagger files
- AsyncAPI files
- protobuf files
- GraphQL schemas
- other machine-readable contract specs

Natural-language docs may be used as weak supporting context during manual
review, but should not be the sole source for an endpoint.

## Examples, Demos, and Mocks

Exclude by default:

```text
example/**
examples/**
sample/**
samples/**
demo/**
demos/**
mock/**
mocks/**
stub/**
stubs/**
fixture/**
fixtures/**
```

Include only when build/runtime evidence proves the directory is a real runtime
service, not sample code.

## Generated Code

Generated code is conditionally in scope.

Include generated code only when:

- it is compiled or packaged into the runtime service;
- it carries machine-readable contract evidence not present elsewhere;
- or it is the only visible source of a client/server contract.

Otherwise, prefer the source spec that generated it.

Lower confidence for endpoints extracted only from generated code unless the
generation source is unavailable.

## Decision Order

For each Graphify candidate node:

1. Normalize the candidate `source_file` path.
2. Reject it immediately if it matches an always-excluded path.
3. Determine whether it belongs to a discovered service runtime root or a
   dependency `scope_root`.
4. If it is a resource/config/contract file, check whether the endpoint family
   rule allows that file type.
5. Confirm with source/config evidence.
6. Emit the endpoint with `owner.service_scope = "runtime"` or `"dependency"`.
7. If the source is outside all service scopes, emit only when the file is a
   repository-level contract spec or service-boundary artifact and the ownership
   can be justified.

## Audit Expectations

When scope filtering is applied, record useful audit details:

```json
{
  "audit": {
    "scope_rules": "rules/analysis_scope_rules.md",
    "excluded_path_families": ["test", "build", "docs-natural-language"],
    "warnings": []
  }
}
```

Warnings should be used when endpoint-like evidence is skipped because it is
outside the runtime/dependency scope.

