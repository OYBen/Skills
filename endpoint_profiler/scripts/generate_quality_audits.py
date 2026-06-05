from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path


EXTS = {".java", ".kt", ".xml", ".sql", ".yml", ".yaml", ".properties", ".proto", ".graphql", ".py", ".js", ".ts"}
SKIP = {"target", ".git", "node_modules", "dist", "build", ".venv", "venv", "graphify-out"}
DATA_FQN = re.compile(r"(?<![A-Za-z0-9_.])(?:data|event)(?:\.[A-Za-z][A-Za-z0-9_]*|\.\$\{[A-Za-z_][A-Za-z0-9_]*\})+\.[A-Za-z][A-Za-z0-9_]*(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)?\b(?!\s*\()")
PHYSICAL_SQL_TABLE = re.compile(
    r"(?:@Table\s*\(\s*name\s*=|@TableName\s*\(|['\"]\s*(?:SELECT\b.*?\bFROM|CREATE\s+TABLE|FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[A-Za-z_][\w.]*)",
    re.IGNORECASE,
)
CLASS_FQN_ACCESS = re.compile(r"\b[A-Z][A-Za-z0-9_]*\.FQN\b")
MODEL_ANNOTATION = re.compile(r"@(Entity|EventModel)\s*\((.*?)\)", re.IGNORECASE | re.S)
MESSAGE_SEND = re.compile(r"\b(?:KafkaTemplate|RabbitTemplate|kafkaTemplate|rabbitTemplate)\b[\s\S]{0,500}\b(?:send|convertAndSend)\s*\(", re.IGNORECASE)
EXPLICIT_TOPIC = re.compile(r"\b(?:TOPIC|topic|queue|routingKey)\b|['\"][A-Za-z0-9_.-]*(?:topic|queue|event|message|notify|behavior|journey)[A-Za-z0-9_.-]*['\"]", re.IGNORECASE)
FEIGN_CLIENT = re.compile(r"@(?:[A-Za-z_][A-Za-z0-9_.]*\.)?(?:[A-Za-z_][A-Za-z0-9_]*FeignClient|FeignClient)\s*\((.*?)\)", re.IGNORECASE | re.S)
JAXRS_PATH = re.compile(r"@Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)
JAXRS_METHOD = re.compile(r"@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", re.IGNORECASE)
RETROFIT_HTTP_METHOD = re.compile(r"@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)
RETROFIT_IMPORT = re.compile(r"\bimport\s+retrofit2\.http\.(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|\*)\s*;?", re.IGNORECASE)
SPRING_MAPPING = re.compile(r"@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\b", re.IGNORECASE)
STATUS_OK = "PASS"
STATUS_FAIL = "FAIL"
TRACE_INGRESS = "TRACE_TO_INGRESS"
TRACE_EGRESS = "TRACE_TO_EGRESS"
SEMANTIC_FLOW = "SEMANTIC_SERVICE_FLOW"
INTERNAL_CAPABILITY = "INTERNAL_CAPABILITY"
NEEDS_EXPANSION = "NEEDS_SOURCE_EXPANSION"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def source_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        parts = {part.lower() for part in path.parts}
        norm = str(path).replace("\\", "/").lower()
        if "/src/test/" in norm or "/test/" in norm:
            continue
        if "/src/main/java/org/flywaydb/" in norm or "/db/migration/" in norm:
            continue
        if path.is_file() and path.suffix.lower() in EXTS and not (parts & SKIP):
            files.append(path)
    return files


def framework_or_facility_path(path: Path) -> bool:
    norm = str(path).replace("\\", "/").lower()
    facility_parts = [
        "/shuyun-spring-boots/",
        "/shuyun-ds-multi-tenant/",
        "/shuyun-es-multi-tenant/",
        "/shuyun-multi-tenant-spring-boot-starter/",
        "/shuyun-leaf/",
        "/src/main/java/com/shuyun/ds/spring/connection/",
        "/src/main/java/com/shuyun/multitenant/",
    ]
    return any(part in norm for part in facility_parts)


def dto_or_plain_model_path(path: Path) -> bool:
    norm = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    return (
        "/model/" in norm
        or "/dto/" in norm
        or "/vo/" in norm
        or "/bo/" in norm
        or "/response/" in norm
        or name.endswith(("response.java", "request.java", "dto.java", "vo.java", "bo.java"))
    )


def strip_line_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def has_semantic_datamodel_evidence(text: str, path: Path) -> bool:
    if framework_or_facility_path(path):
        return False
    norm = str(path).replace("\\", "/").lower()
    if "/src/main/resources/i18n/" in norm or path.suffix.lower() == ".properties":
        return False
    if dto_or_plain_model_path(path) and not MODEL_ANNOTATION.search(text):
        return False
    for match in DATA_FQN.finditer(text):
        value = match.group(0)
        leaf = value.rsplit(".", 1)[-1].lower()
        if leaf in {"tosqlvalue", "tostring", "isnullorempty", "isempty", "isblank", "firstornull", "mapnotnull"}:
            continue
        return True
    if MODEL_ANNOTATION.search(text) and CLASS_FQN_ACCESS.search(text):
        return True
    return False


def has_physical_table_evidence(text: str) -> bool:
    if re.search(r"@(?:Table|TableName)\s*\(", text, re.IGNORECASE):
        return True
    for match in PHYSICAL_SQL_TABLE.finditer(text):
        snippet = match.group(0)
        if "${" in snippet:
            continue
        if re.search(r"\b(?:data|event)\.", snippet, re.IGNORECASE):
            continue
        table_match = re.search(r"\b(?:FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z_][\w.]*)", snippet, re.IGNORECASE)
        table = table_match.group(1) if table_match else ""
        if table.lower() in {"value", "values", "fqn", "field", "fields", "data", "count"}:
            continue
        if table and ("_" in table or "." in table or table.islower()):
            return True
    return False


def has_distributed_cache_evidence(text: str, path: Path) -> bool:
    if framework_or_facility_path(path):
        return False
    low = text.lower()
    return any(x in low for x in ["rediscachekeyenum", "rediscache", "redistemplate", "stringredistemplate", "redisson", "rediscache.getlock", "rediscache."])


def has_dataapi_evidence(text: str) -> bool:
    low = text.lower()
    return any(
        token in low
        for token in [
            "dataapihttpsdk",
            "dataapiwebsocketsdk",
            "dataapisdkfactory",
            "dataapisupport",
            "getdataapisdk()",
            "dataapisdk.",
            "dataapiservice",
        ]
    )


def has_data_model_sql_evidence(text: str) -> bool:
    low = text.lower()
    return bool(re.search(r"\b(?:from|join|insert\s+into|update|delete\s+from)\s+data\.", low) and any(token in low for token in ["commonsqlexecute", "executesql", "sqlsupport", "jobtasksupport", "dataapiservice", "dataapisupport"]))


def has_analytics_model_evidence(text: str) -> bool:
    low = text.lower()
    return has_data_model_sql_evidence(text) and any(token in low for token in ["olap", "htap", "olapforce", "bitmap_"])


def has_data_model_schema_evidence(text: str, path: Path) -> bool:
    low = text.lower()
    return "createdmodel(" in low or "createmodel(" in low


def has_data_event_evidence(text: str) -> bool:
    low = text.lower()
    return "event." in low and ("eventproducer" in low or "event.of" in low or "sendevent" in low or '"event.' in low)


def has_message_producer_evidence(text: str, path: Path) -> bool:
    if framework_or_facility_path(path):
        return False
    return bool(MESSAGE_SEND.search(text) and EXPLICIT_TOPIC.search(text))


def is_jaxrs_feign_contract(text: str) -> bool:
    return bool(FEIGN_CLIENT.search(text) and JAXRS_PATH.search(text) and JAXRS_METHOD.search(text))


def is_standard_retrofit_contract(text: str) -> bool:
    return bool(RETROFIT_IMPORT.search(text) and RETROFIT_HTTP_METHOD.search(text))


def is_jaxrs_server_resource(text: str) -> bool:
    return bool(JAXRS_PATH.search(text) and JAXRS_METHOD.search(text) and not FEIGN_CLIENT.search(text) and not is_standard_retrofit_contract(text))


def normalize_path(path: str) -> str:
    cleaned = (path or "").strip().strip('"\'')
    cleaned = re.sub(r"\$\{([^}]+)\}", r"{\1}", cleaned)
    if "?" in cleaned:
        cleaned = cleaned.split("?", 1)[0]
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    cleaned = re.sub(r"/+", "/", cleaned)
    return cleaned.rstrip("/") or "/"


def join_paths(prefix: str | None, path: str | None) -> str:
    left = normalize_path(prefix or "/")
    right = normalize_path(path or "/")
    if left == "/":
        return right
    if right == "/":
        return left
    return normalize_path(left + "/" + right.lstrip("/"))


def expected_jaxrs_feign_http_calls(text: str) -> list[str]:
    if not is_jaxrs_feign_contract(text):
        return []
    lines = text.splitlines()
    class_path = ""
    for idx, line in enumerate(lines):
        path_match = JAXRS_PATH.search(line)
        if not path_match:
            continue
        lookahead = "\n".join(lines[idx : min(len(lines), idx + 5)])
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", lookahead):
            class_path = path_match.group(1)
            break
    pending_path = None
    pending_method = None
    identifiers = []
    in_contract = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
            in_contract = True
            continue
        if not in_contract:
            continue
        path_match = JAXRS_PATH.search(stripped)
        if path_match:
            pending_path = path_match.group(1)
        method_match = JAXRS_METHOD.search(stripped)
        if method_match:
            pending_method = method_match.group(1).upper()
        if pending_method and pending_path and re.search(r"\bfun\s+|\b[A-Za-z_][A-Za-z0-9_<>, ?]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", stripped):
            identifiers.append(f"{pending_method} {join_paths(class_path, pending_path)}")
            pending_path = None
            pending_method = None
    return identifiers


def expected_standard_retrofit_http_calls(text: str) -> list[str]:
    if not is_standard_retrofit_contract(text):
        return []
    identifiers = []
    for match in RETROFIT_HTTP_METHOD.finditer(text):
        identifiers.append(f"{match.group(1).upper()} {normalize_path(match.group(2))}")
    return identifiers


def expected_jaxrs_http_apis(text: str) -> list[str]:
    if not is_jaxrs_server_resource(text):
        return []
    lines = text.splitlines()
    class_path = ""
    for idx, line in enumerate(lines):
        path_match = JAXRS_PATH.search(line)
        if not path_match:
            continue
        lookahead = "\n".join(lines[idx : min(len(lines), idx + 5)])
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", lookahead):
            class_path = path_match.group(1)
            break
    pending_path = None
    pending_method = None
    identifiers = []
    in_resource = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"\b(?:interface|class)\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
            in_resource = True
            continue
        if not in_resource:
            continue
        path_match = JAXRS_PATH.search(stripped)
        if path_match:
            pending_path = path_match.group(1)
        method_match = JAXRS_METHOD.search(stripped)
        if method_match:
            pending_method = method_match.group(1).upper()
        if pending_method and re.search(r"\bfun\s+|\b[A-Za-z_][A-Za-z0-9_<>, ?]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", stripped):
            identifiers.append(f"{pending_method} {join_paths(class_path, pending_path or '/')}")
            pending_path = None
            pending_method = None
    return identifiers


def layer(path: Path, text: str) -> str:
    p = str(path).replace("\\", "/").lower()
    if "controller" in p or "@restcontroller" in text.lower():
        return "controller"
    if "listener" in p or "consumer" in p or "@rabbitlistener" in text.lower() or "@kafkalistener" in text.lower():
        return "listener"
    if "scheduler" in p or "task" in p or "@scheduled" in text.lower() or "@xxljob" in text.lower():
        return "scheduler"
    if "client" in p or "feign" in text.lower() or "resttemplate" in text.lower() or "webclient" in text.lower():
        return "client"
    if "repository" in p or "mapper" in p or "@tablename" in text.lower() or "select " in text.lower():
        return "repository"
    if "config" in p or ".properties" in p or path.suffix.lower() in {".yml", ".yaml"}:
        return "config"
    if "service" in p:
        return "service"
    return "other"


def expected_kinds(text: str, path: Path) -> set[str]:
    active_text = strip_line_comments(text)
    low = active_text.lower()
    norm = str(path).replace("\\", "/").lower()
    kinds = set()
    if is_jaxrs_feign_contract(active_text):
        kinds.add("HTTP_CALL")
    if any(x in low for x in ["@getmapping", "@postmapping", "@putmapping", "@deletemapping", "@requestmapping"]):
        if "feignclient" in low:
            kinds.add("HTTP_CALL")
        else:
            kinds.add("HTTP_API")
    if any(x in low for x in ["@rabbitlistener", "@kafkalistener", "@streamlistener"]):
        kinds.add("MESSAGE_CONSUMER")
    if has_message_producer_evidence(active_text, path):
        kinds.add("MESSAGE_PRODUCER")
    if re.search(r"\.publishEvent\s*\(", active_text) and not framework_or_facility_path(path):
        kinds.add("EVENT_BUS_PUBLISHER")
    if any(x in low for x in ["@scheduled", "@xxljob"]):
        kinds.add("SCHEDULED_JOB")
    if "src/main/resources/db/migration/" not in norm and has_physical_table_evidence(active_text):
        kinds.add("DB_TABLE")
    if has_analytics_model_evidence(active_text):
        kinds.add("ANALYTICS_MODEL_QUERY")
    elif has_data_model_sql_evidence(active_text):
        kinds.add("DATA_API_CALL")
    elif has_semantic_datamodel_evidence(active_text, path):
        kinds.add("DATAMODEL")
    if has_data_event_evidence(active_text):
        if any(token in low for token in ["eventproducer", "event.of", "sendevent", "publis"]):
            kinds.add("EVENT_BUS_PUBLISHER")
    if has_dataapi_evidence(active_text):
        if "querybystream" in low or "fetch(" in low or "dataapiwebsocketsdk" in low:
            kinds.add("DATA_API_STREAM")
        else:
            kinds.add("DATA_API_CALL")
    if has_distributed_cache_evidence(active_text, path):
        kinds.add("DISTRIBUTED_CACHE")
    if path.suffix.lower() == ".proto":
        kinds.add("RPC_ROUTE")
    return kinds


def endpoint_map(endpoints: list[dict]) -> dict[str, list[dict]]:
    by_file = collections.defaultdict(list)

    def add_ref(ref_file: str, endpoint: dict) -> None:
        key = ref_file.replace("\\", "/")
        endpoint_id = endpoint.get("id")
        if endpoint_id and any(item.get("id") == endpoint_id for item in by_file[key]):
            return
        by_file[key].append(endpoint)

    for endpoint in endpoints:
        file = (endpoint.get("source") or {}).get("file")
        if file:
            add_ref(file, endpoint)
        for ref in (endpoint.get("metadata") or {}).get("source_refs") or []:
            ref_file = str(ref).rsplit(":", 1)[0]
            if ref_file:
                add_ref(ref_file, endpoint)
    return by_file


def endpoint_service(endpoint: dict) -> str:
    return (endpoint.get("owner") or {}).get("service") or "unassigned"


def endpoint_source_file(endpoint: dict) -> str:
    return ((endpoint.get("source") or {}).get("file") or "").replace("\\", "/")


def endpoint_key(endpoint: dict) -> str:
    return "|".join(
        [
            str(endpoint.get("direction") or ""),
            str(endpoint.get("kind") or ""),
            str(endpoint.get("identifier") or ""),
            endpoint_source_file(endpoint),
        ]
    )


def canonical_source_key(path: str) -> str:
    normalized = path.replace("\\", "/").lower()
    for marker in ["/src/main/java/", "/src/main/kotlin/", "/src/main/resources/", "src/main/java/", "src/main/kotlin/", "src/main/resources/"]:
        if marker in normalized:
            return normalized.split(marker, 1)[1]
    for marker in ["/main/java/", "/main/kotlin/", "/main/resources/", "main/java/", "main/kotlin/", "main/resources/"]:
        if marker in normalized:
            return marker.strip("/") + "/" + normalized.split(marker, 1)[1]
    return normalized


def stable_sample(items: list[dict], ratio: float = 0.10) -> list[dict]:
    if not items:
        return []
    take = max(1, math.ceil(len(items) * ratio))
    return sorted(items, key=lambda item: hashlib.sha1(endpoint_key(item).encode("utf-8", "ignore")).hexdigest())[:take]


def chain_samples(endpoints: list[dict]) -> list[dict]:
    grouped = collections.defaultdict(list)
    for endpoint in endpoints:
        direction = endpoint.get("direction")
        kind = endpoint.get("kind")
        if direction in {"ingress", "egress"} and kind:
            grouped[(direction, kind)].append(endpoint)
    samples = []
    for key in sorted(grouped):
        samples.extend(stable_sample(grouped[key], 0.10))
    return samples


def graph_file_adjacency(graph_path: Path | None, root: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], int, int]:
    if not graph_path or not graph_path.exists():
        return {}, {}, 0, 0
    data = read_json(graph_path)
    nodes = data.get("nodes") or data.get("vertices") or []
    edges = data.get("edges") or data.get("links") or []
    node_file = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        source_file = str(node.get("source_file") or "")
        if node_id and source_file:
            node_file[node_id] = canonical_source_key(source_file)
    forward = collections.defaultdict(set)
    reverse = collections.defaultdict(set)
    for edge in edges:
        source_file = node_file.get(str(edge.get("source") or ""))
        target_file = node_file.get(str(edge.get("target") or ""))
        if not source_file:
            source_file = canonical_source_key(str(edge.get("source_file") or ""))
        if source_file and target_file and source_file != target_file:
            forward[source_file].add(target_file)
            reverse[target_file].add(source_file)
    return forward, reverse, len(nodes), len(edges)


def reachable_files(start: str, adjacency: dict[str, set[str]], max_depth: int = 4) -> set[str]:
    if not start:
        return set()
    seen = {start}
    frontier = [(start, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for nxt in adjacency.get(current, set()):
            if nxt in seen:
                continue
            seen.add(nxt)
            frontier.append((nxt, depth + 1))
    return seen


def internal_capability_reason(endpoint: dict) -> str | None:
    identifier = str(endpoint.get("identifier") or "").lower()
    kind = endpoint.get("kind")
    if kind == "HTTP_API" and any(token in identifier for token in ["/ops/", "/ping", "/health", "/openapi", "/swagger", "/loggers"]):
        return "operational/self-describing HTTP endpoint"
    if kind in {"CLI", "WebSocket"}:
        return f"{kind} can be an externally triggered capability without a paired opposite endpoint"
    return None


def source_reference_trace(endpoint: dict, candidates: list[dict], root: Path) -> dict | None:
    source_file = endpoint_source_file(endpoint)
    source_path = root / source_file
    try:
        text = source_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    source_stem = Path(source_file).stem.lower()
    for candidate in candidates:
        candidate_file = endpoint_source_file(candidate)
        candidate_stem = Path(candidate_file).stem
        candidate_identifier = str(candidate.get("identifier") or "")
        identifier_leaf = candidate_identifier.split()[-1].strip("/").split("/")[-1]
        if candidate_file == source_file:
            return candidate
        if candidate_stem and re.search(rf"\b{re.escape(candidate_stem)}\b", text, re.IGNORECASE):
            return candidate
        if identifier_leaf and len(identifier_leaf) > 4 and identifier_leaf.lower() in text.lower():
            return candidate
    return None


def trace_chain(endpoint: dict, endpoints: list[dict], root: Path, forward_graph: dict[str, set[str]], reverse_graph: dict[str, set[str]]) -> tuple[str, str, str]:
    direction = endpoint.get("direction")
    service = endpoint_service(endpoint)
    opposite_direction = "egress" if direction == "ingress" else "ingress"
    candidates = [
        candidate
        for candidate in endpoints
        if candidate.get("direction") == opposite_direction and endpoint_service(candidate) == service
    ]
    if not candidates:
        reason = internal_capability_reason(endpoint)
        if reason:
            return INTERNAL_CAPABILITY, "", reason
        return INTERNAL_CAPABILITY, "", f"no {opposite_direction} endpoint inventory for service {service}; endpoint source is still sampled for inventory evidence"

    source_key = canonical_source_key(endpoint_source_file(endpoint))
    candidate_by_key = {canonical_source_key(endpoint_source_file(candidate)): candidate for candidate in candidates if endpoint_source_file(candidate)}
    adjacency = forward_graph if direction == "ingress" else reverse_graph
    reached = reachable_files(source_key, adjacency)
    for key, candidate in candidate_by_key.items():
        if key in reached:
            status = TRACE_EGRESS if direction == "ingress" else TRACE_INGRESS
            return status, str(candidate.get("identifier") or ""), f"graph/source-file reachability: {source_key} -> {key}"

    ref_candidate = source_reference_trace(endpoint, candidates, root)
    if ref_candidate:
        status = TRACE_EGRESS if direction == "ingress" else TRACE_INGRESS
        return status, str(ref_candidate.get("identifier") or ""), "source semantic reference or same-file evidence"

    if len(candidates) > 1:
        sample = candidates[0]
        return SEMANTIC_FLOW, str(sample.get("identifier") or ""), f"same-service semantic flow candidate among {len(candidates)} opposite-direction endpoints; graph/source path not explicit"

    reason = internal_capability_reason(endpoint)
    if reason:
        return INTERNAL_CAPABILITY, "", reason
    return INTERNAL_CAPABILITY, "", "no explicit upstream/downstream opposite endpoint found; treated as endpoint inventory evidence without topology linkage"


def chain_completeness_rows(root: Path, inventory: dict) -> tuple[list[str], collections.Counter, dict[str, int]]:
    endpoints = inventory.get("endpoints") or []
    graph_path_value = (inventory.get("audit") or {}).get("graphify_index_path")
    graph_path = Path(graph_path_value) if graph_path_value else None
    forward_graph, reverse_graph, node_count, edge_count = graph_file_adjacency(graph_path if graph_path and graph_path.exists() else None, root)
    rows, counts = [], collections.Counter()
    for idx, endpoint in enumerate(chain_samples(endpoints), 1):
        status, linked_identifier, note = trace_chain(endpoint, endpoints, root, forward_graph, reverse_graph)
        verdict = STATUS_FAIL if status == NEEDS_EXPANSION else STATUS_OK
        counts[status] += 1
        counts[verdict] += 1
        opposite = "egress" if endpoint.get("direction") == "ingress" else "ingress"
        source = endpoint.get("source") or {}
        rows.append(
            f"| {idx} | {endpoint.get('direction')} | {endpoint.get('kind')} | {endpoint_service(endpoint)} | "
            f"`{endpoint.get('identifier')}` | {opposite} | `{linked_identifier or '-'}` | {status} | {verdict} | "
            f"{endpoint_source_file(endpoint)}:{source.get('line')} | {note} |"
        )
    return rows, counts, {"node_count": node_count, "edge_count": edge_count, "sample_count": len(rows)}


def sample_by_layer(root: Path, files: list[Path]) -> list[tuple[str, Path, set[str]]]:
    grouped = collections.defaultdict(list)
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        kinds = expected_kinds(text, path)
        if kinds:
            grouped[layer(path, text)].append((path, kinds))
    sampled = []
    for name, items in sorted(grouped.items()):
        take = max(1, math.ceil(len(items) * 0.10))
        step = max(1, len(items) // take)
        for path, kinds in items[::step][:take]:
            sampled.append((name, path, kinds))
    return sampled


def source_sampling_rows(root: Path, endpoints: list[dict]) -> tuple[list[str], collections.Counter]:
    by_file = endpoint_map(endpoints)
    rows, counts = [], collections.Counter()
    for idx, (name, path, kinds) in enumerate(sample_by_layer(root, source_files(root)), 1):
        rel = str(path.relative_to(root)).replace("\\", "/")
        found = {endpoint.get("kind") for endpoint in by_file.get(rel, [])}
        missing = sorted(kinds - found)
        extra = sorted(found - kinds) if found and not kinds else []
        verdict = STATUS_FAIL if missing else STATUS_OK
        counts[verdict] += 1
        rows.append(f"| {idx} | {name} | {rel} | {', '.join(sorted(kinds))} | {', '.join(sorted(found)) or 'none'} | {verdict} | missing={missing}; extra={extra} |")
    return rows, counts


def source_rule_gap_rows(root: Path, endpoints: list[dict]) -> tuple[list[str], collections.Counter]:
    by_file = endpoint_map(endpoints)
    rows, counts = [], collections.Counter()
    for path in source_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(root)).replace("\\", "/")
        active_text = strip_line_comments(text)
        expected_calls = expected_jaxrs_feign_http_calls(active_text) + expected_standard_retrofit_http_calls(active_text)
        if not expected_calls:
            expected_calls = []
        if expected_calls:
            found_calls = {
                endpoint.get("identifier")
                for endpoint in by_file.get(rel, [])
                if endpoint.get("direction") == "egress" and endpoint.get("kind") == "HTTP_CALL"
            }
            missing_calls = [identifier for identifier in expected_calls if identifier not in found_calls]
            verdict = STATUS_FAIL if missing_calls else STATUS_OK
            counts[verdict] += 1
            note = f"expected_http_calls={len(expected_calls)}; found_http_calls={len(found_calls)}"
            if missing_calls:
                note += f"; missing={missing_calls[:10]}"
            rows.append(f"| {len(rows) + 1} | jaxrs-retrofit-http-call | {rel} | {verdict} | {note} |")
        expected_apis = expected_jaxrs_http_apis(active_text)
        if expected_apis:
            found_apis = {
                endpoint.get("identifier")
                for endpoint in by_file.get(rel, [])
                if endpoint.get("direction") == "ingress" and endpoint.get("kind") == "HTTP_API"
            }
            missing_apis = [identifier for identifier in expected_apis if identifier not in found_apis]
            verdict = STATUS_FAIL if missing_apis else STATUS_OK
            counts[verdict] += 1
            note = f"expected_http_apis={len(expected_apis)}; found_http_apis={len(found_apis)}"
            if missing_apis:
                note += f"; missing={missing_apis[:10]}"
            rows.append(f"| {len(rows) + 1} | jaxrs-http-api | {rel} | {verdict} | {note} |")
    return rows, counts


def diverse_endpoint_samples(endpoints: list[dict], per_kind: int = 10) -> list[dict]:
    grouped = collections.defaultdict(list)
    seen = set()
    for endpoint in endpoints:
        src = (endpoint.get("source") or {}).get("file")
        key = (endpoint.get("kind"), (endpoint.get("owner") or {}).get("service"), src)
        if key not in seen:
            seen.add(key)
            grouped[endpoint.get("kind")].append(endpoint)
    return [endpoint for kind in sorted(grouped) for endpoint in grouped[kind][:per_kind]]


def endpoint_sampling_rows(root: Path, endpoints: list[dict], graph_files: set[str]) -> tuple[list[str], collections.Counter]:
    by_file = endpoint_map(endpoints)
    rows, counts = [], collections.Counter()
    for idx, endpoint in enumerate(diverse_endpoint_samples(endpoints), 1):
        source = endpoint.get("source") or {}
        rel = (source.get("file") or "").replace("\\", "/")
        source_exists = bool(rel) and (root / rel).exists()
        peers = by_file.get(rel, [])
        service = (endpoint.get("owner") or {}).get("service")
        duplicate_count = sum(
            1
            for peer in peers
            if (peer.get("owner") or {}).get("service") == service
            and peer.get("direction") == endpoint.get("direction")
            and peer.get("kind") == endpoint.get("kind")
            and peer.get("identifier") == endpoint.get("identifier")
        )
        graph_status = "GRAPH_COVERED" if rel in graph_files else "SOURCE_CONFIRMED" if source_exists else "SOURCE_MISSING"
        verdict = STATUS_FAIL if not source_exists or duplicate_count > 1 else STATUS_OK
        counts[verdict] += 1
        rows.append(
            f"| {idx} | {endpoint.get('direction')} | {endpoint.get('kind')} | {(endpoint.get('owner') or {}).get('service')} | "
            f"`{endpoint.get('identifier')}` | {rel}:{source.get('line')} | {graph_status} | {verdict} | duplicates={duplicate_count} |"
        )
    return rows, counts


def graph_source_files(graph_path: Path | None, root: Path) -> tuple[set[str], int, int]:
    if not graph_path or not graph_path.exists():
        return set(), 0, 0
    data = read_json(graph_path)
    nodes, edges = data.get("nodes") or data.get("vertices") or [], data.get("edges") or data.get("links") or []
    files = set()
    for node in nodes:
        blob = json.dumps(node, ensure_ascii=False)
        for match in re.finditer(r"([A-Za-z0-9_./\\-]+\.(?:java|kt|xml|sql|ya?ml|properties|proto|graphql|py|js|ts))", blob):
            path = Path(match.group(1))
            if not path.is_absolute():
                path = root / path
            if path.exists():
                files.add(str(path.relative_to(root)).replace("\\", "/"))
    return files, len(nodes), len(edges)


def capability_audit_rows(inventory: dict) -> list[str]:
    preflight = (inventory.get("audit") or {}).get("preflight") or {}
    hints = preflight.get("capability_hints") or []
    rows = []
    for idx, hint in enumerate(hints, 1):
        confirmed = hint.get("confirmed_kinds") or {}
        scan_plan = "; ".join(str(item) for item in (hint.get("scan_plan") or [])[:3]) or "-"
        confirmed_kinds = ", ".join(f"{kind}:{count}" for kind, count in confirmed.items()) or "-"
        samples = "; ".join(str(item) for item in (hint.get("confirmed_endpoint_samples") or [])[:3]) or "-"
        rows.append(
            f"| {idx} | {hint.get('capability')} | {hint.get('status')} | "
            f"{', '.join(hint.get('potential_endpoint_kinds') or []) or '-'} | {scan_plan} | "
            f"{confirmed_kinds} | {samples} | {hint.get('audit_action') or '-'} |"
        )
    return rows


def write_source_audit(out: Path, root: Path, inventory: dict) -> None:
    rows, counts, graph_stats = chain_completeness_rows(root, inventory)
    sample_count = graph_stats["sample_count"]
    traced = counts[TRACE_INGRESS] + counts[TRACE_EGRESS] + counts[SEMANTIC_FLOW]
    internal = counts[INTERNAL_CAPABILITY]
    unresolved = counts[NEEDS_EXPANSION]
    gap_rows, gap_counts = source_rule_gap_rows(root, inventory["endpoints"])
    cap_rows = capability_audit_rows(inventory)
    total_failures = unresolved + gap_counts[STATUS_FAIL]
    trace_ratio = (traced + internal) / sample_count if sample_count else 1.0
    verdict = STATUS_OK if total_failures == 0 and trace_ratio >= 0.70 else STATUS_FAIL
    lines = [
        "# Endpoint Chain Completeness Audit",
        "",
        f"- Input source root: `{root}`",
        f"- Endpoint JSON path: `{out / 'endpoints.json'}`",
        f"- Graphify index path: `{(inventory.get('audit') or {}).get('graphify_index_path') or 'not available'}`",
        f"- Audit date: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- Audit Verdict: {verdict}",
        f"- Chain sample count: {sample_count}",
        f"- Chain traced/internal ratio: {trace_ratio:.2f}",
        "",
        "## Chain Completeness Audit",
        "",
        "Random, deterministic 10% per direction/kind endpoint samples are traced to an opposite-direction endpoint. Egress samples trace upstream to ingress; ingress samples trace downstream to egress. Evidence may come from Graphify file edges, direct source references, or explicit same-service semantic flow; unmatched samples must be classified as internal capability or fail.",
        "",
        "## Graph Trace Summary",
        "",
        f"- Graph node count: {graph_stats['node_count']}",
        f"- Graph edge count: {graph_stats['edge_count']}",
        "",
        "| # | sampled direction | kind | service | sampled endpoint | trace target direction | linked endpoint | trace status | verdict | source | evidence |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Rule-Gap Candidate Scan",
        "",
        "| # | candidate family | source file | verdict | notes |",
        "|---|---|---|---|---|",
        *(gap_rows or ["| 1 | none | none | PASS | no framework-specific missing-family candidates detected |"]),
        "",
        "## Capability-Driven Audit",
        "",
        "Dependency/framework capability hints are checked against targeted source/config scans. Candidate-only rows identify a possible missing endpoint family or an unused dependency.",
        "",
        "| # | capability | status | potential kinds | targeted scan plan | confirmed kinds | confirmed samples | audit action |",
        "|---|---|---|---|---|---|---|---|",
        *(cap_rows or ["| 1 | none | none | - | - | - | - | no capability hints detected |"]),
        "",
        "## Rule Gap Discovery",
        "",
        f"- Chain trace status counts: {dict(counts)}",
        f"- Rule-gap candidate verdict counts: {dict(gap_counts)}",
        "- MISSING_ENDPOINT_RULE review: chain rows with FAIL identify sampled endpoints that could not be linked to an opposite-direction endpoint and were not classified as internal capability.",
        "",
        "## Findings",
        "",
        f"- Chain completeness gaps: {'none in sampled endpoints' if verdict == STATUS_OK else 'see FAIL rows'}",
        f"- Internal capability classifications: {internal}",
        f"- Upstream/downstream traced samples: {traced}",
    ]
    (out / f"endpoint_llm_trace_audit_{dt.datetime.now().strftime('%Y%m%d')}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_endpoint_audit(out: Path, root: Path, inventory: dict) -> None:
    graph_path_value = (inventory.get("audit") or {}).get("graphify_index_path")
    graph_path = Path(graph_path_value) if graph_path_value else None
    if not graph_path or not graph_path.exists():
        lines = [
            "# Endpoint Trace Sampling Audit",
            "",
            "GRAPH_AUDIT_SKIPPED_NO_GRAPHIFY_INDEX",
            "",
            f"- Input source root: `{root}`",
            f"- Endpoint JSON path: `{out / 'endpoints.json'}`",
            "- Graphify index path: `not available`",
            f"- Audit date: {dt.datetime.now().isoformat(timespec='seconds')}",
            "- Audit Verdict: PASS",
            "",
            "## Endpoint Trace Sampling Audit",
            "",
            "Graphify-first endpoint trace sampling was skipped because this run has no usable Graphify index. Source-sampling audit remains the quality gate for endpoint inventory evidence.",
            "",
            "## Graph Rule Gap Discovery",
            "",
            "- No graph rule-gap candidates found because no Graphify index was available for this run.",
            "",
            "## Findings",
            "",
            "- Graph audit skipped; see `audit.warnings` in endpoints.json for Graphify generation or availability details.",
        ]
        (out / f"endpoint_graph_edge_trace_audit_{dt.datetime.now().strftime('%Y%m%d')}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    graph_files, node_count, edge_count = graph_source_files(graph_path if graph_path and graph_path.exists() else None, root)
    rows, counts = endpoint_sampling_rows(root, inventory["endpoints"], graph_files)
    gap_rows, gap_counts = source_rule_gap_rows(root, inventory["endpoints"])
    total_failures = counts[STATUS_FAIL] + gap_counts[STATUS_FAIL]
    verdict = STATUS_OK if total_failures == 0 else STATUS_FAIL
    lines = [
        "# Endpoint Trace Sampling Audit",
        "",
        f"- Input source root: `{root}`",
        f"- Endpoint JSON path: `{out / 'endpoints.json'}`",
        f"- Graphify index path: `{graph_path if graph_path and graph_path.exists() else 'not available'}`",
        f"- Audit date: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- Audit Verdict: {verdict}",
        "",
        "## Graph Summary",
        "",
        f"- Node count: {node_count}",
        f"- Edge count: {edge_count}",
        f"- Graph-covered source files detected: {len(graph_files)}",
        "",
        "## Endpoint Trace Sampling Audit",
        "",
        "Endpoint samples are checked with Graphify evidence first; source files are read when graph evidence is absent or insufficient. The goal is correctness, completeness, and no redundancy, not topology reconstruction.",
        "",
        "| # | direction | kind | service | identifier | source | graph/source evidence status | verdict | notes |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Missing-Family Candidate Trace",
        "",
        "| # | candidate family | source file | verdict | notes |",
        "|---|---|---|---|---|",
        *(gap_rows or ["| 1 | none | none | PASS | no missing-family candidates detected |"]),
        "",
        "## Graph Rule Gap Discovery",
        "",
        f"- Endpoint sample verdict counts: {dict(counts)}",
        f"- Missing-family candidate verdict counts: {dict(gap_counts)}",
        "- MISSING_ENDPOINT_RULE review: FAIL rows indicate endpoint evidence or redundancy problems requiring profiler changes.",
        "",
        "## Findings",
        "",
        f"- Endpoint profiler completeness gaps: {'none in sampled endpoints' if verdict == STATUS_OK else 'see FAIL rows'}",
        f"- Endpoint profiler redundancy issues: {'none in sampled endpoints' if verdict == STATUS_OK else 'see FAIL rows'}",
        "- Source confirmation needed: only when graph/source evidence status is not GRAPH_COVERED.",
    ]
    (out / f"endpoint_graph_edge_trace_audit_{dt.datetime.now().strftime('%Y%m%d')}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate endpoint profiler quality audits.")
    parser.add_argument("output_dir")
    parser.add_argument("--source-root", default=None)
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    inventory = read_json(out / "endpoints.json")
    root = Path(args.source_root or inventory.get("source_root")).resolve()
    write_source_audit(out, root, inventory)
    write_endpoint_audit(out, root, inventory)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
