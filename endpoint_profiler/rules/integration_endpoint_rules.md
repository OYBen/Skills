# Integration Endpoint Rules

These rules define extraction policy for message, HTTP egress, distributed
cache, event, and scheduled integration contracts.

## Capability Hints

Frameworks, scaffolds, and dependency packages are important clues for endpoint
families, but they are not endpoint contracts by themselves.

- A dependency or starter such as Spring MVC, OpenFeign, Spring Cloud Stream,
  Kafka, RabbitMQ, Redisson, MyBatis, JPA, XXL-Job, Shuyun EventService, or
  Shuyun DataAPI should create an audit hint and direct source inspection.
- Each capability hint must include a targeted scan plan, confirming features,
  dependency/source evidence, status, confirmed endpoint counts, and sample
  endpoint source references when confirmed.
- Emit an endpoint only after source/config evidence confirms a concrete
  route, client call, topic, Redis key, scheduled worker, table, data model, or
  equivalent contract.
- If a capability exists but no confirming source/config feature is found,
  record it as `candidate_only` in preflight/audit metadata, add a rule-gap
  warning with the executed scan plan, and do not emit an endpoint.

## Message Consumers

Emit `MESSAGE_CONSUMER` for runtime message listener contracts:

- Spring Rabbit `@RabbitListener(queues = ...)`
- Kafka/JMS listener annotations when a topic or queue is visible
- project Kafka wrapper consumers such as `KafkaConsumeService(topics, group)`
  followed by `consume(...)` or `batchConsume(...)`
- task queue decorators in non-Java stacks

Identifier:

- Use the resolved queue or topic name when a string constant is visible.
- If a topic is assembled from a stable prefix plus runtime dimensions, preserve
  it as a clean dynamic template such as
  `calc.service.scheduler.jobEvent.topic.{tenantId}.{group}`.
- Resolve topic maps used by wrapper consumers, for example
  `topicMapping.put(tenantId, tenantId + TOPIC_NAME)` plus
  `KafkaConsumeService(Arrays.asList(topicMapping.get(tenantId)), GROUP)`.
- When a `map.keySet().forEach(key -> ...)` loop branches on
  `key.contains(SOME_TOPIC_CONST)`, use that branch condition to narrow which
  topic template belongs to each `consume(...)` call.
- If a constant cannot be resolved, use the clean semantic constant path without
  regex or wildcard syntax.

Do not emit from commented-out annotations, tests, docs, or examples.

## Message Producers

Emit `MESSAGE_PRODUCER` for explicit outbound message contracts:

- project Rabbit producer annotations such as `@RabbitMqProducerAnnotation`
- `RabbitTemplate.convertAndSend(...)` when exchange or routing key evidence is
  visible
- Kafka producer send/publish calls with visible topic names
- project Kafka wrapper producers such as `KafkaProduceService.produce(...)` or
  `produceAsync(...)` when the first argument resolves to a topic/template

Identifier:

- Prefer queue name when present.
- Otherwise use routing key or topic.
- Preserve stable SaaS/runtime topic templates in `identifier` when the static
  prefix and semantic runtime dimensions are visible.
- Put exchange/routing key details in `match_rule`.

## HTTP Calls

Emit `HTTP_CALL` for outbound HTTP contracts:

- Feign client declarations
- Retrofit service declarations
- route/mapping annotations inside Feign or Retrofit client interfaces
- RestTemplate/WebClient/OkHttp/http-client calls
- project wrapper methods such as `restGet`, `restPost`, `restPut`, `restDelete`
  when the first argument resolves to a URL or path constant
- SDK wrapper methods that first resolve a path through `getApiUrl(CONST)` and
  then call a project HTTP transport method such as
  `responseContentByPost(url, ...)`, `responseContentByGet(url)`, or
  `responseContentByPut(url, ...)`. Resolve the Java constant and emit the
  concrete HTTP contract. Example: `MEMBER_POST_QUERY_OCC_ID =
  "/data/query/occIds"` plus `responseContentByPost(url, ...)` emits
  `HTTP_CALL POST /data/query/occIds`.

Identifier:

- Do not emit a class-level Feign/Retrofit host or base URL as an endpoint.
  Values such as `{system.api.address}` belong in metadata for concrete method
  routes, not in `identifier`.
- Use `METHOD /path/template` for wrapper calls where only path constants are
  visible.
