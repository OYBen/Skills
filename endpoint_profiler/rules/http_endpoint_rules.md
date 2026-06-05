# HTTP Endpoint Rules

These rules define `HTTP_API` endpoint identifiers.

## Identifier Contract

For ingress HTTP APIs, `identifier` must be:

```text
METHOD /full/path
```

Examples:

- `POST /cem/event`
- `GET /api/orders/{id}`

Do not emit method-local fragments such as `POST event`, and do not emit
controller-level prefixes such as `ANY cem` as standalone APIs.

## Spring MVC Rules

For Spring controllers:

1. Class-level `@RequestMapping` is a path prefix, not an endpoint by itself.
2. Method-level mappings define the HTTP endpoint.
3. Combine class-level and method-level paths.
4. Normalize the full path to begin with `/`.
5. If class-level `@RequestMapping` has multiple prefixes, emit one endpoint
   per prefix. Do not collapse the method path into a fragment such as
   `GET /tree`.

Example:

```java
@RestController
@RequestMapping("cem")
public class CemController {
    @PostMapping("event")
    public ApiResult<String> event(@RequestBody String request) { ... }
}
```

Correct endpoint:

```text
POST /cem/event
```

For multi-prefix controllers:

```java
@RequestMapping({"/material-app/material/category", "/guide-app/material/category"})
class AppMaterialCategoryController {
    @GetMapping("tree")
    MaterialCategoryTree tree() { ... }
}
```

Correct endpoints:

```text
GET /material-app/material/category/tree
GET /guide-app/material/category/tree
```

Incorrect endpoints:

```text
ANY cem
POST event
```

## Server Context Path

If a runtime `server.servlet.context-path` is available and clearly applies to
the service, put it in `match_rule.context_path` and include it in the normalized
full path only when the project convention treats it as part of the externally
visible API contract.

When uncertain, prefer the controller full path and preserve service ownership
through `owner.service`.
