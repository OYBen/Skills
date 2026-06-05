#!/usr/bin/env python3
"""Static endpoint inventory extractor.

This is a deterministic, pattern-assisted first pass for the endpoint_profiler
skill. It favors clean endpoint contracts over topology inference.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
from functools import lru_cache
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rb",
    ".php",
    ".cs",
    ".scala",
    ".yaml",
    ".yml",
    ".properties",
    ".xml",
    ".json",
    ".proto",
    ".graphql",
    ".gql",
}

HTTP_METHODS = "GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS"
OPENAPI_PATH_RE = re.compile(r"^(\s*)[\"']?(/[^\"']+)[\"']?\s*:\s*(?:#.*)?$")
OPENAPI_METHOD_RE = re.compile(rf"^(\s*)({HTTP_METHODS.lower()})\s*:\s*(?:#.*)?$", re.IGNORECASE)
ROUTE_DECORATOR_RE = re.compile(
    rf"@(?:app|router|bp|blueprint)\.(get|post|put|patch|delete|head|options|route)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
FASTAPI_DECORATOR_RE = re.compile(
    rf"@[\w.]+\.(get|post|put|patch|delete|head|options)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
EXPRESS_ROUTE_RE = re.compile(
    rf"(?:app|router)\.(get|post|put|patch|delete|head|options|use)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
SPRING_ROUTE_RE = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*(?:\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"])?",
    re.IGNORECASE,
)
SPRING_MAPPING_METHOD_RE = re.compile(r"RequestMethod\.([A-Z]+)", re.IGNORECASE)
HTTP_CALL_RE = re.compile(
    r"(?:requests|httpx|axios|fetch|got|superagent|urllib3|RestTemplate|WebClient|OkHttp|HttpClient)[\w.]*\s*(?:\.\w+)?\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"['\"](https?://[^'\"]+)['\"]", re.IGNORECASE)
FEIGN_CLIENT_RE = re.compile(r"@(?:[A-Za-z_][A-Za-z0-9_.]*\.)?(?:[A-Za-z_][A-Za-z0-9_]*FeignClient|FeignClient)\s*\((.*?)\)", re.IGNORECASE | re.S)
RETROFIT_SERVICE_RE = re.compile(r"@RetrofitService\s*\((.*?)\)", re.IGNORECASE | re.S)
JAXRS_PATH_RE = re.compile(r"@Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)
JAXRS_HTTP_METHOD_RE = re.compile(r"@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", re.IGNORECASE)
RETROFIT_HTTP_METHOD_RE = re.compile(
    r"@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)
RETROFIT_IMPORT_RE = re.compile(r"\bimport\s+retrofit2\.http\.(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|\*)\s*;?", re.IGNORECASE)
REST_WRAPPER_CALL_RE = re.compile(r"\b(restGet|restPost|restPut|restDelete|restPatch)\s*\(\s*([^,\)\n]+)", re.IGNORECASE)
JAVA_GET_API_URL_ASSIGN_RE = re.compile(
    r"\b(?:String\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:String\.format\s*\(\s*)?[A-Za-z_][A-Za-z0-9_.]*\.getApiUrl\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)",
    re.IGNORECASE,
)
PROJECT_HTTP_RESPONSE_CALL_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\.responseContentBy(Get|Post|Put|Delete|Patch)\s*\(\s*([^,\)\n]+)",
    re.IGNORECASE,
)
JAVA_CONFIG_GETTER_ASSIGN_RE = re.compile(
    r"\b(?:final\s+)?(?:String\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:String\.format\s*\(\s*)?([A-Za-z_][A-Za-z0-9_]*)\.(get[A-Z][A-Za-z0-9_]*)\s*\(\s*([^,\)\n]*)",
    re.IGNORECASE,
)
JAVA_MAP_LOOKUP_ASSIGN_RE = re.compile(
    r"\b(?:String\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=.*?\b(?:JsonUtils\.toMap\s*\(\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\)?\.get\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)",
    re.IGNORECASE,
)
JAVA_METHOD_DECL_RE = re.compile(
    r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?(?:<[^>]+>\s*)?[\w<>\[\].?,\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)
JAVA_STRING_ASSIGN_RE = re.compile(
    r"\b(?:(?:val|var)\s+|(?:(?:final|private|public|protected|static)\s+)*String\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;\n]+)",
    re.IGNORECASE,
)
TENANT_TOPIC_JOIN_RE = re.compile(r"\bTenantUtil\.joinTopicName\s*\((.*?)\)", re.IGNORECASE)
KAFKA_CONSUMER_RE = re.compile(
    r"(?:@KafkaListener\s*\([^)]*topics\s*=\s*|consumer\.subscribe\s*\(\s*\[?\s*|subscribe\s*\(\s*)['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
RABBIT_LISTENER_RE = re.compile(r"@RabbitListener\s*\((.*?)\)", re.IGNORECASE | re.S)
TASK_CONSUMER_RE = re.compile(r"@[\w.]+\.task(?:\s*\(|\s*$)", re.IGNORECASE)
KAFKA_PRODUCER_RE = re.compile(
    r"\b(?:send|publish|emit)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
KAFKA_PRODUCER_CONCAT_RE = re.compile(
    r"\b(?:send|publish|emit)\s*\(\s*['\"]([^'\"]+)['\"]\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
KAFKA_PRODUCER_RECORD_RE = re.compile(r"\bnew\s+ProducerRecord\s*(?:<[^>]*>)?\s*\(\s*([^,\)]+)", re.IGNORECASE)
KAFKA_SUBSCRIBE_VAR_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?subscribe\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.IGNORECASE)
KAFKA_CONSUME_SERVICE_RE = re.compile(r"\b(?:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*)?new\s+KafkaConsumeService\s*\(", re.IGNORECASE)
KAFKA_SERVICE_CONSUME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.(?:consume|batchConsume)\s*\(", re.IGNORECASE)
KAFKA_PRODUCE_SERVICE_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?(?:produce|produceAsync)\s*\(", re.IGNORECASE)
JAVA_COLLECTION_ADD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.add\s*\((.*)\)\s*;?", re.IGNORECASE)
JAVA_MAP_PUT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.put\s*\((.*)\)\s*;?", re.IGNORECASE)
JAVA_MAP_KEYSET_FOREACH_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.keySet\s*\(\s*\)\.forEach\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*->", re.IGNORECASE)
RABBIT_PRODUCER_ANNOTATION_RE = re.compile(r"@RabbitMqProducerAnnotation\s*\((.*?)\)", re.IGNORECASE | re.S)
RABBIT_CONVERT_AND_SEND_RE = re.compile(r"\bconvertAndSend\s*\(\s*([^,\)\n]+)(?:\s*,\s*([^,\)\n]+))?", re.IGNORECASE)
STREAM_INPUT_RE = re.compile(r"@Input\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
STREAM_OUTPUT_RE = re.compile(r"@Output\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
STREAM_LISTENER_RE = re.compile(r"@StreamListener\s*\(\s*(?:value\s*=\s*)?([^)]+?)\s*\)", re.IGNORECASE)
STREAM_SEND_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\.send\s*\(", re.IGNORECASE)
SPRING_EVENT_PUBLISH_RE = re.compile(r"\.publishEvent\s*\(\s*new\s+([A-Za-z_]\w*)\s*\(", re.IGNORECASE)
SPRING_EVENT_PUBLISH_ARG_RE = re.compile(r"\.publishEvent\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.IGNORECASE)
JAVA_VARIABLE_DECL_RE = re.compile(r"\b(?:final\s+)?([A-Z][A-Za-z0-9_]*)\s+([a-z][A-Za-z0-9_]*)\b")
SPRING_EVENT_LISTENER_RE = re.compile(r"@EventListener\s*(?:\([^)]*\))?", re.IGNORECASE)
APPLICATION_LISTENER_RE = re.compile(r"\bApplicationListener\s*<\s*([A-Za-z_]\w*)\s*>", re.IGNORECASE)
SCHEDULE_RE = re.compile(r"@(Scheduled|Cron)\s*\(([^)]*)\)|cron\s*[:=]\s*['\"]([^'\"]+)['\"]", re.IGNORECASE | re.S)
XXL_JOB_RE = re.compile(r"@XxlJob\s*\((.*?)\)", re.IGNORECASE | re.S)
CLI_RE = re.compile(r"@(click\.command|app\.command|CommandLine\.Command)|program\.command\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
TABLE_RE = re.compile(
    r"(?:@Table\s*\(\s*name\s*=\s*|@TableName\s*\(\s*(?:value\s*=\s*)?|__tablename__\s*=\s*|table_name\s*=\s*|CREATE\s+TABLE\s+|FROM\s+|JOIN\s+|INSERT\s+INTO\s+|UPDATE\s+|DELETE\s+FROM\s+)([`\"']?)([A-Za-z_][\w.{}$*]*)(?:\1)(?=\s|$|[,);(])",
    re.IGNORECASE,
)
NON_ENDPOINT_TABLE_IDENTIFIERS = {
    "CURRENT_DATE",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "NOW",
    "SYSDATE",
    "TABLE_NAME",
    "P_TABLE_NAME",
    "QUERY_MODEL",
}
CACHE_RE = re.compile(r"(?:@Cacheable\s*\([^)]*(?:value|cacheNames)\s*=\s*|cache\.(?:get|set|delete)\(\s*)['\"]([^'\"]+)['\"]", re.IGNORECASE)
CACHE_INVALIDATE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.invalidateAll\s*\(", re.IGNORECASE)
SPRING_CACHE_RE = re.compile(r"@(Cacheable|CachePut|CacheEvict)\s*\((.*?)\)", re.IGNORECASE | re.S)
ENUM_STRING_ENTRY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*\(\s*['\"]([^'\"]+)['\"]")
REDIS_CACHE_KEY_ENUM_RE = re.compile(r"\bRedisCacheKeyEnum\.([A-Z][A-Z0-9_]*)\.code\b")
STRING_FORMAT_REDIS_ENUM_RE = re.compile(r"String\.format\s*\(\s*RedisCacheKeyEnum\.([A-Z][A-Z0-9_]*)\.code\s*(?:,.*?)?\)", re.IGNORECASE)
KOTLIN_REDIS_ENUM_INTERPOLATION_RE = re.compile(r"\$\{RedisCacheKeyEnum\.([A-Z][A-Z0-9_]*)\.code\}([^\"']*)")
REDIS_OPERATION_RE = re.compile(r"\b(?:redisCache|redisTemplate|stringRedisTemplate|redissonClient|ApplicationContextHolder\.getBean<ICache>\(\"redisCache\"\)|ApplicationContextHolder\.getBean<RedisCache>\(\"redisCache\"\))\s*(?:\[[^\]]+\]|\.\s*(get|put|set|delete|getRaw|putAllRaw|getLock|lock|unLock|evalScript|evalScriptRaw|opsForValue|boundValueOps)\s*(?:<[^>]+>)?\s*\()", re.IGNORECASE)
WRAP_KEY_CONSTANT_RE = re.compile(r"CacheService\.wrapKey\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)")
STARTUP_SCHEDULE_RE = re.compile(r"\b(?:super\.)?startup\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*TimeUnit\.([A-Z]+)\s*\)\s*(?:\{|\s*,\s*\{?)\s*([^}\n]*)", re.IGNORECASE)
STARTUP_SCHEDULE_COMMA_RE = re.compile(r"\b(?:super\.)?startup\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*TimeUnit\.([A-Z]+)\s*,\s*\{?\s*([^}\n]*)", re.IGNORECASE)
TIMER_SCHEDULE_RE = re.compile(r"\btimer\.schedule\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*,\s*([^,]+)\s*,\s*([^)]+)\)", re.IGNORECASE)
EVENT_SERVICE_SUBSCRIBE_RE = re.compile(r"EventServiceContext\s*\(\s*([^,\)]+)\s*,\s*([^,\)]+)\s*\)")
EVENT_SERVICE_PUSH_RE = re.compile(r"EventServiceSupport\.push\s*\(\s*([^,\)]+)", re.IGNORECASE)
EVENT_SERVICE_POLL_RE = re.compile(r"EventServiceSupport\.poll\s*\(\s*([^,\)]+)", re.IGNORECASE)
DATA_EVENT_PUBLISH_CALL_RE = re.compile(r"\b(?:sendEvents|sendEvent|Event\.of|publishBatchSync)\s*\(\s*([^,\)]+)", re.IGNORECASE)
DATA_EVENT_SCHEMA_CALL_RE = re.compile(r"\bPublishOptions\.of\s*\(\s*([^,\)]+)", re.IGNORECASE)
JAVA_ENTITY_MODEL_RE = re.compile(r"@Entity\s*\((.*?)\)", re.IGNORECASE | re.S)
EVENT_MODEL_RE = re.compile(r"@EventModel\s*\((.*?)\)", re.IGNORECASE | re.S)
FILE_RE = re.compile(r"['\"]([^'\"]+\.(?:csv|xlsx|json|xml|parquet|avro|txt|zip|pdf))['\"]", re.IGNORECASE)
PROTO_SERVICE_RE = re.compile(r"service\s+([A-Za-z_]\w*)\s*\{", re.IGNORECASE)
PROTO_RPC_RE = re.compile(r"rpc\s+([A-Za-z_]\w*)\s*\(", re.IGNORECASE)
DATAMODEL_RE = re.compile(r"\b(?:DataModel|DataClient|DataApi)<\s*([A-Za-z_]\w*)\s*>|\b([A-Za-z_]\w*)(?:DataClient|DataApi)\b")
OPENAPI_FQN_MODEL_RE = re.compile(
    r"\b(?:fetchOpenapiFqn|fetchFqnModel|fetchGuideModelMapping|fetchModelFields)\s*\([^;\n]*?ModelNameEnum\.([A-Z][A-Z0-9_]*)",
    re.IGNORECASE,
)
MODEL_ENUM_FQN_ACCESS_RE = re.compile(
    r"\bModelNameEnum\.([A-Z][A-Z0-9_]*)\s*\.\s*(?:getModelFqn|getModelExpr)\s*\(",
    re.IGNORECASE,
)
JAVA_FQN_CONSTANT_ACCESS_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\.FQN\b")
DATA_FQN_RE = re.compile(r"^(?:data|event)(?:\.[A-Za-z][A-Za-z0-9_]*|\.\{[A-Za-z_][A-Za-z0-9_]*\}|\.\$\{[A-Za-z_][A-Za-z0-9_]*\})+\.[A-Za-z][A-Za-z0-9_]*(?:\$\{[A-Za-z_][A-Za-z0-9_]*\})?$")
DATA_FQN_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:data|event)(?:\.[A-Za-z][A-Za-z0-9_]*)+\.[A-Za-z][A-Za-z0-9_]*(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)?(?![A-Za-z0-9_])(?!\s*\()")
DATAAPI_CALL_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?(?:getDataapiSdk\(\)\.)?(execute|query|importData|mergeData|fetch|commonSqlExecute|commonSqlExecuteWithAffectedRows|commonQuerySql|queryByStream|streamGetSn|batchMergeModel|batchInsertModel|batchInsert|saveCustomer|executeSql)\s*\((.*)", re.IGNORECASE)
DATA_MODEL_SCHEMA_CALL_RE = re.compile(r"\b(?:metaDataApiService|MetadataSupport)\.(createModel|createEnumModel|cleanEnumModel|add|deleteModel|getModel)\s*\((.*)", re.IGNORECASE)
DATAAPI_SQL_ASSIGN_RE = re.compile(r"\bString\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(String\.format\s*\(.*|[^;]+)", re.IGNORECASE)
SDK_RE = re.compile(r"\b(?:new\s+|from\s+|import\s+)([A-Z][A-Za-z0-9_]*(?:Client|SDK))\b")
SCHEMA_ENDPOINT_KINDS = {"DATA_MODEL_SCHEMA", "DATA_EVENT_SCHEMA"}
GENERIC_SDK_INFRASTRUCTURE = {
    "OkHttpClient",
    "HttpClient",
    "RestTemplate",
    "WebClient",
    "OSSClient",
}
OSS_OPERATION_RE = re.compile(
    r"\b([A-Za-z_]\w*)\.(putObject|getObject|deleteObject|copyObject)\s*\(\s*([^,\n]+)\s*,\s*([^,\n\)]+)",
    re.IGNORECASE,
)
JAVA_STRING_CONSTANT_RE = re.compile(
    r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?String\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"([^\"]*)\"",
    re.IGNORECASE,
)
JAVA_STATIC_FINAL_STRING_RE = re.compile(
    r"\b(?:public|private|protected)?\s*static\s+final\s+String\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"([^\"]*)\"",
    re.IGNORECASE,
)
JAVA_NAMED_STRING_CONSTANT_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final)\s+)*String\s+([A-Z][A-Z0-9_]*)\s*=\s*\"([^\"]*)\"",
    re.IGNORECASE | re.MULTILINE,
)
KOTLIN_NAMED_STRING_CONSTANT_RE = re.compile(
    r"^\s*(?:(?:private|public|protected|internal)\s+)?(?:const\s+)?val\s+([A-Z][A-Z0-9_]*)\s*=\s*\"([^\"]*)\"",
    re.IGNORECASE | re.MULTILINE,
)
ANNOTATION_STRING_RE = re.compile(r"\"([^\"]*)\"|'([^']*)'")

_JAVA_STRING_CONSTANTS_BY_ROOT: dict[str, dict[str, str]] = {}
_MODEL_NAME_ENUM_FQNS_BY_ROOT: dict[str, dict[str, str]] = {}
_STREAM_OUTPUT_METHODS_BY_ROOT: dict[str, dict[str, str]] = {}
_STREAM_BINDING_DESTINATIONS_BY_ROOT: dict[str, dict[str, str]] = {}


def has_http_client_context(line: str) -> bool:
    lower = line.lower()
    return any(
        token in lower
        for token in [
            "requests.",
            "httpx.",
            "axios",
            "fetch(",
            "got(",
            "superagent",
            "urllib3",
            "resttemplate",
            "webclient",
            "okhttp",
            "httpclient",
        ]
    )


def collect_annotation(lines: list[str], start_index: int) -> str:
    """Collect a Java annotation that may span multiple lines."""
    text = lines[start_index].strip()
    if not text.startswith("@"):
        return text
    balance = text.count("(") - text.count(")")
    cursor = start_index + 1
    while balance > 0 and cursor < len(lines) and cursor <= start_index + 20:
        next_line = lines[cursor].strip()
        if next_line.startswith("//"):
            break
        text += "\n" + next_line
        balance += next_line.count("(") - next_line.count(")")
        cursor += 1
    return text


def java_string_constants(root: Path) -> dict[str, str]:
    cache_key = str(root.resolve())
    if cache_key in _JAVA_STRING_CONSTANTS_BY_ROOT:
        return _JAVA_STRING_CONSTANTS_BY_ROOT[cache_key]
    constants: dict[str, str] = {}
    leaf_counts: Counter[str] = Counter()
    leaf_values: dict[str, str] = {}
    for file in iter_source_files(root):
        if file.suffix.lower() not in {".java", ".kt"} or is_always_excluded_source(file, root):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        class_match = re.search(r"\b(?:class|interface|enum|object)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        owner_name = class_match.group(1) if class_match else file.stem
        string_matches = list(JAVA_NAMED_STRING_CONSTANT_RE.finditer(text)) + list(KOTLIN_NAMED_STRING_CONSTANT_RE.finditer(text))
        for match in string_matches:
            name = match.group(1)
            if name.upper() != name:
                continue
            value = match.group(2)
            constants[f"{owner_name}.{name}"] = value
            leaf_counts[name] += 1
            leaf_values.setdefault(name, value)
    for name, count in leaf_counts.items():
        if count == 1:
            constants[name] = leaf_values[name]
        elif name not in constants:
            constants[name] = name
    _JAVA_STRING_CONSTANTS_BY_ROOT[cache_key] = constants
    return constants


def split_java_args(args: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for char in args:
        if quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        result.append("".join(current).strip())
    return result


def annotation_attr(args: str, name: str) -> str | None:
    pattern = re.compile(rf"\b{name}\s*=\s*")
    match = pattern.search(args)
    if not match:
        return None
    tail = args[match.end() :]
    return split_java_args(tail)[0] if tail else None


def first_annotation_string(expr: str | None) -> str | None:
    if not expr:
        return None
    match = ANNOTATION_STRING_RE.search(expr)
    if not match:
        return None
    return match.group(1) or match.group(2)


def annotation_strings(expr: str | None) -> list[str]:
    if not expr:
        return []
    values: list[str] = []
    for match in ANNOTATION_STRING_RE.finditer(expr):
        value = match.group(1) or match.group(2)
        if value is not None:
            values.append(clean_path(value))
    return values


def resolve_java_expr(expr: str | None, root: Path) -> str | None:
    if not expr:
        return None
    cleaned = expr.strip().strip("{}")
    constants = java_string_constants(root)
    if "${" in cleaned and "}" in cleaned:
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", cleaned):
            if token in constants:
                return "{" + constants[token] + "}"
    literal = first_annotation_string(cleaned)
    if literal is not None:
        return clean_path(literal)
    cleaned = re.sub(r"\.class\b", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    if cleaned in constants:
        return clean_path(constants[cleaned])
    leaf = cleaned.split(".")[-1]
    if "." in cleaned:
        owner_head = cleaned.split(".", 1)[0]
        qualified_matches = [
            value
            for key, value in constants.items()
            if key.startswith(owner_head + ".") and key.endswith("." + leaf)
        ]
        if len(set(qualified_matches)) == 1:
            return clean_path(qualified_matches[0])
    if leaf in constants:
        return clean_path(constants[leaf])
    if cleaned:
        return clean_path(cleaned)
    return None


@lru_cache(maxsize=16)
def cache_enum_codes(root_key: str) -> dict[str, str]:
    root = Path(root_key)
    values: dict[str, str] = {}
    for file in iter_source_files(root):
        if file.suffix.lower() not in {".java", ".kt"} or is_always_excluded_source(file, root):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for enum_name in ("RedisCacheKeyEnum",):
            enum_match = re.search(rf"\benum\s+class\s+{enum_name}\b.*?\{{(.*?)\n\}}", text, re.S)
            if not enum_match:
                continue
            for line in enum_match.group(1).splitlines():
                entry_match = ENUM_STRING_ENTRY_RE.search(line)
                if entry_match:
                    values[f"{enum_name}.{entry_match.group(1)}"] = entry_match.group(2)
    return values


def normalize_cache_template(value: str) -> tuple[str, dict[str, Any]]:
    counter = 0

    def repl(_: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        return f"{{arg{counter}}}"

    identifier = re.sub(r"%[sd]", repl, str(value).strip().strip("\"'"))
    identifier = re.sub(r"\$\{([^}]+)\}", r"{\1}", identifier)
    match_rule: dict[str, Any] = {"type": "distributed_cache", "backend": "redis", "key": identifier}
    if counter:
        match_rule["template_variables"] = [f"arg{i}" for i in range(1, counter + 1)]
        match_rule["raw_template"] = value
    return identifier, match_rule


def cache_key_from_enum(root: Path, enum_name: str, member: str) -> tuple[str, dict[str, Any]] | None:
    raw = cache_enum_codes(str(root.resolve())).get(f"{enum_name}.{member}")
    if not raw:
        return None
    identifier, match_rule = normalize_cache_template(raw)
    match_rule["enum"] = f"{enum_name}.{member}"
    return identifier, match_rule


@lru_cache(maxsize=16)
def enum_first_string_values(root_key: str) -> dict[str, str]:
    root = Path(root_key)
    values: dict[str, str] = {}
    for file in iter_source_files(root):
        if file.suffix.lower() not in {".java", ".kt"} or is_always_excluded_source(file, root):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for enum_match in re.finditer(r"\benum\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b.*?\{(.*?)\n\}", text, re.S):
            enum_name = enum_match.group(1)
            for line in enum_match.group(2).splitlines():
                entry_match = ENUM_STRING_ENTRY_RE.search(line)
                if entry_match:
                    values[f"{enum_name}.{entry_match.group(1)}"] = entry_match.group(2)
    return values


def resolve_event_fqn_expr(expr: str, root: Path) -> str | None:
    cleaned = expr.strip()
    cleaned = re.sub(r"\.fqn\b", "", cleaned)
    cleaned = re.sub(r"\.eventFqn\b", "", cleaned)
    if cleaned in enum_first_string_values(str(root.resolve())):
        return enum_first_string_values(str(root.resolve()))[cleaned]
    literal = first_annotation_string(cleaned)
    if literal and literal.startswith("event."):
        return literal
    resolved = resolve_java_expr(cleaned, root)
    if resolved and resolved.startswith("event."):
        return resolved
    return None


def local_redis_key_builders(text: str, root: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    builders: dict[str, tuple[str, dict[str, Any]]] = {}
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        match = re.search(r"\b(?:private\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*:\s*String\b", line)
        if not match:
            continue
        name = match.group(1)
        window = lines[idx : min(len(lines), idx + 8)]
        for candidate in window:
            return_match = re.search(r"\breturn\s+(.+)$", candidate.strip())
            if not return_match:
                continue
            expr = return_match.group(1).strip()
            resolved = resolve_cache_key_expr(expr, root, {})
            if resolved:
                identifier, match_rule = resolved
                match_rule = {**match_rule, "source_kind": "redis_key_builder", "builder": name}
                builders[name] = (identifier, match_rule)
            break
    return builders


def resolve_cache_key_expr(expr: str, root: Path, local_cache_vars: dict[str, tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    cleaned = expr.strip()
    if cleaned in local_cache_vars:
        return local_cache_vars[cleaned]
    call_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", cleaned)
    if call_match and call_match.group(1) in local_cache_vars:
        return local_cache_vars[call_match.group(1)]
    format_match = STRING_FORMAT_REDIS_ENUM_RE.search(cleaned)
    if format_match:
        return cache_key_from_enum(root, "RedisCacheKeyEnum", format_match.group(1))
    interpolation_match = KOTLIN_REDIS_ENUM_INTERPOLATION_RE.search(cleaned)
    if interpolation_match:
        base = cache_key_from_enum(root, "RedisCacheKeyEnum", interpolation_match.group(1))
        if base:
            identifier, match_rule = base
            suffix = clean_path(interpolation_match.group(2)).strip()
            suffix = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", suffix)
            if suffix:
                identifier = f"{identifier}{suffix}"
                match_rule = {**match_rule, "key": identifier, "suffix": suffix, "source_kind": "kotlin_interpolation"}
            return identifier, match_rule
    enum_match = REDIS_CACHE_KEY_ENUM_RE.search(cleaned)
    if enum_match:
        return cache_key_from_enum(root, "RedisCacheKeyEnum", enum_match.group(1))
    wrap_match = WRAP_KEY_CONSTANT_RE.search(cleaned)
    if wrap_match:
        constant = resolve_java_expr(wrap_match.group(1), root)
        if constant:
            identifier, match_rule = normalize_cache_template(constant)
            match_rule["resolver"] = "CacheService.wrapKey"
            match_rule["constant"] = wrap_match.group(1)
            return identifier, match_rule
    literal = first_annotation_string(cleaned)
    if literal and re.search(r"(cache|key|lock|offset|redis|dynamic_code)", literal, re.IGNORECASE):
        constants = java_string_constants(root)
        literal = re.sub(
            r"\$\{([A-Z][A-Z0-9_]*)\}",
            lambda m: constants.get(m.group(1), "{" + m.group(1) + "}"),
            literal,
        )
        literal = re.sub(
            r"\$([A-Z][A-Z0-9_]*)\b",
            lambda m: constants.get(m.group(1), "{" + m.group(1) + "}"),
            literal,
        )
        return normalize_cache_template(literal)
    return None


def resolve_java_topic_expr(expr: str | None, root: Path) -> tuple[str | None, dict[str, Any]]:
    if not expr:
        return None, {}
    tenant_match = TENANT_TOPIC_JOIN_RE.search(expr)
    if tenant_match:
        args = split_java_args(tenant_match.group(1))
        topic_expr = args[-1] if args else None
        topic = resolve_java_expr(topic_expr, root)
        if topic:
            return topic, {"tenant_scoped": True, "resolver": "TenantUtil.joinTopicName"}
    topic = resolve_java_expr(expr, root)
    if topic and re.search(r"(topic|queue|event|message|reach|audit|log|notify|behavior)", topic, re.IGNORECASE):
        return topic, {}
    return None, {}


def split_java_concat(expr: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for ch in expr:
        if quote:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            current.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if ch == "+" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def extract_call_args_after(text: str, start: int) -> str | None:
    paren = text.find("(", start)
    if paren < 0:
        return None
    depth = 0
    quote: str | None = None
    escape = False
    for index in range(paren, len(text)):
        char = text[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[paren + 1 : index]
    return None


def java_dynamic_topic_placeholder(expr: str) -> str:
    cleaned = expr.strip()
    for pattern, placeholder in [
        (r"\bgetTenantId\s*\(\s*\)", "tenantId"),
        (r"\bgetClient\s*\(\s*\)", "client"),
        (r"\bgetGroup\s*\(\s*\)", "group"),
    ]:
        if re.search(pattern, cleaned):
            return "{" + placeholder + "}"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
        return "{" + cleaned + "}"
    leaf = re.sub(r"\s*\(.*\)\s*$", "", cleaned).split(".")[-1]
    leaf = re.sub(r"[^A-Za-z0-9_]+", "", leaf)
    return "{" + (leaf or "dynamic") + "}"


def java_collection_arg_exprs(expr: str) -> list[str]:
    cleaned = expr.strip().rstrip(";")
    collection_match = re.search(r"\b(?:Arrays\.asList|List\.of|Collections\.singleton(?:List)?)\s*\((.*)\)\s*$", cleaned)
    if collection_match:
        return split_java_args(collection_match.group(1))
    return [cleaned]


def resolve_java_message_topic_entries_expr(
    expr: str | None,
    root: Path,
    local_topics: dict[str, tuple[str, dict[str, Any]]],
    local_topic_sets: dict[str, list[tuple[str, dict[str, Any]]]],
) -> list[tuple[str, dict[str, Any]]]:
    if not expr:
        return []
    entries: list[tuple[str, dict[str, Any]]] = []
    for arg in java_collection_arg_exprs(expr):
        cleaned = arg.strip().rstrip(";")
        if cleaned in local_topic_sets:
            entries.extend(local_topic_sets[cleaned])
            continue
        topic, meta = resolve_java_message_topic_expr(cleaned, root, local_topics)
        if topic:
            entries.append((topic, meta))
    return entries


def narrow_topic_entries_by_contains_branch(
    lines: list[str],
    idx: int,
    entries: list[tuple[str, dict[str, Any]]],
    root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    if len(entries) <= 1:
        return entries
    start = max(0, idx - 14)
    context = lines[start : idx - 1]
    condition_index = -1
    condition_token = None
    for offset, prior in enumerate(context):
        match = re.search(r"\bif\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\.contains\s*\(([^)]+)\)\s*\)", prior)
        if not match:
            continue
        resolved = resolve_java_expr(match.group(1), root) or first_annotation_string(match.group(1))
        if resolved:
            condition_index = offset
            condition_token = resolved
    if not condition_token:
        return entries
    else_seen = any(re.search(r"\}\s*else\b|\belse\s*\{", prior) for prior in context[condition_index + 1 :])
    matched = [(topic, meta) for topic, meta in entries if condition_token in topic]
    unmatched = [(topic, meta) for topic, meta in entries if condition_token not in topic]
    if else_seen and unmatched:
        return unmatched
    if not else_seen and matched:
        return matched
    return entries


def resolve_java_message_topic_expr(
    expr: str | None,
    root: Path,
    local_topics: dict[str, tuple[str, dict[str, Any]]],
) -> tuple[str | None, dict[str, Any]]:
    if not expr:
        return None, {}
    cleaned = expr.strip().rstrip(";")
    if cleaned in local_topics:
        topic, meta = local_topics[cleaned]
        return topic, {**meta, "source_kind": meta.get("source_kind", "local_topic_variable")}
    system_property_match = re.search(r"\bSystem\.getProperty\s*\((.*)\)", cleaned)
    if system_property_match:
        args = split_java_args(system_property_match.group(1))
        for arg in args:
            topic, meta = resolve_java_message_topic_expr(arg, root, local_topics)
            if topic:
                return topic, {**meta, "resolver": "System.getProperty"}
    parts = split_java_concat(cleaned)
    if len(parts) > 1:
        constants = java_string_constants(root)
        rendered: list[str] = []
        dynamic = False
        for part in parts:
            literal = first_annotation_string(part)
            if literal is not None:
                rendered.append(literal)
                continue
            part_clean = re.sub(r"\s+", "", part)
            part_leaf = part_clean.split(".")[-1]
            if part_clean in local_topics:
                rendered.append(local_topics[part_clean][0])
                continue
            if part_clean in constants:
                rendered.append(constants[part_clean])
                continue
            if part_leaf in constants:
                rendered.append(constants[part_leaf])
                continue
            rendered.append(java_dynamic_topic_placeholder(part))
            dynamic = True
        candidate = normalize_message_identifier("".join(rendered))
        if candidate and (dynamic or re.search(r"(topic|queue|event|message|job)", candidate, re.IGNORECASE)):
            return candidate, {"template": candidate, "dynamic": dynamic, "source_kind": "java_topic_template"}
    topic, meta = resolve_java_topic_expr(cleaned, root)
    if topic and topic != re.sub(r"\s+", "", cleaned):
        return normalize_message_identifier(topic), meta
    return None, {}


def java_expr_is_literal_or_constant(expr: str | None, root: Path) -> bool:
    if not expr:
        return False
    if first_annotation_string(expr) is not None:
        return True
    cleaned = re.sub(r"\.class\b", "", expr.strip().strip("{}"))
    leaf = re.sub(r"\s+", "", cleaned).split(".")[-1]
    return leaf in java_string_constants(root)


def normalize_message_identifier(raw: str | None) -> str | None:
    if not raw:
        return None
    identifier = raw.strip()
    identifier = identifier.replace("QueueName.", "").replace("RabbitRoutingKey.", "")
    identifier = identifier.replace("()", "")
    identifier = identifier.strip('"\'')
    return identifier or None


def stream_output_methods(root: Path) -> dict[str, str]:
    cache_key = str(root.resolve())
    if cache_key in _STREAM_OUTPUT_METHODS_BY_ROOT:
        return _STREAM_OUTPUT_METHODS_BY_ROOT[cache_key]
    mapping: dict[str, str] = {}
    for file in iter_source_files(root):
        if file.suffix.lower() not in {".java", ".kt"} or is_always_excluded_source(file, root):
            continue
        try:
            lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines):
            output_match = STREAM_OUTPUT_RE.search(line)
            if not output_match:
                continue
            lookahead = " ".join(item.strip() for item in lines[idx : min(len(lines), idx + 4)])
            method_match = re.search(r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", lookahead)
            if not method_match:
                method_match = re.search(r"\b[A-Za-z_][A-Za-z0-9_<>, ?]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", lookahead)
            owner_type = enclosing_type_name(lines, idx, file.stem)
            channel = resolve_stream_channel(output_match.group(1), root, owner_type)
            if method_match and channel:
                mapping[method_match.group(1)] = channel
    _STREAM_OUTPUT_METHODS_BY_ROOT[cache_key] = mapping
    return mapping


def stream_binding_destinations(root: Path) -> dict[str, str]:
    cache_key = str(root.resolve())
    if cache_key in _STREAM_BINDING_DESTINATIONS_BY_ROOT:
        return _STREAM_BINDING_DESTINATIONS_BY_ROOT[cache_key]
    mapping: dict[str, str] = {}
    for file in iter_source_files(root):
        if file.suffix.lower() not in {".yaml", ".yml", ".properties"} or is_always_excluded_source(file, root):
            continue
        try:
            lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        if file.suffix.lower() == ".properties":
            for line in lines:
                match = re.search(r"spring\.cloud\.stream\.bindings\.([A-Za-z0-9_.-]+)\.destination\s*=\s*(.+)", line)
                if match:
                    mapping[match.group(1)] = clean_path(match.group(2).strip())
            continue
        current_binding: str | None = None
        current_indent: int | None = None
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            binding_match = re.match(r"^(\s*)([A-Z][A-Z0-9_]*(?:_INPUT|_OUTPUT))\s*:\s*$", line)
            if binding_match:
                current_binding = binding_match.group(2)
                current_indent = len(binding_match.group(1))
                continue
            if current_binding is not None and current_indent is not None:
                indent = len(line) - len(line.lstrip())
                if indent <= current_indent:
                    current_binding = None
                    current_indent = None
                    continue
                dest_match = re.match(r"^\s*destination\s*:\s*(.+?)\s*$", line)
                if dest_match:
                    mapping[current_binding] = clean_path(dest_match.group(1).strip().strip('"\''))
    _STREAM_BINDING_DESTINATIONS_BY_ROOT[cache_key] = mapping
    return mapping


def resolve_stream_channel(expr: str | None, root: Path, owner: str | None = None) -> str | None:
    channel = normalize_message_identifier(resolve_java_expr(expr, root))
    if expr and owner:
        cleaned = re.sub(r"\s+", "", expr.strip().strip("{}"))
        constants = java_string_constants(root)
        owner_value = constants.get(f"{owner}.{cleaned}")
        if owner_value and (channel == cleaned or channel == constants.get(cleaned) or channel == expr.strip()):
            channel = normalize_message_identifier(owner_value)
    if not channel:
        return None
    destinations = stream_binding_destinations(root)
    return normalize_message_identifier(destinations.get(channel, channel))


def normalize_cache_identifier(cache_name: str | None, key_expr: str | None, root: Path) -> tuple[str, dict[str, Any]] | None:
    cache = resolve_java_expr(cache_name, root) if cache_name else None
    key_literal = first_annotation_string(key_expr or "")
    key = key_literal or resolve_java_expr(key_expr, root)
    if not cache and not key:
        return None
    cleaned_key = key or ""
    cleaned_key = cleaned_key.replace("*", "").replace("#", "")
    cleaned_key = re.sub(r"\s*\+\s*.*$", "", cleaned_key).strip("'\" +")
    cleaned_key = cleaned_key.rstrip(":")
    identifier = f"{cache}:{cleaned_key}" if cache and cleaned_key else cache or cleaned_key
    match_rule: dict[str, Any] = {"type": "distributed_cache", "backend": "unknown"}
    if cache:
        match_rule["cache"] = cache
    if key:
        match_rule["key"] = key
    return identifier, match_rule


def http_method_from_rest_wrapper(name: str) -> str:
    lower = name.lower()
    if "post" in lower:
        return "POST"
    if "put" in lower:
        return "PUT"
    if "delete" in lower:
        return "DELETE"
    if "patch" in lower:
        return "PATCH"
    return "GET"


def http_method_from_project_response_call(name: str) -> str:
    return name.upper() or "ANY"


def java_getter_property(method_name: str) -> str:
    name = re.sub(r"^get", "", method_name or "", flags=re.IGNORECASE)
    if not name:
        return method_name
    return name[:1].lower() + name[1:]


def looks_like_config_provider(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in ["config", "conf", "properties", "setting"])


def config_placeholder(owner: str, property_name: str, dynamic_key: str | None = None) -> str:
    base = f"{owner}.{property_name}"
    if dynamic_key:
        return "{" + f"{base}[{dynamic_key}]" + "}"
    return "{" + base + "}"


def config_placeholder_with_path(owner: str, property_name: str, path: str | None) -> str:
    placeholder = config_placeholder(owner, property_name)
    if path and path.startswith("/"):
        return placeholder + normalize_route_path(path)
    return placeholder


def normalize_http_call_identifier(method: str | None, url_or_path: str | None) -> str | None:
    if not url_or_path:
        return None
    target = clean_http_target(url_or_path.strip())
    if not target:
        return None
    if target.startswith("http://") or target.startswith("https://") or target.startswith("{"):
        return target
    if target.startswith("/"):
        return f"{method or 'ANY'} {normalize_http_target_path(target)}"
    return f"{method or 'ANY'} {target}"


def split_query(path_or_url: str) -> tuple[str, dict[str, str]]:
    if "?" not in path_or_url:
        return path_or_url, {}
    base, query = path_or_url.split("?", 1)
    params: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
        else:
            key, value = part, ""
        params[clean_path(key)] = clean_path(value)
    return base, params


def normalize_percent_placeholders(path: str) -> str:
    counter = 0

    def repl(_: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        return f"{{arg{counter}}}"

    return re.sub(r"%[sd]", repl, path)


def http_path_identifier_and_rule(method: str, raw_path: str, rule_type: str = "path_template", convert_colon_params: bool = True) -> tuple[str, dict[str, Any]]:
    cleaned = clean_path(raw_path, convert_colon_params=convert_colon_params)
    base, query_params = split_query(cleaned)
    base = normalize_percent_placeholders(base)
    path = normalize_route_path(base, convert_colon_params=convert_colon_params)
    identifier = f"{method} {path}"
    match_rule: dict[str, Any] = {"type": rule_type, "method": method, "path": path}
    if query_params:
        match_rule["query_params"] = query_params
    variables = re.findall(r"\{([^}]+)\}", path)
    if variables:
        match_rule["template_variables"] = variables
    return identifier, match_rule


def http_call_identifier_and_rule(method: str | None, raw_target: str, client: str | None = None) -> tuple[str, dict[str, Any]]:
    target = clean_http_target(raw_target)
    base, query_params = split_query(target)
    base = normalize_percent_placeholders(base)
    if base.startswith("http://") or base.startswith("https://"):
        identifier = base
        match_rule: dict[str, Any] = {"type": "url_template", "url": base}
        if method:
            match_rule["method"] = method
    elif base.startswith("{"):
        identifier = f"{method} {base}" if method else base
        match_rule = {"type": "url_template", "url": base, "resolved": False}
        if method:
            match_rule["method"] = method
    elif base.startswith("/"):
        path = normalize_http_target_path(base)
        identifier = f"{method or 'ANY'} {path}"
        match_rule = {"type": "url_template", "method": method or "ANY", "path": path}
    else:
        identifier = f"{method or 'ANY'} {base}"
        match_rule = {"type": "url_template", "method": method or "ANY", "path": base}
    if client:
        match_rule["client"] = client
    if query_params:
        match_rule["query_params"] = query_params
    return identifier, match_rule


def strip_xml_comments_preserve_lines(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return re.sub(r"<!--.*?-->", repl, text, flags=re.S)


def next_java_method_name(lines: list[str], start_index: int) -> str | None:
    lookahead = " ".join(line.strip() for line in lines[start_index : min(len(lines), start_index + 8)])
    match = re.search(
        r"\b(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:<[^>]+>\s*)?[\w<>\[\].?,\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        lookahead,
    )
    if match:
        return match.group(1)
    match = re.search(r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", lookahead)
    if match:
        return match.group(1)
    return None


def java_type_name(text: str, fallback: str) -> str:
    match = re.search(r"\b(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    return match.group(1) if match else fallback


def enclosing_type_name(lines: list[str], start_index: int, fallback: str) -> str:
    """Best-effort enclosing type for Java/Kotlin files with multiple classes."""
    for line in reversed(lines[:start_index]):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        match = re.search(r"\b(?:class|interface|enum|object)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if match:
            return match.group(1)
    return fallback


def spring_event_listener_identifier(annotation: str, lines: list[str], start_index: int, fallback_type: str) -> tuple[str, float]:
    annotation_match = re.search(r"@EventListener\s*\((.*?)\)", annotation, re.IGNORECASE | re.S)
    if annotation_match:
        args = annotation_match.group(1)
        class_match = re.search(r"\b([A-Z][A-Za-z0-9_]*)\s*::\s*class\b", args)
        if class_match:
            return class_match.group(1), 0.72
        class_match = re.search(r"\b([A-Z][A-Za-z0-9_]*)\s*\.class\b", args)
        if class_match:
            return class_match.group(1), 0.72
    next_lines = "\n".join(lines[start_index : min(len(lines), start_index + 8)])
    java_param_match = re.search(r"\((?:final\s+)?([A-Z][A-Za-z0-9_]*)\s+\w+\)", next_lines)
    if java_param_match:
        return java_param_match.group(1), 0.68
    kotlin_param_match = re.search(r"\(\s*\w+\s*:\s*([A-Z][A-Za-z0-9_]*)\b", next_lines)
    if kotlin_param_match:
        return kotlin_param_match.group(1), 0.68
    method_name = next_java_method_name(lines, start_index)
    if method_name:
        return f"{fallback_type}.{method_name}", 0.58
    return "spring-event-listener", 0.52


def is_java_http_client_contract(text: str) -> bool:
    return bool(
        FEIGN_CLIENT_RE.search(text)
        or RETROFIT_SERVICE_RE.search(text)
        or (RETROFIT_IMPORT_RE.search(text) and RETROFIT_HTTP_METHOD_RE.search(text))
    )


def is_http_call_literal_candidate(target: str) -> bool:
    cleaned = clean_http_target(target or "").strip()
    if not cleaned:
        return False
    if cleaned.startswith(("http://", "https://", "/", "{", "$")):
        return True
    return "/" in cleaned


def source_extension_allows_semantic_code(file: Path) -> bool:
    return file.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rb", ".php", ".cs", ".scala"}


def is_plain_model_or_dto_source(file: Path) -> bool:
    normalized = file.as_posix().lower()
    name = file.name.lower()
    return (
        any(part in normalized for part in ["/model/", "/dto/", "/vo/", "/bo/", "/request/", "/response/"])
        or name.endswith(("request.java", "response.java", "dto.java", "vo.java", "bo.java"))
    )


def source_extension_allows_db_table_scan(file: Path) -> bool:
    return source_extension_allows_semantic_code(file) or file.suffix.lower() in {".xml", ".sql"}


def scope_relative_path(file: Path, root: Path | None = None) -> Path:
    if root is None:
        return file
    try:
        return file.relative_to(root)
    except ValueError:
        return file


def is_test_source(file: Path, root: Path | None = None) -> bool:
    scoped = scope_relative_path(file, root)
    normalized = scoped.as_posix().lower()
    name = file.name.lower()
    return (
        "/src/test/" in normalized
        or normalized.startswith("src/test/")
        or "\\src\\test\\" in str(scoped).lower()
        or "/test/" in normalized
        or normalized.startswith("test/")
        or normalized.startswith("tests/")
        or "/tests/" in normalized
        or name.endswith("test.java")
        or name.endswith("tests.java")
        or name.endswith("_test.py")
        or name.endswith(".spec.ts")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".test.js")
    )


def is_always_excluded_source(file: Path, root: Path | None = None) -> bool:
    scoped = scope_relative_path(file, root)
    normalized = scoped.as_posix().lower()
    path_parts = [part.lower() for part in scoped.parts]
    parts = set(path_parts)
    if file.name.lower().startswith(".graphify"):
        return True
    if is_test_source(file, root):
        return True
    if "/src/main/java/org/flywaydb/" in f"/{normalized}" or "/db/migration/" in f"/{normalized}":
        return True
    if parts & {
        ".git",
        ".cursor",
        ".idea",
        ".vscode",
        "target",
        "build",
        "dist",
        "out",
        "node_modules",
        "coverage",
        "logs",
        "tmp",
        "temp",
    }:
        return True
    example_parts = {"example", "examples", "sample", "samples", "demo", "demos", "mock", "mocks", "stub", "stubs", "fixture", "fixtures"}
    if parts & {"mock", "mocks", "stub", "stubs", "fixture", "fixtures", "examples", "samples", "demos"}:
        return True
    if path_parts and path_parts[0] in example_parts:
        return True
    if len(path_parts) > 1 and path_parts[1] in example_parts:
        return True
    doc_parts = {"docs", "doc", "design"}
    if parts & doc_parts:
        contract_exts = {".yaml", ".yml", ".json", ".proto", ".graphql", ".gql"}
        contract_name = any(token in file.name.lower() for token in ["openapi", "swagger", "asyncapi"])
        if file.suffix.lower() not in contract_exts and not contract_name:
            return True
    if normalized.endswith("/readme.md") or normalized.endswith("/changelog.md"):
        return True
    return False


def is_model_metadata_json(file: Path) -> bool:
    normalized = file.as_posix().lower()
    return (
        file.suffix.lower() == ".json"
        and (
            ("/meta-inf/scripts/" in normalized and "/model/" in normalized)
            or "/dm/migration/" in normalized
            or normalized.endswith("/initevents.json")
            or ("/src/main/resources/json/init" in normalized and normalized.endswith(".json"))
        )
    )


def is_static_model_schema_source(file: Path) -> bool:
    normalized = file.as_posix().lower()
    if file.suffix.lower() != ".json":
        return False
    if "/dm/migration/" in normalized:
        return True
    if "/meta-inf/scripts/" in normalized and "/model/" in normalized:
        return True
    if "/src/main/resources/json/init" in normalized and normalized.endswith(".json"):
        return not normalized.endswith("/initevents.json")
    return False


def normalize_table_identifier(raw: str) -> tuple[str, dict[str, Any]]:
    table = raw.strip().strip("`\"'")
    variables = re.findall(r"\{([^}]+)\}", table)
    clean = re.sub(r"\{[^}]+\}", "", table)
    clean = clean.split(".")[-1]
    clean = clean.strip("_")
    match_rule: dict[str, Any] = {"type": "table", "name": clean or table}
    if table != clean and table:
        match_rule["template"] = table
    if variables:
        match_rule["template_variables"] = variables
    if "." in table and "{" not in table:
        match_rule["schema"] = ".".join(table.split(".")[:-1])
    return clean or table, match_rule


def is_valid_table_endpoint_identifier(identifier: str, raw: str, line: str) -> bool:
    normalized = identifier.strip("`\"'").strip()
    upper = normalized.upper()
    raw_upper = raw.upper()
    if not normalized:
        return False
    if "#" in raw or "#" in normalized:
        return False
    if upper in NON_ENDPOINT_TABLE_IDENTIFIERS:
        return False
    if upper in {"TABLES", "PARTITIONS", "COLUMNS", "SCHEMATA"} and "information_schema" in line.lower():
        return False
    if "TABLE_NAME" in raw_upper and "TABLE_NAME" in upper:
        return False
    if re.search(r"\bUPDATE\s+[`\"']?" + re.escape(raw) + r"[`\"']?\s*=", line, re.IGNORECASE):
        return False
    if re.search(r"\b(?:UPDATE|FROM|JOIN|INSERT\s+INTO|DELETE\s+FROM)\s+" + re.escape(raw), line, re.IGNORECASE):
        if "." not in raw and "_" not in raw and raw[:1].islower() and any(ch.isupper() for ch in raw):
            return False
    return True


def normalize_datamodel_fqn(value: str) -> str:
    normalized = value.strip().strip("\"'").replace("%s", "${dynamic}").replace("%d", "${dynamic}")
    normalized = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", r"${\1}", normalized)
    normalized = normalized.replace("{*}", "${dynamic}")
    return normalized


def is_datamodel_fqn(value: str) -> bool:
    normalized = normalize_datamodel_fqn(value)
    return bool(DATA_FQN_RE.match(normalized)) and not is_config_like_data_key(normalized)


def is_config_like_data_key(value: str) -> bool:
    normalized = normalize_datamodel_fqn(value).lower()
    return (
        normalized.startswith("spring.data.")
        or normalized.startswith("data.redis.")
        or normalized.startswith("data.spring.")
        or normalized == "data.event.concurrency.enabled"
        or re.fullmatch(r"data\.(?:insert|update|delete|query)\.failed", normalized) is not None
        or ".redis." in normalized
    )


def is_event_fqn(value: str) -> bool:
    return normalize_datamodel_fqn(value).startswith("event.")


def data_model_access_kind(line: str, operation: str | None = None, use_mode: str | None = None) -> tuple[str, str]:
    haystack = line.lower()
    op = (operation or "").lower()
    mode = (use_mode or "").upper()
    analytics_tokens = ["olapforce", "bitmap_", "bitmap(", "usemode\":\"olap", "usemode\":\"htap", "usemode: olap", "usemode: htap"]
    if mode in {"OLAP", "HTAP"} or any(token in haystack for token in analytics_tokens):
        return "ANALYTICS_MODEL_QUERY", "analytics-sql"
    if op in {"fetch", "querybystream", "streamgetsn"} or "dataapiwebsocketsdk" in haystack or "asdataapiwebsocketsdk" in haystack:
        return "DATA_API_STREAM", "dataapi-stream-sql"
    return "DATA_API_CALL", "dataapi-sql"


def event_endpoint_kind(line: str) -> tuple[str, str, str]:
    lowered = line.lower()
    if any(token in lowered for token in ["publish", "sendevent", "sendevents", "event.of", "push("]):
        return "egress", "EVENT_BUS_PUBLISHER", "eventservice"
    return "egress", "DATA_EVENT_SCHEMA", "event-schema"


def dataapi_context(text: str, line: str) -> bool:
    combined = f"{text}\n{line}"
    return any(
        token in combined
        for token in [
            "DataapiHttpSdk",
            "DataapiWebSocketSdk",
            "DataApiSupport",
            "DataapiSdkFactory",
            "getDataapiSdk()",
            "dataapiSdk",
            "dataApiService",
            "DataApiSupport",
            "sqlSupport()",
            "ThreadLocalSqlSupport",
            "jobTaskSupport",
            "metaDataApiService",
            "MetadataSupport",
        ]
    )


def extract_dataapi_fqns(expr: str | None, root: Path, local_sql_fqns: dict[str, set[str]]) -> set[str]:
    if not expr:
        return set()
    expr = expr.strip().rstrip(";")
    fqns: set[str] = set()
    resolved = resolve_java_expr(expr, root)
    if resolved and is_datamodel_fqn(resolved):
        fqns.add(normalize_datamodel_fqn(resolved))
    if expr in local_sql_fqns:
        fqns.update(local_sql_fqns[expr])
    format_fqns: set[str] = set()
    for format_match in re.finditer(r'String\.format\s*\(\s*"((?:\\.|[^"\\])*)"', expr):
        format_fqn = normalize_datamodel_fqn(format_match.group(1))
        if is_datamodel_fqn(format_fqn):
            format_fqns.add(format_fqn)
    if expr.startswith("String.format"):
        start = expr.find("(")
        end = expr.rfind(")")
        args = split_java_args(expr[start + 1 : end] if start >= 0 and end > start else expr)
        if args:
            format_value = resolve_java_expr(args[0], root)
            if not format_value:
                format_value = first_annotation_string(args[0])
            if format_value:
                format_fqn = normalize_datamodel_fqn(format_value)
                if is_datamodel_fqn(format_fqn):
                    format_fqns.add(format_fqn)
        for arg in args[1:]:
            fqns.update(extract_dataapi_fqns(arg, root, local_sql_fqns))
            resolved_arg = resolve_java_expr(arg, root)
            if resolved_arg and is_datamodel_fqn(resolved_arg):
                fqns.add(normalize_datamodel_fqn(resolved_arg))
            if arg in local_sql_fqns:
                fqns.update(local_sql_fqns[arg])
    for match in DATA_FQN_LITERAL_RE.finditer(expr):
        fqn = normalize_datamodel_fqn(match.group(0))
        if is_datamodel_fqn(fqn):
            fqns.add(fqn)
    if format_fqns:
        fqns = {fqn for fqn in fqns if not any(full != fqn and full.startswith(fqn + ".") for full in format_fqns)}
        fqns.update(format_fqns)
    fqns = {fqn for fqn in fqns if not any(other != fqn and other.startswith(fqn + ".") for other in fqns)}
    return fqns


def local_string_fqn_bindings(text: str, root: Path) -> dict[str, set[str]]:
    bindings: dict[str, set[str]] = {}
    # Capture Java string variables/constants whose initializer contains a data/event FQN,
    # including common multi-line SQL constants built through string concatenation.
    for match in re.finditer(
        r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?String\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?);",
        text,
        re.IGNORECASE | re.S,
    ):
        name, expr = match.group(1), match.group(2)
        fqns = extract_dataapi_fqns(expr, root, bindings)
        if fqns:
            bindings[name] = fqns
    return bindings


def model_name_enum_fqns(root: Path) -> dict[str, str]:
    cache_key = str(root.resolve())
    if cache_key in _MODEL_NAME_ENUM_FQNS_BY_ROOT:
        return _MODEL_NAME_ENUM_FQNS_BY_ROOT[cache_key]
    mapping: dict[str, str] = {}
    for file in root.rglob("ModelNameEnum.java"):
        if is_always_excluded_source(file, root):
            continue
        try:
            lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            match = re.search(r"\b([A-Z][A-Z0-9_]*)\s*\(\s*\"(data\.[^\"]+)\"", stripped)
            if not match:
                continue
            enum_name = match.group(1).upper()
            fqn = normalize_datamodel_fqn(match.group(2))
            if is_datamodel_fqn(fqn):
                mapping[enum_name] = fqn
    _MODEL_NAME_ENUM_FQNS_BY_ROOT[cache_key] = mapping
    return mapping


def resolve_model_name_enum_fqn(root: Path, model_name: str) -> str | None:
    return model_name_enum_fqns(root).get(model_name.upper())


def is_oss_operation_context(receiver: str, line: str, file: Path) -> bool:
    combined = f"{receiver} {line} {file.as_posix()}".lower()
    return any(token in combined for token in ["oss", "aliyun", "bucket"])


def is_resolved_object_storage_target(bucket: str, object_key: str) -> bool:
    bucket_text = bucket.strip().strip("\"'")
    key_text = object_key.strip().strip("\"'")
    bucket_lower = bucket_text.lower()
    key_lower = key_text.lower()
    generic_bucket_tokens = {"bucket", "bucketname", "bucket_name", "oss_bucket"}
    generic_key_tokens = {"key", "objectkey", "object_key", "filename", "file_name", "dirname", "dir"}
    if not bucket_text or not key_text:
        return False
    if bucket_lower in generic_bucket_tokens or key_lower in generic_key_tokens:
        return False
    if "+" in bucket_text or "+" in key_text:
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", bucket_text) and bucket_lower in generic_bucket_tokens:
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_text) and key_lower in generic_key_tokens:
        return False
    if key_lower.startswith(("dir+", "dir +", "path+", "path +")):
        return False
    return True


def is_comment_or_import(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith(("*", "/*", "//", "#"))
        or stripped.startswith(("import ", "package "))
    )


def has_sql_context(line: str) -> bool:
    lower = line.lower()
    return any(
        token in lower
        for token in [
            "select ",
            " insert ",
            " update ",
            " delete ",
            "@select",
            "@update",
            "@insert",
            "@delete",
            "createquery",
            "nativequery",
            "jdbc",
            "sql",
        ]
    )


def has_db_table_context(line: str, file: Path) -> bool:
    lower = line.lower()
    if has_sql_context(line):
        return True
    if file.suffix.lower() == ".xml" and "mapper" in file.as_posix().lower():
        return any(token in lower for token in ["from ", " join ", "insert into ", "update ", "delete from "])
    return False


def file_integration_channel(line: str, file_contract: str, source_file: Path) -> str | None:
    lower = line.lower()
    contract_lower = file_contract.lower()
    source_lower = source_file.as_posix().lower()
    invalid_tokens = [
        "downloadutils.",
        "response",
        "export",
        "download",
        "template",
        "controller",
        "po.java",
        "vo.java",
        "dto.java",
        "file.separator",
        "classpathresource",
        "@getmapping",
        "mapper/",
        "mapper\\",
        "src/test/",
        "/test/",
        "trace",
        "log",
        "local",
        "c:\\users\\",
        "meta-inf/scripts/",
    ]
    if any(token in lower or token in contract_lower or token in source_lower for token in invalid_tokens):
        return None
    channel_tokens = {
        "oss": ["oss", "object key", "objectkey"],
        "s3": ["s3", "amazonaws"],
        "sftp": ["sftp", "ftp"],
        "shared_directory": ["shared directory", "share directory", "watch folder", "drop folder"],
        "partner_feed": ["partner", "vendor", "feed", "external"],
        "batch_exchange": ["batch exchange", "file exchange", "exchange file", "sync file", "data feed"],
    }
    combined = f"{lower} {contract_lower} {source_lower}"
    for channel, tokens in channel_tokens.items():
        if any(token in combined for token in tokens):
            return channel
    return None


def clean_path(path: str, convert_colon_params: bool = True) -> str:
    path = path.strip()
    if convert_colon_params:
        path = re.sub(r":([A-Za-z_]\w*)", r"{\1}", path)
    path = re.sub(r"<([A-Za-z_]\w*)>", r"{\1}", path)
    path = re.sub(r"\$\{([^}]+)\}", r"{\1}", path)
    path = re.sub(r"\{+([^{}]+)\}+", r"{\1}", path)
    return path


def clean_http_target(path: str) -> str:
    path = path.strip()
    path = re.sub(r"<([A-Za-z_]\w*)>", r"{\1}", path)
    path = re.sub(r"\$\{([^}]+)\}", r"{\1}", path)
    path = re.sub(r"\{+([^{}]+)\}+", r"{\1}", path)
    return path


def normalize_route_path(path: str, convert_colon_params: bool = True) -> str:
    cleaned = clean_path(path or "/", convert_colon_params=convert_colon_params).strip()
    if not cleaned:
        cleaned = "/"
    cleaned = cleaned.replace("\\", "/")
    cleaned = re.sub(r"/+", "/", cleaned)
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def normalize_http_target_path(path: str) -> str:
    cleaned = clean_http_target(path or "/").strip()
    if not cleaned:
        cleaned = "/"
    cleaned = cleaned.replace("\\", "/")
    cleaned = re.sub(r"/+", "/", cleaned)
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def normalize_openapi_route_path(path: str) -> str:
    cleaned = clean_http_target(path or "/").strip()
    if not cleaned:
        cleaned = "/"
    cleaned = cleaned.replace("\\", "/")
    cleaned = re.sub(r"/+", "/", cleaned)
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def join_route_paths(prefix: str | None, path: str | None, convert_colon_params: bool = True) -> str:
    left = normalize_route_path(prefix or "/", convert_colon_params=convert_colon_params)
    right = normalize_route_path(path or "/", convert_colon_params=convert_colon_params)
    if left == "/":
        return right
    if right == "/":
        return left
    return normalize_route_path(left + "/" + right.lstrip("/"), convert_colon_params=convert_colon_params)


def join_http_target_paths(prefix: str | None, path: str | None) -> str:
    left = normalize_http_target_path(prefix or "/")
    right = normalize_http_target_path(path or "/")
    if left == "/":
        return right
    if right == "/":
        return left
    return normalize_http_target_path(left + "/" + right.lstrip("/"))


def openapi_path_identifier_and_rule(method: str, raw_path: str) -> tuple[str, dict[str, Any]]:
    cleaned = clean_http_target(raw_path)
    base, query_params = split_query(cleaned)
    base = normalize_percent_placeholders(base)
    path = normalize_openapi_route_path(base)
    identifier = f"{method} {path}"
    match_rule: dict[str, Any] = {"type": "path_template", "method": method, "path": path}
    if query_params:
        match_rule["query_params"] = query_params
    variables = re.findall(r"\{([^}]+)\}", path)
    if variables:
        match_rule["template_variables"] = variables
    return identifier, match_rule


def is_spring_class_mapping(lines: list[str], index: int) -> bool:
    lookahead = "\n".join(lines[index : min(len(lines), index + 5)])
    return bool(re.search(r"\b(class|interface)\s+[A-Za-z_]\w*", lookahead))


def spring_mapping_paths(annotation: str, fallback: str | None = None) -> list[str]:
    paths = annotation_strings(annotation)
    if not paths and fallback is not None:
        paths = [fallback]
    if not paths:
        paths = ["/"]
    return [normalize_route_path(path or "/") for path in paths]


def spring_request_mapping_method(annotation: str, default: str = "ANY") -> str:
    match = SPRING_MAPPING_METHOD_RE.search(annotation)
    return match.group(1).upper() if match else default


def spring_class_prefixes(lines: list[str]) -> list[str]:
    pending: list[str] | None = None
    for idx, line in enumerate(lines):
        match = SPRING_ROUTE_RE.search(line)
        if match and match.group(1).lower() == "requestmapping":
            annotation = collect_annotation(lines, idx)
            pending = spring_mapping_paths(annotation, match.group(2))
            if is_spring_class_mapping(lines, idx):
                return pending
            continue
        if pending and re.search(r"\b(class|interface)\s+[A-Za-z_]\w*", line):
            return pending
        stripped = line.strip()
        if stripped and not stripped.startswith("@") and not stripped.startswith(("/*", "*", "//")):
            pending = None
    return ["/"]


SPRING_BOOT_APP_RE = re.compile(r"@SpringBootApplication|SpringApplication\.run\s*\(", re.IGNORECASE)
KTOR_SERVER_RE = re.compile(r"\bembeddedServer\s*\(|\bio\.ktor\.server\.|\bApplication\.module\s*\(", re.IGNORECASE)
MAVEN_COORD_RE = re.compile(r"<(groupId|artifactId|version)>([^<]+)</\1>", re.IGNORECASE)


def stable_id(direction: str, kind: str, identifier: str, rel_file: str, line: int, service: str | None = None) -> str:
    raw = f"{direction}|{kind}|{identifier}|{rel_file}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def endpoint(
    root: Path,
    file: Path,
    line: int,
    direction: str,
    kind: str,
    identifier: str,
    match_rule: dict[str, Any],
    evidence: str,
    confidence: float,
    framework: str | None = None,
    service: str | None = None,
    service_scope: str | None = None,
) -> dict[str, Any]:
    rel = file.relative_to(root).as_posix()
    return {
        "id": stable_id(direction, kind, identifier, rel, line, service),
        "direction": direction,
        "kind": kind,
        "identifier": identifier,
        "match_rule": match_rule,
        "owner": {
            "service": service,
            "module": rel.rsplit("/", 1)[0] if "/" in rel else None,
            "service_scope": service_scope,
        },
        "source": {"file": rel, "line": line, "symbol": None},
        "metadata": {
            "framework": framework,
            "operation": None,
            "confidence": confidence,
            "evidence": [evidence[:240]],
        },
    }


def iter_source_files(root: Path):
    ignored = {".git", ".cursor", "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__", "graphify-out"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignored]
        for name in filenames:
            if name.lower().startswith(".graphify"):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in ALLOWED_EXTENSIONS:
                yield path


def endpoint_identity(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    base = f"{item.get('direction')}|{kind}|{item.get('identifier')}"
    owner = item.get("owner") or {}
    if owner.get("service"):
        return f"{owner.get('service')}|{base}"
    return base


def source_ref(item: dict[str, Any]) -> str:
    source = item.get("source") or {}
    return f"{source.get('file')}:{source.get('line')}"


def merge_endpoint(existing: dict[str, Any], item: dict[str, Any]) -> None:
    existing_meta = existing.setdefault("metadata", {})
    item_meta = item.get("metadata") or {}
    existing_evidence = existing_meta.setdefault("evidence", [])
    for evidence in item_meta.get("evidence") or []:
        if evidence not in existing_evidence and len(existing_evidence) < 20:
            existing_evidence.append(evidence)
    refs = existing_meta.setdefault("source_refs", [])
    for ref in [source_ref(existing), source_ref(item)]:
        if ref not in refs and len(refs) < 40:
            refs.append(ref)
    existing_meta["evidence_count"] = int(existing_meta.get("evidence_count") or len(existing_evidence)) + 1
    item_conf = endpoint_confidence(item)
    existing_conf = endpoint_confidence(existing)
    if item_conf > existing_conf:
        existing["source"] = item.get("source", existing.get("source"))
        existing["match_rule"] = item.get("match_rule", existing.get("match_rule"))
        existing_meta["confidence"] = item_conf
        existing_meta["framework"] = item_meta.get("framework", existing_meta.get("framework"))
    existing_owner = existing.get("owner") or {}
    item_owner = item.get("owner") or {}
    fanout = existing_meta.setdefault("service_fanout", [])
    for owner in (existing_owner, item_owner):
        service_name = owner.get("service")
        service_scope = owner.get("service_scope")
        if service_name:
            value = {"service": service_name, "service_scope": service_scope}
            if value not in fanout:
                fanout.append(value)
    if item_owner.get("service_scope") == "runtime" and existing_owner.get("service_scope") != "runtime":
        existing_owner["service_scope"] = "runtime"
        existing["owner"] = existing_owner


def add_unique(seen: dict[str, int], endpoints: list[dict[str, Any]], item: dict[str, Any]) -> None:
    key = endpoint_identity(item)
    if key in seen:
        merge_endpoint(endpoints[seen[key]], item)
        return
    seen[key] = len(endpoints)
    metadata = item.setdefault("metadata", {})
    metadata["evidence_count"] = 1
    metadata["source_refs"] = [source_ref(item)]
    owner = item.get("owner") or {}
    if owner.get("service"):
        metadata["service_fanout"] = [{"service": owner.get("service"), "service_scope": owner.get("service_scope")}]
    endpoints.append(item)


def scan_model_metadata_json(
    root: Path,
    file: Path,
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    try:
        data = json.loads(file.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return

    emit_model_schema = not is_static_model_schema_source(file)

    def emit_datamodel_fqn(fqn: str, evidence_prefix: str = "model.fqn", use_mode: str | None = None) -> None:
        fqn = normalize_datamodel_fqn(fqn)
        if not is_datamodel_fqn(fqn):
            return
        if is_event_fqn(fqn):
            direction, kind, evidence_kind = "egress", "DATA_EVENT_SCHEMA", "event-schema"
            match_rule = {"type": "data_event", "event": fqn, "source_kind": "event_schema"}
        else:
            if not emit_model_schema:
                return
            direction, kind, evidence_kind = "egress", "DATA_MODEL_SCHEMA", "model-schema"
            match_rule = {"type": "data_model_schema", "fqn": fqn, "source_kind": "model_metadata"}
            if use_mode:
                match_rule["use_mode"] = use_mode
        add_unique(
            seen,
            endpoints,
            endpoint(
                root,
                file,
                1,
                direction,
                kind,
                fqn,
                match_rule,
                f"{evidence_prefix} {fqn}",
                0.9,
                evidence_kind,
                service,
                service_scope,
            ),
        )

    def walk_fqn_fields(value: Any) -> None:
        if isinstance(value, dict):
            local_use_mode = value.get("useMode") if isinstance(value.get("useMode"), str) else None
            for key, item in value.items():
                if key in {"fqn", "mainModelFqn", "refModelFqn", "enumModelFqn"} and isinstance(item, str):
                    emit_datamodel_fqn(item, key, local_use_mode)
                else:
                    walk_fqn_fields(item)
        elif isinstance(value, list):
            for item in value:
                walk_fqn_fields(item)

    walk_fqn_fields(data)

    script_content = data.get("scriptContent") if isinstance(data, dict) else None
    if not isinstance(script_content, dict):
        return
    physical_meta = script_content.get("physicalMeta")
    tables = physical_meta.get("tables") if isinstance(physical_meta, dict) else None
    if isinstance(tables, dict):
        for model_key, table_spec in tables.items():
            if not isinstance(table_spec, dict):
                continue
            raw_table = table_spec.get("tableName")
            if not isinstance(raw_table, str) or not raw_table.strip():
                continue
            identifier, match_rule = normalize_table_identifier(raw_table)
            match_rule["source_kind"] = "model_metadata"
            if isinstance(model_key, str) and model_key:
                match_rule["model_key"] = model_key
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    1,
                    "egress",
                    "DB_TABLE",
                    identifier,
                    match_rule,
                    f"physicalMeta.tables tableName {raw_table}",
                    0.95,
                    "model-metadata",
                    service,
                    service_scope,
                ),
            )


def looks_like_openapi_contract(file: Path, text: str) -> bool:
    if file.suffix.lower() not in {".yaml", ".yml", ".json"}:
        return False
    lower_name = file.name.lower()
    normalized = file.as_posix().lower()
    if not any(token in lower_name or token in normalized for token in ["openapi", "swagger"]):
        return False
    return bool(re.search(r"(?m)^\s*(?:openapi|swagger)\s*:\s*", text) and re.search(r"(?m)^\s*paths\s*:\s*", text))


def scan_openapi_contract(
    root: Path,
    file: Path,
    lines: list[str],
    text: str,
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    if not looks_like_openapi_contract(file, text):
        return
    current_path: str | None = None
    path_indent = -1
    in_paths = False
    paths_indent = -1
    for idx, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top_match = re.match(r"^(\s*)([A-Za-z_][\w-]*)\s*:\s*", line)
        if top_match and len(top_match.group(1)) <= paths_indent and top_match.group(2).lower() != "paths":
            in_paths = False
            current_path = None
        if re.match(r"^(\s*)paths\s*:\s*(?:#.*)?$", line):
            in_paths = True
            paths_indent = len(re.match(r"^(\s*)", line).group(1))
            current_path = None
            continue
        if not in_paths:
            continue
        path_match = OPENAPI_PATH_RE.match(line)
        if path_match:
            current_path = path_match.group(2).strip()
            path_indent = len(path_match.group(1))
            continue
        method_match = OPENAPI_METHOD_RE.match(line)
        if current_path and method_match and len(method_match.group(1)) > path_indent:
            method = method_match.group(2).upper()
            identifier, match_rule = openapi_path_identifier_and_rule(method, current_path)
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "ingress",
                    "HTTP_API",
                    identifier,
                    match_rule,
                    line.strip(),
                    0.86,
                    "openapi-contract",
                    service,
                    service_scope,
                ),
            )


def jaxrs_or_retrofit_contract_base(text: str) -> tuple[str | None, str | None]:
    """Return a client/base path for Java/Kotlin HTTP client interfaces."""
    retrofit_match = RETROFIT_SERVICE_RE.search(text)
    if retrofit_match:
        values = annotation_strings(retrofit_match.group(1))
        if values:
            service_name = values[0]
            version = values[1] if len(values) > 1 else None
            base = "{" + service_name + "}"
            if version:
                base = join_route_paths(base, version)
            return base, service_name
    feign_match = FEIGN_CLIENT_RE.search(text)
    client_name = None
    feign_base_path = None
    if feign_match:
        args = feign_match.group(1)
        client_name = first_annotation_string(annotation_attr(args, "name") or annotation_attr(args, "value") or args)
        feign_base_path = first_annotation_string(annotation_attr(args, "path") or "")
    class_prefix = ""
    for idx, line in enumerate(text.splitlines()):
        stripped = line.strip()
        path_match = JAXRS_PATH_RE.search(stripped) if stripped.startswith("@Path") else None
        if not path_match:
            continue
        lookahead = "\n".join(text.splitlines()[idx : min(len(text.splitlines()), idx + 5)])
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", lookahead):
            class_prefix = path_match.group(1)
            break
    return class_prefix or feign_base_path or None, client_name


def scan_java_http_client_contracts(
    root: Path,
    file: Path,
    lines: list[str],
    text: str,
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    if file.suffix.lower() not in {".java", ".kt"} or not is_java_http_client_contract(text):
        return
    base_path, client_name = jaxrs_or_retrofit_contract_base(text)
    pending_path: str | None = None
    pending_method: str | None = None
    pending_evidence: str | None = None
    in_contract_type = False
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
            in_contract_type = True
            continue
        if not in_contract_type:
            continue
        retrofit_match = RETROFIT_HTTP_METHOD_RE.search(stripped)
        if retrofit_match:
            pending_method = retrofit_match.group(1).upper()
            pending_path = retrofit_match.group(2)
            pending_evidence = stripped
            continue
        spring_match = SPRING_ROUTE_RE.search(stripped)
        if spring_match:
            mapping = spring_match.group(1).lower()
            pending_method = {
                "getmapping": "GET",
                "postmapping": "POST",
                "putmapping": "PUT",
                "patchmapping": "PATCH",
                "deletemapping": "DELETE",
                "requestmapping": spring_request_mapping_method(stripped),
            }[mapping]
            paths = spring_mapping_paths(stripped, spring_match.group(2))
            pending_path = paths[0] if paths else ""
            pending_evidence = stripped
            continue
        path_match = JAXRS_PATH_RE.search(stripped) if stripped.startswith("@Path") else None
        if path_match:
            pending_path = path_match.group(1)
            pending_evidence = stripped
            continue
        method_match = JAXRS_HTTP_METHOD_RE.search(stripped)
        if method_match:
            pending_method = method_match.group(1).upper()
            pending_evidence = f"{pending_evidence or ''} {stripped}".strip()
            continue
        if pending_method and re.search(r"\b(?:fun\s+|[A-Za-z_][A-Za-z0-9_<>, ?]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\()", stripped):
            path = join_http_target_paths(base_path or "", pending_path or "")
            if path and not path.startswith("{"):
                path = normalize_http_target_path(path)
            identifier, match_rule = http_call_identifier_and_rule(pending_method, path, client_name or "http-client-interface")
            if client_name:
                match_rule["target_service"] = client_name
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "egress",
                    "HTTP_CALL",
                    identifier,
                    match_rule,
                    pending_evidence or stripped,
                    0.82,
                    "feign-retrofit-client",
                    service,
                    service_scope,
                ),
            )
            pending_path = None
            pending_method = None
            pending_evidence = None


def scan_jaxrs_server_routes(
    root: Path,
    file: Path,
    lines: list[str],
    text: str,
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    if file.suffix.lower() not in {".java", ".kt"} or is_java_http_client_contract(text):
        return
    if not JAXRS_PATH_RE.search(text) or not JAXRS_HTTP_METHOD_RE.search(text):
        return
    class_path = ""
    for idx, line in enumerate(lines):
        path_match = JAXRS_PATH_RE.search(line)
        if not path_match:
            continue
        lookahead = "\n".join(lines[idx : min(len(lines), idx + 5)])
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", lookahead):
            class_path = path_match.group(1)
            break
    in_resource_type = False
    pending_path: str | None = None
    pending_method: str | None = None
    pending_evidence: str | None = None
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
            in_resource_type = True
            continue
        if not in_resource_type:
            continue
        path_match = JAXRS_PATH_RE.search(stripped) if stripped.startswith("@Path") else None
        if path_match:
            pending_path = path_match.group(1)
            pending_evidence = stripped
            continue
        method_match = JAXRS_HTTP_METHOD_RE.search(stripped)
        if method_match:
            pending_method = method_match.group(1).upper()
            pending_evidence = f"{pending_evidence or ''} {stripped}".strip()
            continue
        if pending_method and re.search(r"\b(?:fun\s+|[A-Za-z_][A-Za-z0-9_<>, ?]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\()", stripped):
            path = join_route_paths(class_path or "", pending_path or "", convert_colon_params=False)
            identifier, match_rule = http_path_identifier_and_rule(pending_method, path, convert_colon_params=False)
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "ingress",
                    "HTTP_API",
                    identifier,
                    match_rule,
                    pending_evidence or stripped,
                    0.82,
                    "jax-rs",
                    service,
                    service_scope,
                ),
            )
            pending_path = None
            pending_method = None
            pending_evidence = None


def scan_spring_cloud_stream_contracts(
    root: Path,
    file: Path,
    lines: list[str],
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    if file.suffix.lower() in {".yaml", ".yml", ".properties"}:
        if file.suffix.lower() == ".properties":
            for idx, line in enumerate(lines, start=1):
                match = re.search(r"spring\.cloud\.stream\.bindings\.([A-Za-z0-9_.-]+)\.destination\s*=\s*(.+)", line)
                if not match:
                    continue
                binding, raw_destination = match.group(1), match.group(2)
                direction_kind = None
                if re.search(r"-out-\d+$", binding):
                    direction_kind = ("egress", "MESSAGE_PRODUCER", "spring-cloud-stream-binding-output")
                elif re.search(r"-in-\d+$", binding):
                    direction_kind = ("ingress", "MESSAGE_CONSUMER", "spring-cloud-stream-binding-input")
                if not direction_kind:
                    continue
                topic = normalize_message_identifier(clean_path(raw_destination.strip()))
                if topic:
                    direction, kind, evidence_kind = direction_kind
                    add_unique(seen, endpoints, endpoint(root, file, idx, direction, kind, topic, {"type": "topic", "broker": "spring-cloud-stream", "topic": topic, "binding": binding}, line.strip(), 0.78, evidence_kind, service, service_scope))
            return

        current_binding: str | None = None
        current_indent: int | None = None
        for idx, line in enumerate(lines, start=1):
            binding_match = re.match(r"^(\s*)([A-Za-z0-9_.-]+-(?:out|in)-\d+)\s*:\s*$", line)
            if binding_match:
                current_binding = binding_match.group(2)
                current_indent = len(binding_match.group(1))
                continue
            if current_binding is not None and current_indent is not None:
                if line.strip() and len(line) - len(line.lstrip(" ")) <= current_indent:
                    current_binding = None
                    current_indent = None
                    continue
                dest_match = re.match(r"^\s*destination\s*:\s*(.+?)\s*$", line)
                if not dest_match:
                    continue
                direction_kind = ("egress", "MESSAGE_PRODUCER", "spring-cloud-stream-binding-output") if "-out-" in current_binding else ("ingress", "MESSAGE_CONSUMER", "spring-cloud-stream-binding-input")
                topic = normalize_message_identifier(clean_path(dest_match.group(1).strip().strip("\"'")))
                if topic:
                    direction, kind, evidence_kind = direction_kind
                    add_unique(seen, endpoints, endpoint(root, file, idx, direction, kind, topic, {"type": "topic", "broker": "spring-cloud-stream", "topic": topic, "binding": current_binding}, line.strip(), 0.78, evidence_kind, service, service_scope))
        return

    if file.suffix.lower() not in {".java", ".kt"}:
        return
    output_methods = stream_output_methods(root)
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        for match in STREAM_INPUT_RE.finditer(stripped):
            owner_type = enclosing_type_name(lines, idx, file.stem)
            channel = resolve_stream_channel(match.group(1), root, owner_type)
            if channel:
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", channel, {"type": "topic", "broker": "spring-cloud-stream", "topic": channel}, stripped, 0.82, "spring-cloud-stream-input", service, service_scope))
        for match in STREAM_LISTENER_RE.finditer(stripped):
            owner_type = enclosing_type_name(lines, idx, file.stem)
            channel = resolve_stream_channel(match.group(1), root, owner_type)
            if channel:
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", channel, {"type": "topic", "broker": "spring-cloud-stream", "topic": channel}, stripped, 0.86, "spring-cloud-stream-listener", service, service_scope))
        for match in STREAM_OUTPUT_RE.finditer(stripped):
            owner_type = enclosing_type_name(lines, idx, file.stem)
            channel = resolve_stream_channel(match.group(1), root, owner_type)
            if channel:
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "MESSAGE_PRODUCER", channel, {"type": "topic", "broker": "spring-cloud-stream", "topic": channel}, stripped, 0.82, "spring-cloud-stream-output", service, service_scope))
        for match in STREAM_SEND_RE.finditer(stripped):
            channel = output_methods.get(match.group(1))
            if channel:
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "MESSAGE_PRODUCER", channel, {"type": "topic", "broker": "spring-cloud-stream", "topic": channel, "binding_method": match.group(1)}, stripped, 0.86, "spring-cloud-stream-send", service, service_scope))


def scan_file(
    root: Path,
    file: Path,
    seen: dict[str, int],
    endpoints: list[dict[str, Any]],
    service: str | None = None,
    service_scope: str | None = None,
) -> None:
    if is_always_excluded_source(file, root):
        return
    if is_model_metadata_json(file):
        scan_model_metadata_json(root, file, seen, endpoints, service, service_scope)
    try:
        text = file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    if file.suffix.lower() == ".xml":
        text = strip_xml_comments_preserve_lines(text)
    lines = text.splitlines()
    scan_openapi_contract(root, file, lines, text, seen, endpoints, service, service_scope)
    scan_java_http_client_contracts(root, file, lines, text, seen, endpoints, service, service_scope)
    scan_jaxrs_server_routes(root, file, lines, text, seen, endpoints, service, service_scope)
    scan_spring_cloud_stream_contracts(root, file, lines, seen, endpoints, service, service_scope)
    spring_prefixes = spring_class_prefixes(lines) if file.suffix.lower() in {".java", ".kt"} else ["/"]
    java_http_client_contract = file.suffix.lower() in {".java", ".kt"} and is_java_http_client_contract(text)
    java_type = java_type_name(text, file.stem)
    java_http_url_vars: dict[str, str] = {}
    java_message_topics: dict[str, tuple[str, dict[str, Any]]] = {}
    java_message_topic_sets: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    java_map_topic_keys: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    kafka_consume_services: dict[str, dict[str, Any]] = {}
    java_var_types: dict[str, str] = {}
    local_dataapi_sql_fqns: dict[str, set[str]] = local_string_fqn_bindings(text, root)
    local_cache_vars: dict[str, tuple[str, dict[str, Any]]] = local_redis_key_builders(text, root)
    current_java_method: str | None = None
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*")):
            continue
        annotation = collect_annotation(lines, idx - 1) if stripped.startswith("@") else stripped
        if file.suffix.lower() in {".java", ".kt"}:
            method_match = JAVA_METHOD_DECL_RE.search(line)
            if method_match and method_match.group(1) not in {"if", "for", "while", "switch", "catch"}:
                current_java_method = method_match.group(1)
            for var_match in JAVA_VARIABLE_DECL_RE.finditer(line):
                var_type, var_name = var_match.group(1), var_match.group(2)
                if var_type not in {"String", "List", "Map", "Set", "Optional"}:
                    java_var_types[var_name] = var_type
            for assign_match in JAVA_STRING_ASSIGN_RE.finditer(line):
                var_name, expr = assign_match.group(1), assign_match.group(2)
                topic, topic_meta = resolve_java_message_topic_expr(expr, root, java_message_topics)
                if topic and (re.search(r"(topic|queue|event|message)", var_name, re.IGNORECASE) or re.search(r"(topic|queue|event|message|job)", topic, re.IGNORECASE)):
                    java_message_topics[var_name] = (topic, topic_meta)
                cache_key = resolve_cache_key_expr(expr, root, local_cache_vars)
                if cache_key and re.search(r"(cache|key|lock|offset)", var_name, re.IGNORECASE):
                    local_cache_vars[var_name] = cache_key
            for add_match in JAVA_COLLECTION_ADD_RE.finditer(line):
                collection_name, expr = add_match.group(1), add_match.group(2)
                if not re.search(r"(topic|queue|event|message)", collection_name, re.IGNORECASE):
                    continue
                topic, topic_meta = resolve_java_message_topic_expr(expr, root, java_message_topics)
                if topic:
                    java_message_topic_sets[collection_name].append((topic, topic_meta))
            for map_match in JAVA_MAP_PUT_RE.finditer(line):
                map_name, arg_text = map_match.group(1), map_match.group(2)
                args = split_java_args(arg_text)
                if len(args) < 2:
                    continue
                key_topic, key_meta = resolve_java_message_topic_expr(args[0], root, java_message_topics)
                value_topic, value_meta = resolve_java_message_topic_expr(args[1], root, java_message_topics)
                if key_topic:
                    java_map_topic_keys[map_name].append((key_topic, {**key_meta, "source_kind": "map_topic_key"}))
                if value_topic:
                    get_key = f"{map_name}.get({re.sub(r'\\s+', '', args[0])})"
                    java_message_topics[get_key] = (value_topic, {**value_meta, "source_kind": "map_topic_value"})
            for keyset_match in JAVA_MAP_KEYSET_FOREACH_RE.finditer(line):
                map_name, var_name = keyset_match.group(1), keyset_match.group(2)
                if java_map_topic_keys.get(map_name):
                    java_message_topic_sets[var_name].extend(java_map_topic_keys[map_name])
            for dataapi_sql_match in DATAAPI_SQL_ASSIGN_RE.finditer(line):
                var_name, expr = dataapi_sql_match.group(1), dataapi_sql_match.group(2)
                fqns = extract_dataapi_fqns(expr, root, local_dataapi_sql_fqns)
                if fqns:
                    local_dataapi_sql_fqns[var_name] = fqns
            for match in JAVA_GET_API_URL_ASSIGN_RE.finditer(line):
                var_name = match.group(1)
                path = resolve_java_expr(match.group(2), root)
                if path and path.startswith("/"):
                    java_http_url_vars[var_name] = path
            for match in JAVA_CONFIG_GETTER_ASSIGN_RE.finditer(line):
                var_name, owner, getter, path_expr = match.group(1), match.group(2), match.group(3), match.group(4)
                if getter.lower() == "getapiurl" or not looks_like_config_provider(owner):
                    continue
                path = resolve_java_expr(path_expr, root) if path_expr else None
                java_http_url_vars[var_name] = config_placeholder_with_path(owner, java_getter_property(getter), path)
            for match in JAVA_MAP_LOOKUP_ASSIGN_RE.finditer(line):
                var_name, source_var, dynamic_key = match.group(1), match.group(2), match.group(3)
                source_placeholder = java_http_url_vars.get(source_var)
                if source_placeholder and source_placeholder.startswith("{") and source_placeholder.endswith("}"):
                    java_http_url_vars[var_name] = source_placeholder[:-1] + f"[{dynamic_key}]" + "}"
            if dataapi_context(text, line):
                for dataapi_match in DATAAPI_CALL_RE.finditer(line):
                    operation = dataapi_match.group(1)
                    arg_text = dataapi_match.group(2)
                    args = split_java_args(arg_text)
                    if not args:
                        continue
                    fqns = extract_dataapi_fqns(args[0], root, local_dataapi_sql_fqns)
                    if not fqns:
                        fqns = extract_dataapi_fqns(arg_text, root, local_dataapi_sql_fqns)
                    op_lower = operation.lower()
                    sql_proxy_ops = {"execute", "query", "commonsqlexecute", "commonsqlexecutewithaffectedrows", "commonquerysql", "querybystream", "streamgetsn", "executesql"}
                    direct_model_ops = {"importdata", "mergedata", "batchmergemodel", "batchinsertmodel", "batchinsert", "savecustomer"}
                    if op_lower in sql_proxy_ops:
                        kind, access_mode = data_model_access_kind(line, operation)
                        match_type = "data_model_sql" if kind == "ANALYTICS_MODEL_QUERY" else "dataapi_model"
                        source_kind = "analytics_sql" if kind == "ANALYTICS_MODEL_QUERY" else "dataapi_sql"
                    else:
                        kind = "DATA_API_STREAM" if op_lower == "fetch" or "dataapiWebSocketSdk" in line or "asDataapiWebSocketSdk" in line else "DATA_API_CALL"
                        access_mode = "dataapi-websocket" if kind == "DATA_API_STREAM" else "dataapi-http"
                        match_type = "dataapi_model"
                        source_kind = "dataapi_call" if op_lower in direct_model_ops else "dataapi_call"
                    for fqn in fqns:
                        if is_event_fqn(fqn):
                            direction, event_kind, evidence_kind = event_endpoint_kind(line)
                            add_unique(
                                seen,
                                endpoints,
                        endpoint(
                            root,
                            file,
                            idx,
                            direction,
                            event_kind,
                            fqn,
                                    {
                                        "type": "event" if event_kind in {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} else "data_event",
                                        "event": fqn,
                                        "source_kind": "dataapi_event_reference",
                                        **({"bus": "eventservice"} if event_kind in {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} else {}),
                                    },
                            stripped,
                            0.78,
                            evidence_kind,
                                    service,
                                    service_scope,
                                ),
                            )
                            continue
                        add_unique(
                            seen,
                            endpoints,
                            endpoint(
                                root,
                                file,
                                idx,
                                "egress",
                                kind,
                                fqn,
                                {
                                    "type": match_type,
                                    "fqn": fqn,
                                    "operation": operation,
                                    "access_mode": access_mode,
                                    "source_kind": source_kind,
                                    **({"query_language": "SQL"} if source_kind in {"dataapi_sql", "analytics_sql"} else {}),
                                },
                                stripped,
                                0.84 if kind == "ANALYTICS_MODEL_QUERY" else 0.86,
                                "dataapi-sql" if source_kind in {"dataapi_sql", "analytics_sql"} else "dataapi",
                                service,
                                service_scope,
                            ),
                        )
            for schema_match in DATA_MODEL_SCHEMA_CALL_RE.finditer(line):
                operation = schema_match.group(1)
                args = split_java_args(schema_match.group(2))
                if not args:
                    continue
                fqns = extract_dataapi_fqns(args[0], root, local_dataapi_sql_fqns)
                for fqn in fqns:
                    if is_event_fqn(fqn):
                        continue
                    add_unique(
                        seen,
                        endpoints,
                        endpoint(
                            root,
                            file,
                            idx,
                            "egress",
                            "DATA_MODEL_SCHEMA",
                            fqn,
                            {
                                "type": "data_model_schema",
                                "fqn": fqn,
                                "operation": operation,
                                "source_kind": "metadata_api_call",
                            },
                            stripped,
                            0.84,
                            "model-schema",
                            service,
                            service_scope,
                        ),
                    )
        for match in ROUTE_DECORATOR_RE.finditer(line):
            method = match.group(1).upper()
            path = clean_path(match.group(2))
            if method == "ROUTE":
                method = "ANY"
            identifier, match_rule = http_path_identifier_and_rule(method, path)
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "HTTP_API", identifier, match_rule, stripped, 0.86, "python-route", service, service_scope))
        for match in FASTAPI_DECORATOR_RE.finditer(line):
            method = match.group(1).upper()
            identifier, match_rule = http_path_identifier_and_rule(method, match.group(2))
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "HTTP_API", identifier, match_rule, stripped, 0.88, "fastapi", service, service_scope))
        for match in EXPRESS_ROUTE_RE.finditer(line):
            method = match.group(1).upper()
            identifier, match_rule = http_path_identifier_and_rule(method, match.group(2))
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "HTTP_API", identifier, match_rule, stripped, 0.84, "express", service, service_scope))
        for match in SPRING_ROUTE_RE.finditer(line):
            mapping = match.group(1).lower()
            if mapping == "requestmapping" and is_spring_class_mapping(lines, idx - 1):
                continue
            method = {
                "getmapping": "GET",
                "postmapping": "POST",
                "putmapping": "PUT",
                "patchmapping": "PATCH",
                "deletemapping": "DELETE",
                "requestmapping": spring_request_mapping_method(annotation),
            }[mapping]
            local_paths = spring_mapping_paths(annotation, match.group(2))
            for local_path in local_paths:
                for spring_prefix in spring_prefixes:
                    path = join_route_paths(spring_prefix, local_path)
                    if java_http_client_contract:
                        identifier, match_rule = http_call_identifier_and_rule(method, path, "java-http-client-interface")
                        add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "HTTP_CALL", identifier, match_rule, stripped, 0.76, "spring-client-mapping", service, service_scope))
                    else:
                        identifier, match_rule = http_path_identifier_and_rule(method, path)
                        add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "HTTP_API", identifier, match_rule, stripped, 0.82, "spring", service, service_scope))
        if "WxCpApiPathConsts.Message.MESSAGE_SEND" in line:
            identifier, match_rule = http_call_identifier_and_rule("POST", "/cgi-bin/message/send", "WxCpMessageClient.send")
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "egress",
                    "HTTP_CALL",
                    identifier,
                    match_rule,
                    stripped,
                    0.82,
                    "weixin-cp-sdk",
                    service,
                    service_scope,
                ),
            )
        for match in FEIGN_CLIENT_RE.finditer(annotation):
            # Feign class-level host/baseUrl is client metadata, not an endpoint.
            # Concrete method mappings in the same interface are emitted as HTTP_CALL.
            continue
        for match in RETROFIT_SERVICE_RE.finditer(annotation):
            # Retrofit class-level host/contextPath is client metadata, not an
            # endpoint. Emit only concrete method routes.
            continue
        for match in HTTP_CALL_RE.finditer(line):
            if not is_http_call_literal_candidate(match.group(1)):
                continue
            identifier, match_rule = http_call_identifier_and_rule(None, match.group(1), "http-client")
            add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "HTTP_CALL", identifier, match_rule, stripped, 0.78, "http-client", service, service_scope))
        for match in REST_WRAPPER_CALL_RE.finditer(line):
            if re.search(r"\b(public|private|protected)\b.*\brest(?:Get|Post|Put|Delete|Patch)\s*\(", line):
                continue
            if not java_expr_is_literal_or_constant(match.group(2), root):
                continue
            method = http_method_from_rest_wrapper(match.group(1))
            target = resolve_java_expr(match.group(2), root)
            identifier, match_rule = http_call_identifier_and_rule(method, target or "", "rest-wrapper")
            if identifier:
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "HTTP_CALL",
                        identifier,
                        match_rule,
                        stripped,
                        0.7 if target and target.startswith("/") else 0.62,
                        "rest-wrapper",
                        service,
                        service_scope,
                    ),
                )
        for match in PROJECT_HTTP_RESPONSE_CALL_RE.finditer(line):
            method = http_method_from_project_response_call(match.group(1))
            target_expr = match.group(2).strip()
            target = java_http_url_vars.get(target_expr) or resolve_java_expr(target_expr, root)
            if not target or not target.startswith(("/", "http://", "https://", "{")):
                if current_java_method:
                    target = config_placeholder(java_type, current_java_method)
                else:
                    continue
            identifier, match_rule = http_call_identifier_and_rule(method, target, "project-http-wrapper")
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "egress",
                    "HTTP_CALL",
                    identifier,
                    match_rule,
                    stripped,
                    0.78,
                    "project-http-wrapper",
                    service,
                    service_scope,
                ),
            )
        for match in HTTP_URL_RE.finditer(line):
            if has_http_client_context(line):
                identifier, match_rule = http_call_identifier_and_rule(None, match.group(1), "http-url")
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "HTTP_CALL", identifier, match_rule, stripped, 0.7, "http-url", service, service_scope))
        for match in KAFKA_CONSUMER_RE.finditer(line):
            topic = match.group(1)
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", topic, {"type": "topic", "topic": topic}, stripped, 0.8, "message", service, service_scope))
        for match in KAFKA_CONSUME_SERVICE_RE.finditer(line):
            args_text = extract_call_args_after(line, match.start())
            args = split_java_args(args_text or "")
            if not args:
                continue
            topics = resolve_java_message_topic_entries_expr(args[0], root, java_message_topics, java_message_topic_sets)
            topics = narrow_topic_entries_by_contains_branch(lines, idx, topics, root)
            if not topics:
                continue
            service_var = match.group(1) or "KafkaConsumeService"
            kafka_consume_services[service_var] = {
                "topics": topics,
                "group": resolve_java_expr(args[1], root) if len(args) > 1 else None,
                "raw_args": args_text,
            }
            for topic, topic_meta in topics:
                match_rule = {
                    "type": "topic",
                    "broker": "kafka",
                    "topic": topic,
                    "group": resolve_java_expr(args[1], root) if len(args) > 1 else None,
                    "source_kind": "kafka_consume_service_constructor",
                    **topic_meta,
                }
                add_unique(
                    seen,
                    endpoints,
                    endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", topic, match_rule, stripped, 0.8, "kafka-consume-service", service, service_scope),
                )
        for match in KAFKA_SERVICE_CONSUME_RE.finditer(line):
            service_var = match.group(1)
            consume_info = kafka_consume_services.get(service_var)
            if not consume_info:
                continue
            for topic, topic_meta in consume_info.get("topics") or []:
                match_rule = {
                    "type": "topic",
                    "broker": "kafka",
                    "topic": topic,
                    "group": consume_info.get("group"),
                    "source_kind": "kafka_consume_service_consume",
                    **topic_meta,
                }
                add_unique(
                    seen,
                    endpoints,
                    endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", topic, match_rule, stripped, 0.86, "kafka-consume-service", service, service_scope),
                )
        for match in KAFKA_SUBSCRIBE_VAR_RE.finditer(line):
            topic_var = match.group(1)
            topic_entries: list[tuple[str, dict[str, Any]]] = []
            if topic_var in java_message_topic_sets:
                topic_entries.extend(java_message_topic_sets[topic_var])
            if topic_var in java_message_topics:
                topic_entries.append(java_message_topics[topic_var])
            for topic, topic_meta in topic_entries:
                match_rule = {
                    "type": "topic",
                    "broker": "kafka",
                    "topic": topic,
                    "source_kind": "resolved_subscribe_variable",
                    **topic_meta,
                }
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "ingress",
                        "MESSAGE_CONSUMER",
                        topic,
                        match_rule,
                        stripped,
                        0.78,
                        "kafka-consumer",
                        service,
                        service_scope,
                    ),
                )
        kafka_listener = re.search(r"@KafkaListener\s*\((.*?)\)", annotation, re.IGNORECASE | re.S)
        if kafka_listener:
            args = kafka_listener.group(1)
            topic_expr = annotation_attr(args, "topics") or annotation_attr(args, "topic") or annotation_attr(args, "value")
            topic = normalize_message_identifier(resolve_java_expr(topic_expr, root))
            if topic:
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "ingress",
                        "MESSAGE_CONSUMER",
                        topic,
                        {"type": "topic", "broker": "kafka", "topic": topic},
                        annotation,
                        0.84,
                        "kafka-listener",
                        service,
                        service_scope,
                    ),
                )
        for match in RABBIT_LISTENER_RE.finditer(annotation):
            args = match.group(1)
            queue_expr = annotation_attr(args, "queues") or annotation_attr(args, "queue") or annotation_attr(args, "value")
            queue = normalize_message_identifier(resolve_java_expr(queue_expr, root))
            if queue:
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "ingress",
                        "MESSAGE_CONSUMER",
                        queue,
                        {"type": "topic", "broker": "rabbitmq", "queue": queue},
                        annotation,
                        0.84,
                        "rabbitmq-listener",
                        service,
                        service_scope,
                    ),
                )
        if TASK_CONSUMER_RE.search(line):
            name = Path(file).stem
            identifier = f"{name}.task"
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "MESSAGE_CONSUMER", identifier, {"type": "task_decorator", "name": identifier}, stripped, 0.58, "task-queue", service, service_scope))
        for match in RABBIT_PRODUCER_ANNOTATION_RE.finditer(annotation):
            args = match.group(1)
            queue = normalize_message_identifier(resolve_java_expr(annotation_attr(args, "queue"), root))
            routing_key = normalize_message_identifier(resolve_java_expr(annotation_attr(args, "routingKey"), root))
            exchange = normalize_message_identifier(resolve_java_expr(annotation_attr(args, "exchange"), root))
            identifier = queue or routing_key
            if identifier:
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "MESSAGE_PRODUCER",
                        identifier,
                        {"type": "topic", "broker": "rabbitmq", "queue": queue, "routing_key": routing_key, "exchange": exchange},
                        annotation,
                        0.82,
                        "rabbitmq-producer",
                        service,
                        service_scope,
                    ),
                )
        for match in RABBIT_CONVERT_AND_SEND_RE.finditer(line):
            if re.search(r"\b(public|private|protected)\b.*\bconvertAndSend\s*\(", line):
                continue
            if "rabbit" not in line.lower() and "convertandsend" not in line.lower():
                continue
            if not (java_expr_is_literal_or_constant(match.group(1), root) or java_expr_is_literal_or_constant(match.group(2), root)):
                continue
            exchange = normalize_message_identifier(resolve_java_expr(match.group(1), root))
            routing_key = normalize_message_identifier(resolve_java_expr(match.group(2), root)) if match.group(2) else None
            identifier = routing_key or exchange
            if identifier and not identifier.startswith("messageReliable.get"):
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "MESSAGE_PRODUCER",
                        identifier,
                        {"type": "topic", "broker": "rabbitmq", "exchange": exchange, "routing_key": routing_key},
                        stripped,
                        0.64,
                        "rabbitmq-producer",
                        service,
                        service_scope,
                    ),
                )
        if any(token in line.lower() for token in ["kafka", "producer", "eventbus", "rabbit", "sns", "sqs"]):
            for send_match in re.finditer(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?send\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,", line):
                topic_var = send_match.group(1)
                if topic_var not in java_message_topics:
                    continue
                topic, topic_meta = java_message_topics[topic_var]
                match_rule = {"type": "topic", "topic": topic, "source_kind": "resolved_topic_variable", **topic_meta}
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "MESSAGE_PRODUCER",
                        topic,
                        match_rule,
                        stripped,
                        0.78,
                        "message",
                        service,
                        service_scope,
                    ),
                )
            for produce_match in KAFKA_PRODUCE_SERVICE_RE.finditer(line):
                args_text = extract_call_args_after(line, produce_match.start())
                args = split_java_args(args_text or "")
                if not args:
                    continue
                for topic, topic_meta in resolve_java_message_topic_entries_expr(args[0], root, java_message_topics, java_message_topic_sets):
                    match_rule = {
                        "type": "topic",
                        "broker": "kafka",
                        "topic": topic,
                        "source_kind": "kafka_produce_service",
                        **topic_meta,
                    }
                    add_unique(
                        seen,
                        endpoints,
                        endpoint(
                            root,
                            file,
                            idx,
                            "egress",
                            "MESSAGE_PRODUCER",
                            topic,
                            match_rule,
                            stripped,
                            0.8,
                            "kafka-produce-service",
                            service,
                            service_scope,
                        ),
                    )
            for match in KAFKA_PRODUCER_CONCAT_RE.finditer(line):
                topic = f"{match.group(1)}${{{match.group(2)}}}"
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "MESSAGE_PRODUCER",
                        topic,
                        {"type": "topic", "topic": topic, "prefix": match.group(1), "dynamic_suffix": match.group(2)},
                        stripped,
                        0.72,
                        "message",
                        service,
                        service_scope,
                    ),
                )
            for match in KAFKA_PRODUCER_RE.finditer(line):
                if KAFKA_PRODUCER_CONCAT_RE.search(line):
                    continue
                topic = match.group(1)
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "MESSAGE_PRODUCER", topic, {"type": "topic", "topic": topic}, stripped, 0.64, "message", service, service_scope))
            for match in KAFKA_PRODUCER_RECORD_RE.finditer(line):
                topic_expr = match.group(1)
                topic, topic_meta = resolve_java_message_topic_expr(topic_expr, root, java_message_topics)
                if not topic:
                    continue
                match_rule = {
                    "type": "topic",
                    "broker": "kafka",
                    "topic": topic,
                    "source_kind": "producer_record",
                    **topic_meta,
                }
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "MESSAGE_PRODUCER",
                        topic,
                        match_rule,
                        stripped,
                        0.82,
                        "kafka-producer",
                        service,
                        service_scope,
                    ),
                )
        for match in SCHEDULE_RE.finditer(line):
            if not match.group(1) and source_extension_allows_semantic_code(file):
                continue
            expr = (match.group(2) or match.group(3) or "").strip()
            method_name = next_java_method_name(lines, idx) if source_extension_allows_semantic_code(file) else None
            owner_type = enclosing_type_name(lines, idx, java_type)
            identifier = f"{owner_type}.{method_name}" if method_name else expr or "scheduled-job"
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "SCHEDULED_JOB", identifier, {"type": "schedule", "expression": expr}, stripped, 0.74 if method_name else 0.72, "schedule", service, service_scope))
        for match in list(STARTUP_SCHEDULE_RE.finditer(line)) + list(STARTUP_SCHEDULE_COMMA_RE.finditer(line)):
            owner_type = enclosing_type_name(lines, idx, java_type)
            worker_expr = match.group(4).strip()
            worker_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", worker_expr)
            worker = worker_match.group(1) if worker_match else owner_type
            worker_args = worker_match.group(2).strip() if worker_match else ""
            identifier = f"{owner_type}.{worker}"
            match_rule = {
                "type": "schedule",
                "scheduler": "scheduled-executor",
                "initial_delay": clean_path(match.group(1)),
                "fixed_rate": clean_path(match.group(2)),
                "time_unit": match.group(3).upper(),
                "worker": worker,
            }
            if worker_args:
                match_rule["worker_args"] = worker_args
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "SCHEDULED_JOB", identifier, match_rule, stripped, 0.82, "custom-schedule", service, service_scope))
        for match in TIMER_SCHEDULE_RE.finditer(line):
            owner_type = enclosing_type_name(lines, idx, java_type)
            worker = match.group(1)
            identifier = f"{owner_type}.{worker}"
            match_rule = {
                "type": "schedule",
                "scheduler": "java-timer",
                "start_time": clean_path(match.group(2)),
                "period": clean_path(match.group(3)),
                "worker": worker,
            }
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "SCHEDULED_JOB", identifier, match_rule, stripped, 0.8, "custom-schedule", service, service_scope))
        for match in XXL_JOB_RE.finditer(annotation):
            args = match.group(1)
            expr = first_annotation_string(annotation_attr(args, "cornExpr") or "") or first_annotation_string(annotation_attr(args, "cronExpr") or "")
            desc = first_annotation_string(annotation_attr(args, "desc") or "")
            execute_class = resolve_java_expr(annotation_attr(args, "executeClass"), root)
            disabled = bool(re.search(r"\bdisable\s*=\s*true\b", args, re.IGNORECASE))
            identifier = execute_class or desc or expr or "xxl-job"
            match_rule = {"type": "schedule", "scheduler": "xxl-job", "expression": expr, "description": desc, "disabled": disabled}
            if execute_class:
                match_rule["execute_class"] = execute_class
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "SCHEDULED_JOB", identifier, match_rule, annotation, 0.86, "xxl-job", service, service_scope))
        for match in SPRING_EVENT_PUBLISH_RE.finditer(line):
            event_type = match.group(1)
            add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "EVENT_BUS_PUBLISHER", event_type, {"type": "event", "event": event_type, "bus": "spring-application-event"}, stripped, 0.66, "spring-event", service, service_scope))
        for match in SPRING_EVENT_PUBLISH_ARG_RE.finditer(line):
            event_arg = match.group(1)
            event_type = java_var_types.get(event_arg)
            if not event_type:
                continue
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "egress",
                    "EVENT_BUS_PUBLISHER",
                    event_type,
                    {"type": "event", "event": event_type, "bus": "spring-application-event", "source_kind": "publishEvent_variable"},
                    stripped,
                    0.62,
                    "spring-event",
                    service,
                    service_scope,
                ),
            )
        if SPRING_EVENT_LISTENER_RE.search(annotation):
            owner_type = enclosing_type_name(lines, idx, java_type)
            event_type, event_confidence = spring_event_listener_identifier(annotation, lines, idx, owner_type)
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "EVENT_BUS_LISTENER", event_type, {"type": "event", "event": event_type, "bus": "spring-application-event"}, annotation, event_confidence, "spring-event", service, service_scope))
        for match in APPLICATION_LISTENER_RE.finditer(line):
            event_type = match.group(1)
            if len(event_type) <= 1:
                continue
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "EVENT_BUS_LISTENER", event_type, {"type": "event", "event": event_type, "bus": "spring-application-event"}, stripped, 0.68, "spring-event", service, service_scope))
        for match in EVENT_SERVICE_SUBSCRIBE_RE.finditer(line):
            event_fqn = resolve_event_fqn_expr(match.group(1), root)
            handler = clean_path(match.group(2))
            if event_fqn:
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "EVENT_BUS_LISTENER", event_fqn, {"type": "event", "event": event_fqn, "bus": "eventservice", "handler": handler}, stripped, 0.86, "eventservice", service, service_scope))
        if (service is None or service == "mbsp-stream") and "EventMessageHandleEnum" in text and re.match(r"\s*[A-Z][A-Z0-9_]*\s*\(", line):
            args_match = re.search(r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", line)
            if args_match and args_match.group(1).startswith("event.") and args_match.group(2).lower().endswith("handler"):
                event_fqn = args_match.group(1)
                handler = args_match.group(2)
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "EVENT_BUS_LISTENER", event_fqn, {"type": "event", "event": event_fqn, "bus": "eventservice", "handler": handler, "source_kind": "event_handler_enum"}, stripped, 0.88, "eventservice", service, service_scope))
        for match in EVENT_SERVICE_PUSH_RE.finditer(line):
            event_fqn = resolve_event_fqn_expr(match.group(1), root)
            if event_fqn:
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "EVENT_BUS_PUBLISHER", event_fqn, {"type": "event", "event": event_fqn, "bus": "eventservice"}, stripped, 0.88, "eventservice", service, service_scope))
        for match in DATA_EVENT_PUBLISH_CALL_RE.finditer(line):
            event_fqn = resolve_event_fqn_expr(match.group(1), root)
            if event_fqn:
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "EVENT_BUS_PUBLISHER",
                        event_fqn,
                        {"type": "event", "event": event_fqn, "bus": "eventservice", "source_kind": "eventservice_publish_call"},
                        stripped,
                        0.84,
                        "eventservice",
                        service,
                        service_scope,
                    ),
                )
        for match in DATA_EVENT_SCHEMA_CALL_RE.finditer(line):
            event_fqn = resolve_event_fqn_expr(match.group(1), root)
            if event_fqn:
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "DATA_EVENT_SCHEMA", event_fqn, {"type": "data_event", "event": event_fqn, "source_kind": "event_publish_options"}, stripped, 0.74, "event-schema", service, service_scope))
        for match in EVENT_SERVICE_POLL_RE.finditer(line):
            event_fqn = resolve_event_fqn_expr(match.group(1), root)
            if event_fqn:
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "EVENT_BUS_LISTENER", event_fqn, {"type": "event", "event": event_fqn, "bus": "eventservice", "source_kind": "poll"}, stripped, 0.7, "eventservice", service, service_scope))
        for match in CLI_RE.finditer(line):
            command = match.group(2) or "cli-command"
            add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "CLI", command, {"type": "cli_command", "command": command}, stripped, 0.66, "cli", service, service_scope))
        file_scope = scope_relative_path(file, root).as_posix().lower()
        if source_extension_allows_db_table_scan(file) and not is_test_source(file, root) and "/resources/back/" not in f"/{file_scope}" and not is_comment_or_import(line):
            for match in TABLE_RE.finditer(line):
                if match.group(0).strip().upper().startswith(("FROM", "JOIN", "UPDATE", "INSERT", "DELETE")) and not has_db_table_context(line, file):
                    continue
                table = match.group(2)
                if table.lower() in {"the", "it", "this", "that", "a", "an", "update"}:
                    continue
                if "@TableName" in line:
                    table = resolve_java_expr(table, root) or table
                if is_datamodel_fqn(table):
                    fqn = normalize_datamodel_fqn(table)
                    kind, access_mode = data_model_access_kind(line)
                    add_unique(
                        seen,
                        endpoints,
                        endpoint(
                            root,
                            file,
                            idx,
                            "egress",
                            kind,
                            fqn,
                            {
                                "type": "data_model_sql" if kind == "ANALYTICS_MODEL_QUERY" else "dataapi_model",
                                "fqn": fqn,
                                "operation": "sql",
                                "access_mode": access_mode,
                                "source_kind": "table_adapter",
                                "query_language": "SQL",
                            },
                            stripped,
                            0.82,
                            "dataapi-sql",
                            service,
                            service_scope,
                        ),
                    )
                    continue
                identifier, match_rule = normalize_table_identifier(table)
                if not is_valid_table_endpoint_identifier(identifier, table, line):
                    continue
                source_kind = "mapper_xml" if file.suffix.lower() == ".xml" else "source_sql"
                match_rule["source_kind"] = source_kind
                confidence = 0.85 if source_kind == "mapper_xml" or "mapper" in file.name.lower() else 0.75
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "DB_TABLE", identifier, match_rule, stripped, confidence, "database", service, service_scope))
        cache_expr = resolve_cache_key_expr(line, root, local_cache_vars)
        operation_match = REDIS_OPERATION_RE.search(line)
        if operation_match:
            arg_match = re.search(r"\(\s*([^,\)\n]+)", line[operation_match.end() - 1 :])
            if arg_match:
                cache_expr = resolve_cache_key_expr(arg_match.group(1).strip(), root, local_cache_vars) or cache_expr
        if cache_expr and (
            operation_match
            or "RedisCacheKeyEnum." in line
            or "CacheService.wrapKey" in line
        ):
            identifier, match_rule = cache_expr
            operation = operation_match.group(1) if operation_match and operation_match.group(1) else None
            if operation:
                match_rule = {**match_rule, "operation": operation}
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    "egress",
                    "DISTRIBUTED_CACHE",
                    identifier,
                    match_rule,
                    stripped,
                    0.8 if operation else 0.72,
                    "redis",
                    service,
                    service_scope,
                ),
            )
        for model_match in list(JAVA_ENTITY_MODEL_RE.finditer(annotation)) + list(EVENT_MODEL_RE.finditer(annotation)):
            args = model_match.group(1)
            fqn = resolve_java_expr(annotation_attr(args, "name") or annotation_attr(args, "fqn") or annotation_attr(args, "value"), root)
            if not fqn or not is_datamodel_fqn(fqn):
                continue
            normalized_fqn = normalize_datamodel_fqn(fqn)
            if is_event_fqn(normalized_fqn):
                direction, kind, evidence_kind = "egress", "DATA_EVENT_SCHEMA", "event-schema"
                match_rule = {"type": "data_event", "event": normalized_fqn, "source_kind": "semantic_event_annotation"}
            else:
                direction, kind, evidence_kind = "egress", "DATAMODEL", "semantic-model-annotation"
                match_rule = {"type": "datamodel", "fqn": normalized_fqn, "source_kind": "semantic_model_annotation"}
            add_unique(
                seen,
                endpoints,
                endpoint(
                    root,
                    file,
                    idx,
                    direction,
                    kind,
                    normalized_fqn,
                    match_rule,
                    annotation,
                    0.84,
                    evidence_kind,
                    service,
                    service_scope,
                ),
            )
        for match in FILE_RE.finditer(line):
            file_contract = match.group(1)
            if file_contract.lower().startswith(("http://", "https://")):
                continue
            channel = file_integration_channel(line, file_contract, file)
            if channel:
                add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "FILE", file_contract, {"type": "file_path", "path": file_contract, "integration": True, "channel": channel}, stripped, 0.62, "file-integration", service, service_scope))
        if file.suffix.lower() == ".proto":
            for match in PROTO_SERVICE_RE.finditer(line):
                rpc_service = match.group(1)
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "RPC_ROUTE", rpc_service, {"type": "rpc_service", "service": rpc_service}, stripped, 0.84, "protobuf", service, service_scope))
            for match in PROTO_RPC_RE.finditer(line):
                method = match.group(1)
                add_unique(seen, endpoints, endpoint(root, file, idx, "ingress", "RPC_ROUTE", method, {"type": "rpc_method", "method": method}, stripped, 0.78, "protobuf", service, service_scope))
        if source_extension_allows_semantic_code(file) and not is_comment_or_import(line):
            for match in JAVA_FQN_CONSTANT_ACCESS_RE.finditer(line):
                fqn = java_string_constants(root).get(f"{match.group(1)}.FQN")
                if not fqn or not is_datamodel_fqn(fqn):
                    continue
                normalized_fqn = normalize_datamodel_fqn(fqn)
                if is_event_fqn(normalized_fqn):
                    direction, kind, evidence_kind = event_endpoint_kind(line)
                    match_rule = {"type": "data_event", "event": normalized_fqn, "source_kind": "java_fqn_constant", "constant": f"{match.group(1)}.FQN"}
                else:
                    direction, kind, evidence_kind = "egress", "DATAMODEL", "java-fqn-constant"
                    match_rule = {"type": "datamodel", "fqn": normalized_fqn, "source_kind": "java_fqn_constant", "constant": f"{match.group(1)}.FQN"}
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        direction,
                        kind,
                        normalized_fqn,
                        match_rule,
                        f"{match.group(1)}.FQN -> {normalized_fqn}; {stripped}",
                        0.78,
                        evidence_kind,
                        service,
                        service_scope,
                    ),
                )
            enum_matches = list(OPENAPI_FQN_MODEL_RE.finditer(line)) + list(MODEL_ENUM_FQN_ACCESS_RE.finditer(line))
            for match in enum_matches:
                model = match.group(1).upper()
                fqn = resolve_model_name_enum_fqn(root, model)
                if not fqn:
                    continue
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "DATAMODEL",
                        fqn,
                        {
                            "type": "datamodel",
                            "name": model,
                            "fqn": fqn,
                            "resolver": "FetchCacheService.fetchOpenapiFqn",
                            "dynamic_fqn": True,
                        },
                        f"ModelNameEnum.{model} -> {fqn}; {stripped}",
                        0.76,
                        "openapi-fqn-model",
                        service,
                        service_scope,
                    ),
                )
            for match in DATAMODEL_RE.finditer(line):
                model = match.group(1) or match.group(2)
                if model in {"RequestMapping", "RequestMappingRepository"}:
                    continue
                if is_datamodel_fqn(model):
                    fqn = normalize_datamodel_fqn(model)
                    add_unique(seen, endpoints, endpoint(root, file, idx, "egress", "DATAMODEL", fqn, {"type": "datamodel", "fqn": fqn}, stripped, 0.7, "datamodel", service, service_scope))
        if file.suffix.lower() in {".java", ".kt", ".yaml", ".yml", ".json", ".properties"} and not is_comment_or_import(line):
            for match in DATA_FQN_LITERAL_RE.finditer(line):
                fqn = normalize_datamodel_fqn(match.group(0))
                if is_datamodel_fqn(fqn):
                    if is_plain_model_or_dto_source(file):
                        continue
                    if "@DataModel" in line:
                        continue
                    lowered_line = line.lower()
                    schema_literal_context = (
                        any(token in lowered_line for token in ["createmodel", "createenummodel", "cleanenummodel", "metadataapi", "usemode", "enummodelfqn", "\"olap\"", "\"htap\"", "\"oltp\""])
                        or "fqn_prefix" in lowered_line
                        or "%s" in line
                        or "%d" in line
                    )
                    configurable_model_context = "system.getproperty" in lowered_line or "getsysorenv" in lowered_line
                    cleanup_sql_context = "doclean(" in lowered_line
                    payload_or_filter_context = (
                        configurable_model_context
                        and any(token in lowered_line for token in ["targetfqn", "targetlastfqn", "segmentpayload", "bitmap", "rule_meta_model_fqn"])
                    )
                    if (cleanup_sql_context or payload_or_filter_context) and not is_event_fqn(fqn):
                        kind, access_mode = data_model_access_kind(line, "query" if cleanup_sql_context else None)
                        add_unique(
                            seen,
                            endpoints,
                            endpoint(
                                root,
                                file,
                                idx,
                                "egress",
                                kind,
                                fqn,
                                {
                                    "type": "data_model_sql" if kind == "ANALYTICS_MODEL_QUERY" else "dataapi_model",
                                    "fqn": fqn,
                                    "operation": "query",
                                    "access_mode": access_mode,
                                    "source_kind": "model_fqn_config_or_cleanup",
                                    "query_language": "SQL",
                                },
                                stripped,
                                0.72,
                                "dataapi-sql",
                                service,
                                service_scope,
                            ),
                        )
                        continue
                    if schema_literal_context and not is_event_fqn(fqn):
                        if "string.format" in lowered_line or "%s" in line or "%d" in line:
                            schema_fqns = extract_dataapi_fqns(line, root, local_dataapi_sql_fqns)
                            if any(full != fqn and full.startswith(fqn + ".") for full in schema_fqns):
                                continue
                            if schema_fqns and fqn not in schema_fqns:
                                fqn = sorted(schema_fqns)[0]
                        literal = first_annotation_string(line)
                        if literal and "data." in literal:
                            fqn = normalize_datamodel_fqn(literal)
                        if not is_datamodel_fqn(fqn):
                            continue
                        add_unique(
                            seen,
                            endpoints,
                            endpoint(
                                root,
                                file,
                                idx,
                                "egress",
                                "DATA_MODEL_SCHEMA",
                                fqn,
                                {"type": "data_model_schema", "fqn": fqn, "source_kind": "schema_literal"},
                                stripped,
                                0.72,
                                "model-schema",
                                service,
                                service_scope,
                            ),
                        )
                        continue
                    if re.search(r"^\s*(?:(?:public|private|protected|static|final)\s+)*String\s+[A-Z][A-Z0-9_]*\s*=", line):
                        continue
                    stronger_data_model_context = (
                        is_model_metadata_json(file)
                        or dataapi_context(text, line)
                        or any(token in lowered_line for token in ["commonsqlexecute", "querybystream", "streamgetsn", "batchmergemodel", "batchinsertmodel", "importdata", "mergedata", "fetch("])
                        or re.search(r"\b(?:from|join|insert\s+into|update|delete\s+from)\s+data\.", lowered_line)
                    )
                    if not is_event_fqn(fqn) and stronger_data_model_context:
                        continue
                    if is_event_fqn(fqn):
                        direction, kind, evidence_kind = event_endpoint_kind(line)
                        match_rule = {
                            "type": "event" if kind in {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} else "data_event",
                            "event": fqn,
                            "source_kind": "literal_fqn",
                            **({"bus": "eventservice"} if kind in {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} else {}),
                        }
                        confidence = 0.72 if kind == "DATA_EVENT_PUBLISHER" else 0.68
                    else:
                        direction, kind, evidence_kind = "egress", "DATAMODEL", "datamodel-literal"
                        match_rule = {"type": "datamodel", "fqn": fqn, "source_kind": "literal_fqn"}
                        confidence = 0.68
                    add_unique(
                        seen,
                        endpoints,
                        endpoint(
                            root,
                            file,
                            idx,
                            direction,
                            kind,
                            fqn,
                            match_rule,
                            stripped,
                            confidence,
                            evidence_kind,
                            service,
                            service_scope,
                        ),
                    )
            for match in OSS_OPERATION_RE.finditer(line):
                receiver = match.group(1)
                if not is_oss_operation_context(receiver, line, file):
                    continue
                operation = match.group(2)
                bucket = resolve_java_expr(match.group(3).strip(), root) or match.group(3).strip()
                object_key = resolve_java_expr(match.group(4).strip(), root) or match.group(4).strip()
                if not is_resolved_object_storage_target(bucket, object_key):
                    continue
                identifier = f"OSS {operation} {bucket}/{object_key}"
                add_unique(
                    seen,
                    endpoints,
                    endpoint(
                        root,
                        file,
                        idx,
                        "egress",
                        "SDK",
                        identifier,
                        {"type": "object_storage", "sdk": "OSSClient", "operation": operation, "bucket": bucket, "object_key": object_key},
                        stripped,
                        0.68,
                        "sdk-object-storage",
                        service,
                        service_scope,
                    ),
                )


def parse_pom(pom: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"artifact_id": pom.parent.name, "modules": [], "dependencies": []}
    try:
        tree = ET.parse(pom)
    except ET.ParseError:
        text = pom.read_text(encoding="utf-8", errors="ignore")
        artifact = re.search(r"<artifactId>([^<]+)</artifactId>", text)
        if artifact:
            result["artifact_id"] = artifact.group(1).strip()
        result["modules"] = re.findall(r"<module>([^<]+)</module>", text)
        result["dependencies"] = re.findall(r"<dependency>.*?<artifactId>([^<]+)</artifactId>.*?</dependency>", text, re.S)
        return result
    root = tree.getroot()
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"

    def child_text(elem: ET.Element, name: str) -> str | None:
        child = elem.find(f"{ns}{name}")
        if child is not None and child.text:
            return child.text.strip()
        return None

    artifact = child_text(root, "artifactId")
    if artifact:
        result["artifact_id"] = artifact
    modules = root.find(f"{ns}modules")
    if modules is not None:
        result["modules"] = [m.text.strip() for m in modules.findall(f"{ns}module") if m.text]
    dependencies = root.find(f"{ns}dependencies")
    if dependencies is not None:
        for dep in dependencies.findall(f"{ns}dependency"):
            artifact_id = child_text(dep, "artifactId")
            if artifact_id:
                result["dependencies"].append(artifact_id)
    return result


def iter_module_source_files(module_dir: Path, declared_modules: list[str]):
    child_dirs = {module_dir / child for child in declared_modules}
    for file in iter_source_files(module_dir):
        if any(_is_relative_to(file, child) for child in child_dirs):
            continue
        yield file


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def has_spring_boot_app(module_dir: Path, declared_modules: list[str]) -> bool:
    for file in iter_module_source_files(module_dir, declared_modules):
        if file.suffix.lower() not in {".java", ".kt"}:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SPRING_BOOT_APP_RE.search(text):
            return True
    return False


def has_runtime_config(module_dir: Path, declared_modules: list[str]) -> bool:
    config_names = {"application.properties", "application.yml", "application.yaml", "bootstrap.properties", "bootstrap.yml", "bootstrap.yaml"}
    for file in iter_module_source_files(module_dir, declared_modules):
        if file.name.lower() in config_names:
            try:
                text = file.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            if any(token in text for token in ["server.servlet.context-path", "server.port", "spring.application.name", "xxl.job.executor"]):
                return True
    return False


def has_ktor_server_app(module_dir: Path, declared_modules: list[str]) -> bool:
    for file in iter_module_source_files(module_dir, declared_modules):
        if file.suffix.lower() not in {".java", ".kt"}:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if KTOR_SERVER_RE.search(text):
            return True
    return False


def has_runtime_packaging(module_dir: Path) -> bool:
    dockerfile = module_dir / "Dockerfile"
    if dockerfile.exists():
        return True
    pom = module_dir / "pom.xml"
    if pom.exists():
        try:
            text = pom.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        return bool(re.search(r"<main\.class>[^<]+</main\.class>", text, re.IGNORECASE))
    return False


def capability_scan_plan(capability: str, kinds: list[str]) -> list[str]:
    plans = {
        "Spring MVC": [
            "scan controller annotations and class/method mapping combinations",
            "confirm each route with HTTP method and normalized path template",
        ],
        "Spring OpenFeign": [
            "scan @FeignClient interfaces and inherited mapping annotations",
            "classify client mappings as HTTP_CALL rather than HTTP_API",
        ],
        "JAX-RS annotations": [
            "scan @Path plus HTTP verb annotations in service/client contracts",
            "cross-check owner context to classify ingress route versus outbound call",
        ],
        "Kafka": [
            "scan @KafkaListener, KafkaTemplate.send, KafkaProducer, ProducerRecord, KafkaConsumer.subscribe, and project KafkaConsumeService/KafkaProduceService wrappers",
            "resolve constants, collections, maps, branch-filtered topic templates, and stable dynamic topic templates into MESSAGE_CONSUMER/MESSAGE_PRODUCER identifiers",
        ],
        "RabbitMQ": [
            "scan @RabbitListener, RabbitTemplate.convertAndSend, and project producer annotations",
            "resolve queue, exchange, and routing key constants before endpoint emission",
        ],
        "Redis/Redisson": [
            "scan RedisTemplate/StringRedisTemplate operations, Redisson locks, and distributed cache enums",
            "confirm a stable distributed key namespace or prefix before emitting DISTRIBUTED_CACHE",
        ],
        "XXL-Job": [
            "scan @XxlJob declarations and scheduler metadata",
            "emit scheduled entry contracts with executeClass/job handler identifiers",
        ],
        "Spring Scheduler": [
            "scan @Scheduled, TaskScheduler, Timer, and fixed-rate scheduling calls",
            "emit scheduled entry contracts only for runtime jobs",
        ],
        "MyBatis": [
            "scan @TableName, mapper interfaces, mapper XML, and table-position SQL",
            "exclude tests, migrations, comments, and unresolved generic table constants",
        ],
        "JPA": [
            "scan @Entity and @Table mappings",
            "emit DB_TABLE only when production ORM metadata names a table",
        ],
        "Shuyun EventService": [
            "scan com.shuyun.air.es/EventService wrappers, Event.of, EventProducer, PublishOptions, and publish calls",
            "resolve event FQN constants/templates into EVENT_BUS_PUBLISHER or EVENT_BUS_LISTENER contracts",
        ],
        "Shuyun DataAPI": [
            "scan DataapiHttpSdk, DataapiWebSocketSdk, DataapiSdkFactory, DataApiService, and SQL/query wrapper calls",
            "resolve data.* model FQNs and classify ordinary calls as DATA_API_CALL, streaming/fetch paths as DATA_API_STREAM, and OLAP/columnar paths as ANALYTICS_MODEL_QUERY",
        ],
    }
    return plans.get(
        capability,
        [
            f"scan source/config features that can confirm {', '.join(kinds)}",
            "emit endpoints only after a concrete runtime contract identifier is visible or template-resolvable",
        ],
    )


def detect_toolchain_preflight(root: Path) -> dict[str, Any]:
    capability_specs = {
        "Spring Boot": {
            "patterns": ["spring-boot", "@SpringBootApplication", "SpringApplication.run"],
            "potential_kinds": [],
            "confirming_features": ["runtime bootstrap"],
        },
        "Spring MVC": {
            "patterns": ["spring-webmvc", "@GetMapping", "@PostMapping", "@RequestMapping", "@RestController"],
            "potential_kinds": ["HTTP_API"],
            "confirming_features": ["@RestController", "@RequestMapping", "@GetMapping", "@PostMapping"],
        },
        "Spring OpenFeign": {
            "patterns": ["spring-cloud-starter-openfeign", "spring-cloud-openfeign", "@FeignClient", "@EnableFeignClients"],
            "potential_kinds": ["HTTP_CALL"],
            "confirming_features": ["@FeignClient", "method mapping annotations"],
        },
        "JAX-RS annotations": {
            "patterns": ["javax.ws.rs", "jakarta.ws.rs", "@Path(", "@GET", "@POST"],
            "potential_kinds": ["HTTP_CALL", "HTTP_API"],
            "confirming_features": ["@Path", "@GET", "@POST", "@PUT", "@DELETE"],
        },
        "Ktor server": {
            "patterns": ["ktor-server", "embeddedServer(", "io.ktor.server"],
            "potential_kinds": ["HTTP_API"],
            "confirming_features": ["embeddedServer", "routing"],
        },
        "Retrofit": {
            "patterns": ["retrofit", "@RetrofitService"],
            "potential_kinds": ["HTTP_CALL"],
            "confirming_features": ["Retrofit service interface", "HTTP method annotations"],
        },
        "OkHttp": {
            "patterns": ["okhttp", "OkHttpClient"],
            "potential_kinds": ["HTTP_CALL"],
            "confirming_features": ["OkHttpClient", "Request.Builder", "wrapper URL construction"],
        },
        "Spring Cloud Stream": {
            "patterns": ["spring-cloud-stream", "@StreamListener", "spring.cloud.stream.bindings", "-in-0", "-out-0"],
            "potential_kinds": ["MESSAGE_CONSUMER", "MESSAGE_PRODUCER"],
            "confirming_features": ["binding destination", "@StreamListener", "send"],
        },
        "Kafka": {
            "patterns": ["kafka-clients", "@KafkaListener", "KafkaTemplate", "KafkaConsumer", "KafkaProducer", "ProducerRecord", "consumer.subscribe", "KafkaConsumeService", "KafkaProduceService"],
            "potential_kinds": ["MESSAGE_CONSUMER", "MESSAGE_PRODUCER"],
            "confirming_features": ["@KafkaListener topics", "KafkaTemplate.send", "ProducerRecord topic", "KafkaConsumer.subscribe", "KafkaConsumeService.consume/batchConsume", "KafkaProduceService.produce/produceAsync"],
        },
        "RabbitMQ": {
            "patterns": ["amqp", "RabbitListener", "RabbitTemplate", "RabbitMqProducerAnnotation"],
            "potential_kinds": ["MESSAGE_CONSUMER", "MESSAGE_PRODUCER"],
            "confirming_features": ["@RabbitListener queues", "convertAndSend", "producer annotation"],
        },
        "Redis/Redisson": {
            "patterns": ["redis", "RedisTemplate", "StringRedisTemplate", "Redisson", "redisCache"],
            "potential_kinds": ["DISTRIBUTED_CACHE"],
            "confirming_features": ["Redis key enum", "redisCache operation", "Redisson lock", "RedisTemplate operation"],
        },
        "XXL-Job": {
            "patterns": ["xxl-job", "@XxlJob"],
            "potential_kinds": ["SCHEDULED_JOB"],
            "confirming_features": ["@XxlJob"],
        },
        "Spring Scheduler": {
            "patterns": ["@Scheduled", "TaskScheduler", "scheduleAtFixedRate"],
            "potential_kinds": ["SCHEDULED_JOB"],
            "confirming_features": ["@Scheduled", "scheduleAtFixedRate", "Timer.schedule"],
        },
        "MyBatis": {
            "patterns": ["mybatis", "@Mapper", "mapper.xml"],
            "potential_kinds": ["DB_TABLE"],
            "confirming_features": ["@TableName", "mapper SQL", "mapper XML table-position SQL"],
        },
        "JPA": {
            "patterns": ["spring-data-jpa", "@Entity", "@Table("],
            "potential_kinds": ["DB_TABLE"],
            "confirming_features": ["@Entity", "@Table(name=...)"],
        },
        "OpenAPI": {
            "patterns": ["openapi", "swagger", "springdoc-openapi"],
            "potential_kinds": ["HTTP_API", "HTTP_CALL"],
            "confirming_features": ["OpenAPI paths", "generated client/server contract"],
        },
        "Shuyun EventService": {
            "patterns": ["com.shuyun.air.es", "EventProducer", "PublishOptions", "Event.of", "EsFactory", "eventservice", "publishBatchSync", "sendEvents"],
            "potential_kinds": ["EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"],
            "confirming_features": ["Event.of(eventFqn)", "EventProducer", "publishBatchSync", "EventServiceSupport push/poll"],
        },
        "Shuyun DataAPI": {
            "patterns": ["DataapiHttpSdk", "DataapiWebSocketSdk", "DataapiSdkFactory", "DataApiService", "DataApiSupport", "getDataapiSdk()", "commonSqlExecute", "queryByStream"],
            "potential_kinds": ["DATA_API_CALL", "DATA_API_STREAM", "ANALYTICS_MODEL_QUERY"],
            "confirming_features": ["DataapiHttpSdk execute/importData/mergeData", "DataapiWebSocketSdk or fetch stream", "DataApiService SQL/model wrappers"],
        },
    }
    capability_patterns = {name: spec["patterns"] for name, spec in capability_specs.items()}
    capability_evidence: dict[str, list[str]] = {name: [] for name in capability_patterns}
    scanned_files = 0
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        parts = {part.lower() for part in file.parts}
        if parts & {"target", ".git", ".cursor", "node_modules", "dist", "build", ".venv", "venv", "graphify-out"}:
            continue
        if file.name != "pom.xml" and file.suffix.lower() not in {".java", ".kt", ".xml", ".yml", ".yaml", ".properties"}:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned_files += 1
        rel = file.relative_to(root).as_posix()
        lower_text = text.lower()
        for capability, patterns in capability_patterns.items():
            if capability_evidence[capability] and len(capability_evidence[capability]) >= 5:
                continue
            for pattern in patterns:
                if pattern.startswith("@") or pattern.endswith("("):
                    found = pattern in text
                else:
                    found = pattern.lower() in lower_text
                if found:
                    capability_evidence[capability].append(f"{rel}: {pattern}")
                    break
    capabilities = [
        {
            "name": name,
            "potential_endpoint_kinds": capability_specs[name].get("potential_kinds", []),
            "confirming_features": capability_specs[name].get("confirming_features", []),
            "evidence": evidence,
        }
        for name, evidence in sorted(capability_evidence.items())
        if evidence
    ]
    detected = {item["name"] for item in capabilities}
    rule_gap_warnings = []
    coverage_notes = []
    if {"Spring OpenFeign", "JAX-RS annotations"} <= detected:
        coverage_notes.append("Spring OpenFeign plus JAX-RS annotations detected; @FeignClient + @Path + @GET/@POST HTTP_CALL extraction and audit coverage are enabled.")
    if "Ktor server" in detected:
        coverage_notes.append("Ktor server runtime detected; embeddedServer/main-class service discovery coverage is enabled.")
    capability_hints = []
    for capability in capabilities:
        kinds = capability.get("potential_endpoint_kinds") or []
        if not kinds:
            continue
        capability_hints.append(
            {
                "capability": capability["name"],
                "potential_endpoint_kinds": kinds,
                "confirming_features": capability.get("confirming_features") or [],
                "scan_plan": capability_scan_plan(capability["name"], kinds),
                "evidence": capability.get("evidence") or [],
                "status": "candidate_only",
                "confirmed_endpoint_count": 0,
                "confirmed_kinds": {},
                "audit_action": "targeted_scan_pending",
                "note": "Dependency/framework capability is a clue only; endpoint emission still requires source/config usage evidence.",
            }
        )
    return {
        "scanned_files": scanned_files,
        "capabilities": capabilities,
        "capability_hints": capability_hints,
        "coverage_notes": coverage_notes,
        "rule_gap_warnings": rule_gap_warnings,
    }


def capability_matches_endpoint(capability: str, endpoint: dict[str, Any]) -> bool:
    kind = endpoint.get("kind")
    metadata = endpoint.get("metadata") or {}
    match_rule = endpoint.get("match_rule") or {}
    identifier = str(endpoint.get("identifier") or "").lower()
    framework = str(metadata.get("framework") or "").lower()
    evidence_text = "\n".join(str(item) for item in metadata.get("evidence") or []).lower()
    source_text = "\n".join(str(item) for item in metadata.get("source_refs") or []).lower()
    match_text = json.dumps(match_rule, ensure_ascii=False, default=str).lower()
    combined = f"{identifier}\n{framework}\n{evidence_text}\n{source_text}\n{match_text}"
    if capability == "Spring MVC":
        return kind == "HTTP_API" and ("spring" in framework or "@requestmapping" in combined or "@getmapping" in combined or "@postmapping" in combined)
    if capability == "Spring OpenFeign":
        return kind == "HTTP_CALL" and ("feign" in framework or "@feignclient" in combined)
    if capability == "JAX-RS annotations":
        return kind in {"HTTP_CALL", "HTTP_API"} and any(token in combined for token in ("@path", "javax.ws.rs", "jakarta.ws.rs"))
    if capability == "Ktor server":
        return kind == "HTTP_API" and any(token in combined for token in ("ktor", "embeddedserver", "routing"))
    if capability == "Retrofit":
        return kind == "HTTP_CALL" and ("retrofit" in combined or "feign-retrofit" in framework)
    if capability == "OkHttp":
        return kind == "HTTP_CALL" and any(token in combined for token in ("okhttp", "okhttpclient", "request.builder"))
    if capability == "Spring Cloud Stream":
        return kind in {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"} and "spring-cloud-stream" in framework
    if capability == "Kafka":
        return kind in {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"} and any(token in combined for token in ("kafkatemplate", "@kafkalistener", "kafka", "producerrecord", "subscribe"))
    if capability == "RabbitMQ":
        return kind in {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"} and any(token in combined for token in ("rabbit", "amqp", "convertandsend"))
    if capability == "Redis/Redisson":
        return kind == "DISTRIBUTED_CACHE" and any(token in combined for token in ("redis", "redisson", "redistemplate", "rediscache"))
    if capability == "XXL-Job":
        return kind == "SCHEDULED_JOB" and any(token in combined for token in ("xxl", "@xxljob"))
    if capability == "Spring Scheduler":
        return kind == "SCHEDULED_JOB" and any(token in combined for token in ("@scheduled", "scheduleatfixedrate", "timer.schedule"))
    if capability == "MyBatis":
        return kind == "DB_TABLE" and any(token in combined for token in ("mybatis", "@tablename", "mapper"))
    if capability == "JPA":
        return kind == "DB_TABLE" and any(token in combined for token in ("@entity", "@table", "jpa"))
    if capability == "OpenAPI":
        return kind in {"HTTP_API", "HTTP_CALL"} and (
            "openapi" in framework
            or "swagger" in framework
            or any(token in source_text for token in (".openapi.", "/openapi/", "swagger.yml", "swagger.yaml", "openapi.yml", "openapi.yaml"))
        )
    if capability == "Shuyun EventService":
        return kind in {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} and any(
            token in combined
            for token in ("eventservice", "com.shuyun.air.es", "event.of", "eventproducer", "publishbatchsync", "shuyun-eventservice")
        )
    if capability == "Shuyun DataAPI":
        return kind in {"DATA_API_CALL", "DATA_API_STREAM", "ANALYTICS_MODEL_QUERY"} and any(
            token in combined
            for token in ("dataapi", "dataapisdk", "dataapiservice", "commonsqlexecute", "querybystream", "data proxy")
        )
    return False


def finalize_capability_hints(preflight: dict[str, Any], endpoints: list[dict[str, Any]]) -> None:
    warnings = preflight.setdefault("rule_gap_warnings", [])
    for hint in preflight.get("capability_hints") or []:
        capability = hint.get("capability")
        matching = [endpoint for endpoint in endpoints if capability_matches_endpoint(capability, endpoint)]
        confirmed = Counter(endpoint.get("kind") for endpoint in matching)
        confirmed = {kind: count for kind, count in confirmed.items() if count}
        hint["confirmed_kinds"] = confirmed
        hint["confirmed_endpoint_count"] = sum(confirmed.values())
        hint["status"] = "confirmed_by_source" if confirmed else "candidate_only"
        hint["confirmed_endpoint_samples"] = [source_ref(endpoint) for endpoint in matching[:5]]
        hint["scan_plan_executed"] = bool(hint.get("scan_plan"))
        if confirmed:
            hint["audit_action"] = "targeted_scan_confirmed"
            hint["note"] = "Framework/dependency capability is present and matching source/config features produced confirmed endpoint contracts."
        else:
            hint["audit_action"] = "targeted_scan_no_confirming_contract"
            hint["note"] = "Capability is present in dependencies/frameworks, but no source/config evidence confirmed an endpoint contract."
            warning = (
                f"Capability {capability} detected but no endpoint was confirmed for "
                f"{', '.join(hint.get('potential_endpoint_kinds') or [])}; targeted scan plan: "
                f"{'; '.join(hint.get('scan_plan') or [])}"
            )
            if warning not in warnings:
                warnings.append(warning)


def discover_maven_modules(root: Path) -> dict[str, dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for pom in root.rglob("pom.xml"):
        if any(part in {"target", ".git", ".cursor"} for part in pom.parts):
            continue
        info = parse_pom(pom)
        artifact = info["artifact_id"]
        modules[artifact] = {
            "artifact_id": artifact,
            "path": pom.parent,
            "rel_path": pom.parent.relative_to(root).as_posix() if pom.parent != root else ".",
            "dependencies": list(dict.fromkeys(info.get("dependencies", []))),
            "declared_modules": info.get("modules", []),
            "is_runtime": False,
            "runtime_evidence": [],
        }
    for module in modules.values():
        path = module["path"]
        declared_modules = module.get("declared_modules", [])
        if has_spring_boot_app(path, declared_modules):
            module["is_runtime"] = True
            module["runtime_evidence"].append("SpringBootApplication")
        if has_runtime_config(path, declared_modules):
            module["is_runtime"] = True
            module["runtime_evidence"].append("runtime application config")
        if has_ktor_server_app(path, declared_modules):
            module["is_runtime"] = True
            module["runtime_evidence"].append("Ktor embeddedServer")
        if module["is_runtime"] and has_runtime_packaging(path):
            module["runtime_evidence"].append("runtime packaging")
    return modules


def dependency_closure(name: str, modules: dict[str, dict[str, Any]]) -> list[str]:
    internal = set(modules)
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(current: str) -> None:
        for dep in modules.get(current, {}).get("dependencies", []):
            if dep not in internal or dep in visited:
                continue
            visited.add(dep)
            ordered.append(dep)
            visit(dep)

    visit(name)
    return ordered


def discover_services(root: Path) -> list[dict[str, Any]]:
    modules = discover_maven_modules(root)
    services: list[dict[str, Any]] = []
    for name, module in sorted(modules.items(), key=lambda item: item[1]["rel_path"]):
        if not module["is_runtime"]:
            continue
        deps = dependency_closure(name, modules)
        scope_modules = [name] + deps
        scope_roots = [modules[m]["path"] for m in scope_modules if m in modules]
        services.append(
            {
                "name": name,
                "root": module["rel_path"],
                "runtime_evidence": module["runtime_evidence"],
                "dependencies": deps,
                "scope_roots": [p.relative_to(root).as_posix() if p != root else "." for p in scope_roots],
                "_scope_paths": scope_roots,
                "_runtime_path": module["path"],
            }
        )
    return services


def classify_service_scope(file: Path, service: dict[str, Any]) -> str:
    runtime_path = service["_runtime_path"]
    try:
        file.relative_to(runtime_path)
        return "runtime"
    except ValueError:
        return "dependency"


def graphify_present(root: Path) -> bool:
    return find_graphify_index(root) is not None


def find_graphify_index(root: Path, explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    candidates.extend(
        [
            root / "graphify-out" / "graph.json",
            root / "graph.json",
            root.parent / f"{root.name}-graphify-out" / "graphify-out" / "graph.json",
            root.parent / f"{root.name}-graphify-out" / "graph.json",
        ]
    )
    for parent in [root.parent, root.parent.parent if root.parent != root.parent.parent else root.parent]:
        candidates.extend(parent.glob("*graphify*out*/graphify-out/graph.json"))
        candidates.extend(parent.glob("*graphify*out*/graph.json"))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


GRAPH_ENDPOINT_TERMS = re.compile(
    r"api|route|controller|resource|handler|consumer|producer|listener|client|feign|retrofit|rpc|"
    r"websocket|scheduler|cache|table|mapper|repository|datamodel|fqn|sdk|oss|sftp|file|"
    r"RequestMapping|GetMapping|PostMapping|RabbitListener|KafkaListener|Scheduled|TableName",
    re.IGNORECASE,
)


def ensure_graphify_index(root: Path, mode: str = "") -> Path | None:
    script = Path(__file__).resolve().parent / "ensure_graphify_index.py"
    cmd = [sys.executable, str(script), str(root)]
    if mode:
        cmd.extend(["--mode", mode])
    try:
        result = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, check=False)
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    graph = Path(result.stdout.strip().splitlines()[-1])
    return graph.resolve() if graph.exists() else None


def graphify_source_candidates(root: Path, graph_index: Path | None) -> tuple[list[Path], dict[str, Any]]:
    if not graph_index or not graph_index.exists():
        return [], {"node_count": 0, "edge_count": 0, "candidate_source_files": 0}
    try:
        data = json.loads(graph_index.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return [], {"node_count": 0, "edge_count": 0, "candidate_source_files": 0, "read_error": str(exc)}
    nodes = data.get("nodes") or data.get("vertices") or []
    edges = data.get("edges") or data.get("links") or []
    candidates: set[Path] = set()
    for node in nodes:
        blob = json.dumps(node, ensure_ascii=False)
        if not GRAPH_ENDPOINT_TERMS.search(blob):
            continue
        file_value = None
        if isinstance(node, dict):
            meta = node.get("metadata") or {}
            props = node.get("properties") or {}
            file_value = node.get("source_file") or node.get("file") or node.get("path") or meta.get("source_file") or meta.get("file") or props.get("source_file") or props.get("file")
        if not file_value:
            match = re.search(r"([A-Za-z0-9_./\\-]+\.(?:java|kt|py|js|ts|tsx|jsx|go|rb|php|cs|scala|xml|sql|ya?ml|properties|proto|graphql))", blob)
            file_value = match.group(1) if match else None
        if not file_value:
            continue
        path = Path(str(file_value))
        if not path.is_absolute():
            path = root / path
        if path.exists() and path.is_file():
            candidates.add(path.resolve())
    return sorted(candidates), {"node_count": len(nodes), "edge_count": len(edges), "candidate_source_files": len(candidates)}


def path_in_any_scope(path: Path, scopes: list[Path]) -> bool:
    for scope in scopes:
        try:
            path.relative_to(scope)
            return True
        except ValueError:
            continue
    return False


def build_inventory(root: Path, graphify_index: Path | None = None, ensure_graphify: bool = False, graphify_mode: str = "") -> dict[str, Any]:
    endpoints: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    preflight = detect_toolchain_preflight(root)
    services = discover_services(root)
    graph_index = find_graphify_index(root, graphify_index)
    if ensure_graphify and graph_index is None:
        graph_index = ensure_graphify_index(root, graphify_mode)
    graph_candidates, graph_summary = graphify_source_candidates(root, graph_index)
    globally_scanned: set[Path] = set()
    if services:
        for service in services:
            service_seen: set[Path] = set()
            prioritized = [p for p in graph_candidates if path_in_any_scope(p, service["_scope_paths"])]
            for file in prioritized:
                resolved = file.resolve()
                if resolved in service_seen:
                    continue
                service_seen.add(resolved)
                globally_scanned.add(resolved)
                scan_file(root, file, seen, endpoints, service["name"], classify_service_scope(file, service))
            for scope_root in service["_scope_paths"]:
                for file in iter_source_files(scope_root):
                    resolved = file.resolve()
                    if resolved in service_seen:
                        continue
                    service_seen.add(resolved)
                    globally_scanned.add(resolved)
                    scan_file(root, file, seen, endpoints, service["name"], classify_service_scope(file, service))
        for file in graph_candidates:
            resolved = file.resolve()
            if resolved in globally_scanned:
                continue
            globally_scanned.add(resolved)
            scan_file(root, file, seen, endpoints)
        for file in iter_source_files(root):
            resolved = file.resolve()
            if resolved in globally_scanned:
                continue
            globally_scanned.add(resolved)
            scan_file(root, file, seen, endpoints)
    else:
        scanned: set[Path] = set()
        for file in graph_candidates:
            scan_file(root, file, seen, endpoints)
            scanned.add(file.resolve())
        for file in iter_source_files(root):
            if file.resolve() in scanned:
                continue
            scan_file(root, file, seen, endpoints)
    public_services = [
        {k: v for k, v in service.items() if not k.startswith("_")}
        for service in services
    ]
    warnings = [] if endpoints else ["No endpoints detected by deterministic first-pass scanner."]
    warnings.extend(preflight.get("rule_gap_warnings") or [])
    endpoints = [endpoint for endpoint in endpoints if endpoint.get("kind") not in SCHEMA_ENDPOINT_KINDS]
    finalize_capability_hints(preflight, endpoints)
    return {
        "schema_version": "endpoint-profiler.v1",
        "source_root": str(root.resolve()),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "services": public_services,
        "endpoints": endpoints,
        "audit": {
            "graphify_used": graph_index is not None,
            "graphify_index_path": str(graph_index) if graph_index else None,
            "graphify_summary": graph_summary,
            "preflight": preflight,
            "scan_modes": [
                "dependency-toolchain-preflight",
                "service-discovery",
                "maven-dependency-closure",
                "graphify-index" if graph_index else "source",
                "graphify-candidate-scan" if graph_candidates else "graphify-candidate-scan-skipped",
                "focused-source-confirmation" if graph_index else "pattern",
                "pattern",
            ],
            "warnings": warnings,
        },
    }


def safe_service_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return cleaned or "unknown-service"


def endpoint_confidence(item: dict[str, Any]) -> float:
    confidence = (item.get("metadata") or {}).get("confidence")
    return float(confidence) if isinstance(confidence, (int, float)) else 0.0


def endpoint_service(item: dict[str, Any]) -> str:
    return (item.get("owner") or {}).get("service") or "unassigned"


def endpoint_module(item: dict[str, Any]) -> str:
    source_file = (item.get("source") or {}).get("file") or ""
    parts = source_file.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts and parts[0] else "unknown"


def endpoint_cluster_key(item: dict[str, Any]) -> str:
    kind = item.get("kind") or "UNKNOWN"
    identifier = str(item.get("identifier") or "")
    match_rule = item.get("match_rule") or {}
    source_kind = match_rule.get("source_kind")
    if kind == "HTTP_API":
        parts = identifier.split(maxsplit=1)
        method = parts[0] if parts else "ANY"
        path = parts[1] if len(parts) > 1 else "/"
        first = next((part for part in path.split("/") if part and not part.startswith("{")), "")
        return f"{method} /{first}/**" if first else f"{method} /"
    if kind == "HTTP_CALL":
        parsed = urlparse(identifier)
        if parsed.netloc:
            return parsed.netloc
        first = next((part for part in identifier.split("/") if part and not part.startswith("{")), "")
        return f"/{first}/**" if first else "http-call"
    if kind == "DB_TABLE":
        schema = match_rule.get("schema")
        prefix = identifier.split("_", 1)[0] if "_" in identifier else identifier
        carrier = source_kind or "table"
        return f"{carrier}:{schema + '.' if schema else ''}{prefix}*"
    if kind in {"DATAMODEL", "DATA_MODEL_SCHEMA", "DATA_MODEL_SQL", "ANALYTICS_MODEL_QUERY", "DATA_API_CALL", "DATA_API_STREAM"}:
        parts = [p for p in identifier.replace("{tenantCode}", "*").split(".") if p]
        return ".".join(parts[:3]) + (".*" if len(parts) > 3 else "") if parts else "datamodel"
    if kind in {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER", "EVENT_BUS_LISTENER", "EVENT_BUS_PUBLISHER", "DATA_EVENT_SCHEMA", "DATA_EVENT_PUBLISHER"}:
        topic = match_rule.get("topic") or identifier
        return str(topic).split(".", 2)[0] + ".*" if "." in str(topic) else str(topic)
    if kind == "DISTRIBUTED_CACHE":
        key = match_rule.get("key") or identifier
        return str(key).split(":", 1)[0] + ":*" if ":" in str(key) else str(key)
    if kind == "FILE":
        return str(match_rule.get("channel") or match_rule.get("source_kind") or "file-integration")
    if kind == "SCHEDULED_JOB":
        expression = match_rule.get("expression") or identifier
        return "cron:" + str(expression)[:40] if expression else "scheduled-job"
    if kind == "SDK":
        if identifier.endswith("Client"):
            return "*Client"
        if identifier.endswith("Service"):
            return "*Service"
        if identifier.endswith("SDK"):
            return "*SDK"
        return "sdk"
    return endpoint_module(item)


def avg_confidence(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(endpoint_confidence(item) for item in items) / len(items)


def render_endpoint_report(inventory: dict[str, Any], html_path: Path, title: str = "Endpoint Profiler Result") -> None:
    endpoints = list(inventory.get("endpoints") or [])
    services = list(inventory.get("services") or [])
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in endpoints:
        by_kind[item.get("kind") or "UNKNOWN"].append(item)
    kinds = sorted(by_kind)
    total = len(endpoints)
    ingress = sum(1 for item in endpoints if item.get("direction") == "ingress")
    egress = sum(1 for item in endpoints if item.get("direction") == "egress")
    avg_conf = avg_confidence(endpoints)
    service_names = sorted({endpoint_service(item) for item in endpoints} | {s.get("name") for s in services if s.get("name")})

    def esc(value: Any) -> str:
        return html.escape("" if value is None else str(value), quote=True)

    def pct(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    def bar(value: int, maximum: int) -> str:
        width = int((value / maximum) * 100) if maximum else 0
        return f'<span class="bar"><span style="width:{width}%"></span></span>'

    kind_counts = Counter(item.get("kind") for item in endpoints)
    max_kind_count = max(kind_counts.values(), default=1)
    kind_rows = []
    for kind in kinds:
        items = by_kind[kind]
        clusters = {endpoint_cluster_key(item) for item in items}
        kind_rows.append(
            "<tr>"
            f"<td><a href='#{esc(kind)}'>{esc(kind)}</a></td>"
            f"<td>{len(items)}</td>"
            f"<td>{pct(len(items), total)}</td>"
            f"<td>{sum(1 for item in items if item.get('direction') == 'ingress')}</td>"
            f"<td>{sum(1 for item in items if item.get('direction') == 'egress')}</td>"
            f"<td>{len({item.get('identifier') for item in items})}</td>"
            f"<td>{len(clusters)}</td>"
            f"<td>{avg_confidence(items):.2f}</td>"
            f"<td>{bar(len(items), max_kind_count)}</td>"
            "</tr>"
        )

    service_matrix_header = "".join(f"<th>{esc(kind)}</th>" for kind in kinds)
    service_matrix_rows = []
    for service in service_names:
        items = [item for item in endpoints if endpoint_service(item) == service]
        counts = Counter(item.get("kind") for item in items)
        service_matrix_rows.append(
            "<tr>"
            f"<td>{esc(service)}</td>"
            f"<td>{len(items)}</td>"
            + "".join(f"<td>{counts.get(kind, 0)}</td>" for kind in kinds)
            + "</tr>"
        )

    preflight = (inventory.get("audit") or {}).get("preflight") or {}
    capability_rows = []
    for hint in preflight.get("capability_hints") or []:
        evidence = hint.get("evidence") or []
        confirmed = hint.get("confirmed_kinds") or {}
        confirmed_samples = hint.get("confirmed_endpoint_samples") or []
        scan_plan = hint.get("scan_plan") or []
        capability_rows.append(
            "<tr>"
            f"<td>{esc(hint.get('capability'))}</td>"
            f"<td>{esc(hint.get('status'))}</td>"
            f"<td>{esc(', '.join(hint.get('potential_endpoint_kinds') or []))}</td>"
            f"<td>{esc(', '.join(f'{kind}:{count}' for kind, count in confirmed.items()) or '-')}</td>"
            f"<td>{esc('; '.join(str(value) for value in scan_plan[:3]) or '-')}</td>"
            f"<td>{esc('; '.join(hint.get('confirming_features') or []))}</td>"
            f"<td>{esc('; '.join(str(value) for value in evidence[:3]))}</td>"
            f"<td>{esc('; '.join(str(value) for value in confirmed_samples[:3]) or '-')}</td>"
            "</tr>"
        )
    capability_section = ""
    if capability_rows:
        capability_section = (
            "<section>"
            "<h2>Capability Hints</h2>"
            "<p class='muted'>Frameworks and dependencies are candidate clues that drive targeted scans; endpoints are emitted only after source or configuration usage evidence confirms a contract.</p>"
            "<table><thead><tr><th>Capability</th><th>Status</th><th>Potential Kinds</th><th>Confirmed Kinds</th><th>Scan Plan</th><th>Confirming Features</th><th>Capability Evidence</th><th>Confirmed Endpoint Samples</th></tr></thead>"
            f"<tbody>{''.join(capability_rows)}</tbody></table>"
            "</section>"
        )

    kind_sections = []
    for kind in kinds:
        items = by_kind[kind]
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            clusters[endpoint_cluster_key(item)].append(item)
        cluster_rows = []
        max_cluster_count = max((len(group) for group in clusters.values()), default=1)
        for cluster, group in sorted(clusters.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:80]:
            service_count = len({endpoint_service(item) for item in group})
            top_sources = Counter(endpoint_module(item) for item in group).most_common(3)
            examples = [item.get("identifier") for item in group[:5]]
            cluster_rows.append(
                "<tr>"
                f"<td>{esc(cluster)}</td>"
                f"<td>{len(group)}</td>"
                f"<td>{service_count}</td>"
                f"<td>{len({item.get('identifier') for item in group})}</td>"
                f"<td>{avg_confidence(group):.2f}</td>"
                f"<td>{esc(', '.join(f'{name} ({count})' for name, count in top_sources))}</td>"
                f"<td>{esc(' | '.join(str(example) for example in examples if example))}</td>"
                f"<td>{bar(len(group), max_cluster_count)}</td>"
                "</tr>"
            )
        low_samples = sorted(items, key=endpoint_confidence)[:12]
        sample_rows = []
        for item in low_samples:
            source = item.get("source") or {}
            sample_rows.append(
                "<tr>"
                f"<td>{endpoint_confidence(item):.2f}</td>"
                f"<td>{esc(item.get('kind'))}</td>"
                f"<td>{esc(endpoint_service(item))}</td>"
                f"<td>{esc(item.get('identifier'))}</td>"
                f"<td>{esc(source.get('file'))}:{esc(source.get('line'))}</td>"
                f"<td>{esc('; '.join((item.get('metadata') or {}).get('evidence') or []))}</td>"
                "</tr>"
            )
        detail_rows = []
        for item in sorted(items, key=lambda entry: (endpoint_service(entry), str(entry.get("identifier") or ""), (entry.get("source") or {}).get("file") or "")):
            source = item.get("source") or {}
            owner = item.get("owner") or {}
            metadata = item.get("metadata") or {}
            evidence = metadata.get("evidence") or []
            source_refs = metadata.get("source_refs") or []
            detail_rows.append(
                "<tr>"
                f"<td>{esc(item.get('kind'))}</td>"
                f"<td>{esc(item.get('direction'))}</td>"
                f"<td>{esc(endpoint_service(item))}</td>"
                f"<td>{esc(owner.get('service_scope'))}</td>"
                f"<td>{esc(item.get('identifier'))}</td>"
                f"<td>{esc(endpoint_cluster_key(item))}</td>"
                f"<td>{endpoint_confidence(item):.2f}</td>"
                f"<td>{esc(metadata.get('evidence_count'))}</td>"
                f"<td>{esc(source.get('file'))}:{esc(source.get('line'))}</td>"
                f"<td>{esc('; '.join(str(value) for value in evidence[:5]))}</td>"
                f"<td>{esc('; '.join(str(value) for value in source_refs[:12]))}</td>"
                "</tr>"
            )
        kind_sections.append(
            f"<section class='kind' id='{esc(kind)}'>"
            f"<h2>{esc(kind)}</h2>"
            "<div class='mini'>"
            f"<span>Total <b>{len(items)}</b></span>"
            f"<span>Clusters <b>{len(clusters)}</b></span>"
            f"<span>Unique identifiers <b>{len({item.get('identifier') for item in items})}</b></span>"
            f"<span>Avg confidence <b>{avg_confidence(items):.2f}</b></span>"
            "</div>"
            f"<details class='details-table' open><summary>All {esc(kind)} Endpoint Details ({len(items)})</summary>"
            "<table><thead><tr><th>Kind</th><th>Direction</th><th>Service</th><th>Scope</th><th>Identifier</th><th>Cluster</th><th>Conf.</th><th>Evidence Count</th><th>Primary Source</th><th>Evidence</th><th>Source Refs</th></tr></thead>"
            f"<tbody>{''.join(detail_rows)}</tbody></table>"
            "</details>"
            "<h3>Clusters</h3>"
            "<table><thead><tr><th>Cluster</th><th>Count</th><th>Services</th><th>Unique IDs</th><th>Avg Conf.</th><th>Top Modules</th><th>Examples</th><th>Share</th></tr></thead>"
            f"<tbody>{''.join(cluster_rows)}</tbody></table>"
            "<h3>Lowest Confidence Samples</h3>"
            "<table><thead><tr><th>Conf.</th><th>Kind</th><th>Service</th><th>Identifier</th><th>Source</th><th>Evidence</th></tr></thead>"
            f"<tbody>{''.join(sample_rows)}</tbody></table>"
            "</section>"
        )

    audit = inventory.get("audit") or {}
    generated_at = inventory.get("generated_at")
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{ color-scheme: light; --line:#d7dde5; --ink:#18212f; --muted:#667085; --bg:#f7f8fb; --panel:#ffffff; --accent:#2563eb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Arial, Helvetica, sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:24px 32px; background:#ffffff; border-bottom:1px solid var(--line); position:sticky; top:0; z-index:2; }}
    h1 {{ margin:0 0 8px; font-size:26px; }}
    h2 {{ margin:0 0 14px; font-size:21px; }}
    h3 {{ margin:18px 0 10px; font-size:15px; color:#344054; }}
    main {{ padding:24px 32px 48px; }}
    .meta {{ color:var(--muted); font-size:13px; display:flex; gap:16px; flex-wrap:wrap; }}
    .muted {{ color:var(--muted); font-size:13px; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:20px 0; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .card b {{ display:block; font-size:24px; margin-top:6px; }}
    section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; margin:18px 0; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid #eef1f5; padding:8px 10px; text-align:left; vertical-align:top; }}
    th {{ color:#344054; background:#f9fafb; }}
    td {{ max-width:560px; overflow-wrap:anywhere; }}
    a {{ color:var(--accent); text-decoration:none; }}
    .bar {{ display:block; height:8px; min-width:72px; background:#e7ecf4; border-radius:999px; overflow:hidden; }}
    .bar span {{ display:block; height:100%; background:#2563eb; }}
    .mini {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
    .mini span {{ border:1px solid var(--line); border-radius:999px; padding:5px 9px; color:#344054; background:#fbfcfe; font-size:12px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
    .nav a {{ border:1px solid var(--line); background:#fbfcfe; border-radius:999px; padding:5px 9px; font-size:12px; color:#344054; }}
    details {{ margin-top:18px; border:1px solid var(--line); border-radius:8px; background:#fbfcfe; }}
    summary {{ cursor:pointer; padding:10px 12px; font-weight:700; color:#344054; user-select:none; background:#f2f5f9; }}
    details table {{ background:#ffffff; }}
    .details-table[open] summary {{ border-bottom:1px solid var(--line); }}
    code {{ background:#eef2f7; padding:2px 4px; border-radius:4px; }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(title)}</h1>
    <div class="meta">
      <span>Generated: {esc(generated_at)}</span>
      <span>Source: <code>{esc(inventory.get("source_root"))}</code></span>
      <span>Graphify: {esc(audit.get("graphify_index_path") or "not used")}</span>
    </div>
    <nav class="nav">{"".join(f"<a href='#{esc(kind)}'>{esc(kind)}</a>" for kind in kinds)}</nav>
  </header>
  <main>
    <div class="cards">
      <div class="card">Total endpoints<b>{total}</b></div>
      <div class="card">Ingress<b>{ingress}</b></div>
      <div class="card">Egress<b>{egress}</b></div>
      <div class="card">Kinds<b>{len(kinds)}</b></div>
      <div class="card">Services<b>{len(service_names)}</b></div>
      <div class="card">Avg confidence<b>{avg_conf:.2f}</b></div>
    </div>
    <section>
      <h2>Kind Statistics</h2>
      <table><thead><tr><th>Kind</th><th>Count</th><th>Share</th><th>Ingress</th><th>Egress</th><th>Unique IDs</th><th>Clusters</th><th>Avg Conf.</th><th>Scale</th></tr></thead>
      <tbody>{"".join(kind_rows)}</tbody></table>
    </section>
    <section>
      <h2>Service x Kind Matrix</h2>
      <table><thead><tr><th>Service</th><th>Total</th>{service_matrix_header}</tr></thead>
      <tbody>{"".join(service_matrix_rows)}</tbody></table>
    </section>
    {capability_section}
    {"".join(kind_sections)}
  </main>
</body>
</html>
"""
    html_path.write_text(html_text, encoding="utf-8")