- If the base URL comes from a configuration getter but the path is a visible
  static string or Java constant, the endpoint is **partially resolved**, not
  unresolved. Emit `METHOD {configKey}/path` as the identifier. Examples:
  `POST {kyLinApiConfig.mbspApiUrl}/member/register`,
  `POST {kyLinApiConfig.customerUrl}/wechat/member/register`,
  `POST {kyLinApiConfig.ebrandMemberUrl}/mobile/encryption`, and
  `POST {kyLinConfService.guidePackageApiBaseUrl}/configuration/fqn/fields`.
- Recognize configuration-style base URL getters such as `get*BaseUrl()`,
  `get*ApiUrl()`, `get*Url()`, and path-accepting helpers such as
  `getMbspApiUrl(PATH_CONST)`, `getCustomerUrl(PATH_CONST)`,
  `getEbrandMemberUrl(PATH_CONST)`, or `getApiUrl(PATH_CONST)`. Derive the
  config key from the receiver and getter name, for example
  `kyLinApiConfig.getMbspApiUrl(...)` -> `kyLinApiConfig.mbspApiUrl`.
- Resolve path arguments and path concatenations before falling back:
  `getMbspApiUrl(KyLinMbspApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT)`
  plus `MEMBER_POST_REGISTER_WECHAT = "/member/register"` becomes
  `POST {kyLinApiConfig.mbspApiUrl}/member/register`.
  `kyLinConfService.getGuidePackageApiBaseUrl() + DATA_MODEL_META_QUERY` plus
  `DATA_MODEL_META_QUERY = "/configuration/fqn/fields"` becomes
  `POST {kyLinConfService.guidePackageApiBaseUrl}/configuration/fqn/fields`.
- Track same-method URL variables. If `url` is assigned from a configuration
  base plus a path constant and later passed to `responseContentByPost(url, ...)`,
  emit the combined identifier from the assignment, not the bare variable name.
- For `String.format(...)`, resolve the format string first, strip query
  strings from the identifier, normalize `%s`/`%d` path placeholders to
  `{argN}`, and store query parameters in `match_rule.query_params`.
- If a concrete path cannot be resolved but the value comes from a visible
  configuration getter, keep the configuration key as the unresolved contract
  fingerprint instead of dropping the endpoint. Include the HTTP method:
  `POST {smartGuideConfService.iconUrl}` or
  `POST {smartGuideConfService.iconUrl[iconCode]}`.
- Keep an endpoint unresolved only when the path itself is not visible in source
  or machine-readable configuration. Dynamic map lookup such as
  `JsonUtils.toMap(config).get(iconCode)` remains
  `POST {smartGuideConfService.iconUrl[iconCode]}` unless a config file maps
  `iconCode` to a concrete path. Do not mark `baseConfig + staticPath` as
  unresolved.
- If the transport call is proven but neither a path nor a configuration key is
  available, fall back to a semantic operation placeholder such as
  `POST {SmartGuideSystemServer.generateRedirectUrl}`. Mark it unresolved in
  `match_rule`; do not invent a URL.
- For generic HTTP clients such as OkHttp, HttpClient, RestTemplate, or
  WebClient, emit an endpoint only when the concrete request method and URL/path
  can be read or resolved. A transport client class name such as `OkHttpClient`
  is infrastructure, not an endpoint.
- For SDK-backed HTTP clients, prefer the concrete HTTP contract when method and
  path are visible. Example: `WxCpMessageClient.send(...)` resolves through
  `WxCpApiPathConsts.Message.MESSAGE_SEND` to
  `HTTP_CALL POST /cgi-bin/message/send`; do not emit only
  `SDK WxCpMessageClient`.
- For CDP/data SDK wrappers, do not emit the request DTO or wrapper service
  method as an endpoint. The endpoint is the outbound HTTP contract, for
  example `CdpQueryOccIdsByMemberIdsRequest` is evidence for
  `HTTP_CALL POST /data/query/occIds` when the CDP path constant is visible.
- Strip query strings from the identifier and put them in
  `match_rule.query_params`.
- Keep dynamic values in `match_rule`; do not place wildcard syntax in
  `identifier`. Stable dynamic templates are allowed in `identifier` when they
  name a real runtime contract family and use `{placeholder}` dimensions rather
  than regex/wildcard syntax.
- For source-only calls into an external SDK where jar/class/source is not
  available, method names and parameters may participate in the identifier only
  when they are stable contract values: constants, enum members, topic names,
  API operation codes, path constants, or named configuration keys. Ordinary
  DTOs, request objects, local variables, `params`, `request`, and `body` are
  not endpoint identifiers by themselves.

