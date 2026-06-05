# HTTP_API Rules

## Purpose

`HTTP_API` is an ingress endpoint exposed by the analyzed service over HTTP.
It represents the externally callable API contract, not an internal helper
method or outbound client interface.

## Evidence

- Spring MVC controller mappings: `@RestController`, `@Controller`,
  `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`,
  `@DeleteMapping`, `@PatchMapping`.
- Other framework route declarations with an explicit HTTP method and route
  template.
- OpenAPI or route metadata when paired with service ownership evidence.

## Identifier

- Use `METHOD /full/path`.
- Combine class-level path prefixes with method-level mappings.
- Normalize duplicate slashes and ensure the path starts with `/`.
- Do not include query strings in `identifier`; place query parameter evidence
  in `match_rule.query_params`.

## Exclusions

- Feign, Retrofit, or SDK client mapping annotations are `HTTP_CALL`, not
  `HTTP_API`.
- Do not emit class-level `@RequestMapping` alone as an endpoint unless it
  declares a concrete handler method.
- Exclude tests, examples, generated docs, and mock controllers outside runtime
  scope.