def write_service_splits(inventory: dict[str, Any], aggregate_path: Path) -> None:
    services = inventory.get("services") or []
    endpoints = inventory.get("endpoints") or []
    if not services:
        return

    output_root = aggregate_path.parent / "services"
    output_root.mkdir(parents=True, exist_ok=True)
    service_index = {service.get("name"): service for service in services if service.get("name")}
    by_service: dict[str, list[dict[str, Any]]] = {}
    for item in endpoints:
        service = (item.get("owner") or {}).get("service") or "unknown-service"
        by_service.setdefault(service, []).append(item)

    manifest: list[dict[str, Any]] = []
    for service_name in sorted(service_index):
        items = by_service.get(service_name, [])
        service_meta = service_index.get(service_name, {"name": service_name, "root": None, "dependencies": [], "scope_roots": []})
        service_payload = {
            "schema_version": inventory.get("schema_version"),
            "source_root": inventory.get("source_root"),
            "generated_at": inventory.get("generated_at"),
            "service": service_meta,
            "services": [service_meta],
            "endpoints": items,
            "audit": {
                **inventory.get("audit", {}),
                "split_from": str(aggregate_path),
                "split_service": service_name,
                "split_endpoint_count": len(items),
            },
        }
        service_dir = output_root / safe_service_name(service_name)
        service_dir.mkdir(parents=True, exist_ok=True)
        service_path = service_dir / "endpoints.json"
        service_path.write_text(json.dumps(service_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        render_endpoint_report(service_payload, service_dir / "endpoints_result.html", f"Endpoint Profiler Result - {service_name}")
        flat_service_path = aggregate_path.parent / f"{safe_service_name(service_name)}_endpoints.json"
        flat_service_path.write_text(json.dumps(service_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest.append(
            {
                "service": service_name,
                "file": str(service_path),
                "flat_file": str(flat_service_path),
                "html": str(service_dir / "endpoints_result.html"),
                "endpoints": len(items),
                "runtime": sum(1 for e in items if (e.get("owner") or {}).get("service_scope") == "runtime"),
                "dependency": sum(1 for e in items if (e.get("owner") or {}).get("service_scope") == "dependency"),
            }
        )
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract endpoint contracts from source code.")
    parser.add_argument("input_dir", nargs="?", default=".", help="Source root to scan.")
    parser.add_argument("--out", default=None, help="Output directory or JSON file path.")
    parser.add_argument("--graphify-index", default=None, help="Explicit path to graphify-out/graph.json.")
    parser.add_argument("--ensure-graphify", action="store_true", help="Run graphify first when no usable graphify-out/graph.json is found.")
    parser.add_argument("--graphify-mode", default="", choices=["", "deep"], help="Optional graphify mode used with --ensure-graphify.")
    args = parser.parse_args()

    root = Path(args.input_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Input directory does not exist: {root}")

    graphify_index = Path(args.graphify_index).resolve() if args.graphify_index else None
    inventory = build_inventory(root, graphify_index, ensure_graphify=args.ensure_graphify, graphify_mode=args.graphify_mode)
    out_arg = Path(args.out) if args.out else root / "endpoint-profiler-out"
    out_path = out_arg if out_arg.suffix.lower() == ".json" else out_arg / "endpoints.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path = out_path.parent / "endpoints_result.html"
    render_endpoint_report(inventory, report_path)
    write_service_splits(inventory, out_path)
    print(str(out_path))
    print(str(report_path))
    print(f"endpoints={len(inventory['endpoints'])}")
    if inventory.get("services"):
        print(f"services={len(inventory['services'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