Do not emit a wrapper method declaration as a call.
Do not emit Feign/Retrofit route annotations as `HTTP_API`.

## Distributed Cache

Emit `DISTRIBUTED_CACHE` for distributed cache contracts:

- RedisTemplate/StringRedisTemplate operations when a stable key prefix is
  visible
- Redisson or project Redis cache lock keys when a stable key prefix is visible

Identifier:

- Prefer the stable Redis key namespace or prefix.
- Strip wildcard markers from identifier and preserve raw key expression in
  `match_rule.key`.
- Resolve Redis key constants such as `RedisCacheKeyEnum.X.code` before
  emitting the identifier.
- Put backend evidence in `match_rule.backend`, such as `redis`.

Exclusions:

- In-memory caches such as Caffeine, Guava Cache, local maps, and
  `MemoryCacheKeyEnum` are not endpoint contracts.
- Spring Cache annotations are not distributed cache endpoints unless the source
  also proves a distributed backend.

## Event Bus

Emit local Spring application events as event bus endpoints with conservative
confidence:

- `publishEvent(new EventType(...))` -> `EVENT_BUS_PUBLISHER`
- `@EventListener` and `ApplicationListener<EventType>` ->
  `EVENT_BUS_LISTENER`

Use `match_rule.bus = "spring-application-event"` to distinguish local event
bus contracts from external brokers.

For Shuyun EventService (`com.shuyun.air.es`, `EventProducer`,
`PublishOptions`, `Event.of`, `publishBatchSync`, project `sendEvents` wrappers),
emit runtime event publish/consume contracts as `EVENT_BUS_PUBLISHER` or
`EVENT_BUS_LISTENER`. The identifier is the event FQN or stable event template;
initialization/schema JSON is setup evidence and must not be emitted as a
business endpoint.

When auditing or sampling endpoint results, treat the same event type and source
listener as one semantic endpoint even if it appears under multiple service
dependency closures. Record the service-scope fanout as metadata instead of
sampling repeated rows.

## Scheduled Jobs

Emit `SCHEDULED_JOB` for runtime scheduled entry contracts:

- Spring `@Scheduled`
- Cron annotations/configs
- XXL job declarations `@XxlJob`

For `@XxlJob`, prefer `executeClass` as identifier and record `desc`,
`cornExpr`, and `disable` in `match_rule`.

For Spring `@Scheduled`, prefer `ClassName.methodName` as identifier and record
cron/fixedDelay/fixedRate details in `match_rule.expression`.

## Negative Rules

Do not emit:

- commented-out annotations
- unit test, fixture, sample, or docs-only evidence
- XML comment SQL and inactive `resources/back` mapper SQL
- business table endpoints for `information_schema` or unresolved constants such
  as `TABLE_NAME`
- `CommandLineRunner` or `ApplicationRunner` as `CLI` without explicit
  user-invokable command evidence
- WebSocket infrastructure/interceptors as `WebSocket` endpoints without a
  route/channel declaration
- user-facing import/export templates, response downloads, or local classpath
  resources as `FILE`
- internal `*Service` classes as `SDK`; require an external `*Client` or `*SDK`
  contract.
- generic SDK or transport facilities (`OkHttpClient`, `HttpClient`,
  `RestTemplate`, `WebClient`, bare `OSSClient`) when no concrete operation
  target is visible.
- bare client construction such as `new AdminBizClient(...)`,
  `new ExecutorBizClient(...)`, or `new WeiXinMpClient(...)`. A client object is
  facility evidence, not an endpoint contract.

## SDK and Object Storage Contracts

Emit `SDK` only when the endpoint identifier names a semantic external
operation, not just the SDK class.

Identifier:

- For object storage SDK calls, include the operation and logical object target,
  for example `OSS putObject {bucket}/officialAccount/qrcode/{fileName}`.
- Do not emit object-storage identifiers whose target is only a generic
  parameter or helper template, such as `OSS getObject bucketName/dir+fileName`
  or `OSS putObject bucket/key`. Keep these as candidate evidence until the
  caller provides a concrete bucket/key contract.
- For SDK-backed HTTP or RPC calls, prefer the concrete request contract as
  `HTTP_CALL` or `RPC_CALL` when path/method is visible.
- If only `new SomeClient(...)` is visible and no operation/path/channel is
  visible nearby, do not emit an endpoint; keep it as evidence for a later
  concrete call.
