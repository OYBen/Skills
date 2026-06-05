# DISTRIBUTED_CACHE Rules

## Purpose

`DISTRIBUTED_CACHE` is an egress endpoint for a cache contract backed by
cross-process cache infrastructure. A Redis key is one concrete implementation.

Process-local memory caches are not endpoint contracts. They are implementation
details inside a service process and must not be emitted as egress endpoints.

## Evidence

Emit `DISTRIBUTED_CACHE` only with explicit distributed-cache evidence:

- Redis operations with stable key prefixes or named key builders.
- `RedisCacheKeyEnum` or equivalent project Redis key enums.
- Redis/Redisson lock keys such as `redisCache.getLock(...)`.
- `StringRedisTemplate`, `RedisTemplate`, Redisson, or a project bean clearly
  named `redisCache`.

## Identifier

- Use the stable Redis key namespace or prefix as the identifier.
- Convert runtime suffixes to template variables, for example
  `mbsp_task_lock_key_{taskEnum}`.
- Store raw templates and backend details in `match_rule`, with
  `match_rule.type = "distributed_cache"` and
  `match_rule.backend = "redis"` when Redis evidence is visible.

## Exclusions

- Do not emit `DISTRIBUTED_CACHE` for `MemoryCacheKeyEnum`, Caffeine,
  Guava Cache, in-process maps, or Spring Cache annotations unless the source
  also proves a distributed backend.
- Redis host, connection factory, template class, serializer, or pool config
  names are infrastructure, not endpoints.
- Do not emit generic helper method names unless they define a stable
  distributed cache contract.
