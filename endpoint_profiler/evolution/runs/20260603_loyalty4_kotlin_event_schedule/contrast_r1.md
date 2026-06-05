# Contrast

Before:

- The extractor could scan Kotlin files but used the first type name in the file for scheduled job identifiers.
- Spring `@EventListener` parsing only handled Java-style method parameters, so Kotlin `ApplicationReadyEvent::class` became `spring-event-listener`.
- Graph audit guidance assumed a single complete `graph.json` and did not clearly describe partial root/shard graph coverage.

After:

- `@Scheduled` uses the nearest enclosing Java/Kotlin type around the annotated method.
- `@EventListener(ApplicationReadyEvent::class)` uses `ApplicationReadyEvent` as the event contract.
- Generic `spring-event-listener` is a verifier failure.
- Graph audit can report `GRAPH_INDEX_PARTIAL` when root/shard graphs do not cover sampled endpoint modules.

Remaining limitation:

- `loyalty4` emits no HTTP_CALL/MQ/SDK/FILE endpoints with the current rules. This may be correct for scanned evidence, but deeper review of facade/stream modules and Graphify shards is recommended before treating those families as absent.
- CACHE_KEY `all` from Caffeine remains semantically weak and needs caller expansion to decide whether a richer cache identifier should be derived.
