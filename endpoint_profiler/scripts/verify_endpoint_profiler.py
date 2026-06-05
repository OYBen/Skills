#!/usr/bin/env python3
"""Deterministic verifier for endpoint_profiler outputs.

The checks are intentionally schema/property based. Expected values come from
visible output files and small public fixtures, not hidden oracle answers.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_KINDS = {
    "HTTP_API",
    "RPC_ROUTE",
    "WebSocket",
    "MESSAGE_CONSUMER",
    "EVENT_BUS_LISTENER",
    "SCHEDULED_JOB",
    "CLI",
    "HTTP_CALL",
    "RPC_CALL",
    "DB_TABLE",
    "DISTRIBUTED_CACHE",
    "MESSAGE_PRODUCER",
    "EVENT_BUS_PUBLISHER",
    "DATAMODEL",
    "DATA_API_CALL",
    "DATA_API_STREAM",
    "DATA_MODEL_SQL",
    "ANALYTICS_MODEL_QUERY",
    "DATA_MODEL_SCHEMA",
    "DATA_EVENT_SCHEMA",
    "DATA_EVENT_PUBLISHER",
    "SDK",
    "FILE",
}

BAD_IDENTIFIER_PATTERNS = [".*", ":*", "(?"]
VALID_FILE_CHANNELS = {"oss", "s3", "sftp", "ftp", "shared_directory", "partner_feed", "batch_exchange"}
DATAMODEL_FQN_RE = re.compile(
    r"^(?:data|event)"
    r"(?:\.[A-Za-z][A-Za-z0-9_]*|\.\{[A-Za-z_][A-Za-z0-9_]*\}|\.\$\{[A-Za-z_][A-Za-z0-9_]*\})+"
    r"\.[A-Za-z][A-Za-z0-9_]*(?:\$\{[A-Za-z_][A-Za-z0-9_]*\})?$"
)
GENERIC_OBJECT_STORAGE_PARTS = {
    "bucket",
    "bucketname",
    "bucket_name",
    "oss_bucket",
    "key",
    "objectkey",
    "object_key",
    "filename",
    "file_name",
    "dirname",
    "dir",
}


def is_test_source_path(source_file: Any) -> bool:
    normalized = str(source_file or "").replace("\\", "/").lower()
    name = Path(normalized).name
    return (
        "/src/test/" in normalized
        or "/test/" in normalized
        or name.endswith("test.java")
        or name.endswith("tests.java")
        or name.endswith("_test.py")
        or name.endswith(".spec.ts")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".test.js")
    )


def is_always_excluded_source_path(source_file: Any) -> bool:
    normalized = str(source_file or "").replace("\\", "/").lower()
    path_parts = [part for part in normalized.split("/") if part]
    parts = set(path_parts)
    if is_test_source_path(source_file):
        return True
    if "/src/main/java/org/flywaydb/" in f"/{normalized}" or "/db/migration/" in f"/{normalized}":
        return True
    if parts & {
        ".git",
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
    if path_parts and path_parts[0] in example_parts:
        return True
    if len(path_parts) > 1 and path_parts[1] in example_parts:
        return True
    name = Path(normalized).name
    if name in {"readme.md", "changelog.md"}:
        return True
    return False


def fail(failures: list[str], name: str, observed: Any, expected: str) -> None:
    failures.append(f"{name}: observed={observed!r}; expected={expected}")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def service_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return cleaned or "unknown-service"


def validate_endpoint_shape(data: dict[str, Any], failures: list[str], context: str) -> None:
    for key in ["schema_version", "source_root", "generated_at", "endpoints", "audit"]:
        if key not in data:
            fail(failures, f"{context}.top_level.{key}", None, "required key present")
    if data.get("schema_version") != "endpoint-profiler.v1":
        fail(failures, f"{context}.schema_version", data.get("schema_version"), "endpoint-profiler.v1")
    identity_seen: dict[str, int] = {}
    for index, endpoint in enumerate(data.get("endpoints", [])):
        prefix = f"{context}.endpoints[{index}]"
        for key in ["id", "direction", "kind", "identifier", "match_rule", "source", "metadata"]:
            if key not in endpoint:
                fail(failures, f"{prefix}.{key}", None, "required endpoint key present")
        if endpoint.get("direction") not in {"ingress", "egress"}:
            fail(failures, f"{prefix}.direction", endpoint.get("direction"), "ingress or egress")
        if endpoint.get("kind") not in ALLOWED_KINDS:
            fail(failures, f"{prefix}.kind", endpoint.get("kind"), "allowed endpoint kind")
        identifier = endpoint.get("identifier", "")
        if not identifier:
            fail(failures, f"{prefix}.identifier", identifier, "non-empty")
        for pattern in BAD_IDENTIFIER_PATTERNS:
            if pattern in identifier:
                fail(failures, f"{prefix}.identifier", identifier, f"must not contain {pattern}")
        confidence = (endpoint.get("metadata") or {}).get("confidence")
        if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
            fail(failures, f"{prefix}.metadata.confidence", confidence, "number between 0 and 1")
        evidence = (endpoint.get("metadata") or {}).get("evidence")
        if not evidence:
            fail(failures, f"{prefix}.metadata.evidence", evidence, "non-empty evidence")
        source_file = (endpoint.get("source") or {}).get("file")
        if not source_file or Path(str(source_file)).is_absolute():
            fail(failures, f"{prefix}.source.file", source_file, "relative source path")
        if is_always_excluded_source_path(source_file):
            fail(failures, f"{prefix}.source.file", source_file, "in-scope production, dependency, resource, or machine-readable contract source")
        if endpoint.get("kind") == "FILE":
            match_rule = endpoint.get("match_rule") or {}
            channel = match_rule.get("channel")
            integration = match_rule.get("integration")
            if integration is not True and channel not in VALID_FILE_CHANNELS:
                fail(failures, f"{prefix}.FILE.match_rule", match_rule, "integration true or valid file-exchange channel")
            evidence_text = " ".join((endpoint.get("metadata") or {}).get("evidence") or []).lower()
            source_text = str(source_file or "").lower()
            identifier_text = str(endpoint.get("identifier") or "").lower()
            if any(token in f"{evidence_text} {source_text} {identifier_text}" for token in ["template", "download", "response", "controller", "exportpo", "vo.java", "dto.java"]):
                fail(failures, f"{prefix}.FILE.semantic", endpoint.get("identifier"), "file-sharing integration endpoint, not export/download/template implementation file")
        if endpoint.get("kind") == "HTTP_API":
            parts = str(identifier).split(maxsplit=1)
            if len(parts) != 2 or not parts[1].startswith("/"):
                fail(failures, f"{prefix}.HTTP_API.identifier", identifier, "METHOD /full/path")
            if "?" in str(identifier):
                fail(failures, f"{prefix}.HTTP_API.identifier", identifier, "query parameters belong in match_rule.query_params")
            if parts and parts[0] == "ANY" and re.match(r"^ANY\s+[^/]", str(identifier)):
                fail(failures, f"{prefix}.HTTP_API.identifier", identifier, "method-level API, not class-level prefix")
        if endpoint.get("kind") == "DB_TABLE":
            match_rule = endpoint.get("match_rule") or {}
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.DB_TABLE.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "table":
                fail(failures, f"{prefix}.DB_TABLE.match_rule.type", match_rule.get("type"), "table")
            if str(endpoint.get("identifier") or "").upper() in {"TABLES", "PARTITIONS", "COLUMNS", "SCHEMATA", "TABLE_NAME"}:
                fail(failures, f"{prefix}.DB_TABLE.identifier", endpoint.get("identifier"), "business table identifier, not system metadata or unresolved constant")
            evidence_text = " ".join((endpoint.get("metadata") or {}).get("evidence") or [])
            if str(source_file or "").replace("\\", "/").lower().find("/resources/back/") >= 0:
                fail(failures, f"{prefix}.DB_TABLE.source.file", source_file, "active runtime mapper/resource, not resources/back archive")
            if evidence_text.lstrip().startswith("<!--"):
                fail(failures, f"{prefix}.DB_TABLE.evidence", evidence_text, "active SQL evidence, not XML comment")
            ident = str(endpoint.get("identifier") or "")
            if re.search(rf"\bUPDATE\s+{re.escape(ident)}\s*=", evidence_text, re.IGNORECASE):
                fail(failures, f"{prefix}.DB_TABLE.identifier", ident, "table identifier, not an UPDATE field assignment")
        if endpoint.get("kind") in {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"}:
            match_rule = endpoint.get("match_rule") or {}
            expected_direction = "ingress" if endpoint.get("kind") == "MESSAGE_CONSUMER" else "egress"
            if endpoint.get("direction") != expected_direction:
                fail(failures, f"{prefix}.{endpoint.get('kind')}.direction", endpoint.get("direction"), expected_direction)
            if match_rule.get("type") not in {"topic", "task_decorator"}:
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.type", match_rule.get("type"), "topic or task_decorator")
            if re.match(r"^[A-Z0-9_.]+$", str(endpoint.get("identifier") or "")):
                fail(failures, f"{prefix}.{endpoint.get('kind')}.identifier", endpoint.get("identifier"), "resolved topic/queue value, not Java constant name")
        if endpoint.get("kind") in {"EVENT_BUS_LISTENER", "EVENT_BUS_PUBLISHER"}:
            match_rule = endpoint.get("match_rule") or {}
            expected_direction = "ingress" if endpoint.get("kind") == "EVENT_BUS_LISTENER" else "egress"
            if endpoint.get("direction") != expected_direction:
                fail(failures, f"{prefix}.{endpoint.get('kind')}.direction", endpoint.get("direction"), expected_direction)
            if match_rule.get("type") != "event":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.type", match_rule.get("type"), "event")
            if endpoint.get("kind") == "EVENT_BUS_LISTENER" and str(endpoint.get("identifier") or "") == "spring-event-listener":
                fail(failures, f"{prefix}.EVENT_BUS_LISTENER.identifier", endpoint.get("identifier"), "event type from annotation/parameter, or owner method fallback")
        if endpoint.get("kind") == "DISTRIBUTED_CACHE":
            match_rule = endpoint.get("match_rule") or {}
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.DISTRIBUTED_CACHE.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "distributed_cache":
                fail(failures, f"{prefix}.DISTRIBUTED_CACHE.match_rule.type", match_rule.get("type"), "distributed_cache")
            if not match_rule.get("backend"):
                fail(failures, f"{prefix}.DISTRIBUTED_CACHE.match_rule.backend", match_rule.get("backend"), "distributed cache backend such as redis")
            if str(endpoint.get("identifier") or "").startswith("CacheNames."):
                fail(failures, f"{prefix}.DISTRIBUTED_CACHE.identifier", endpoint.get("identifier"), "resolved distributed cache key, not Java constant expression")
        if endpoint.get("kind") == "HTTP_CALL":
            match_rule = endpoint.get("match_rule") or {}
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.HTTP_CALL.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") not in {"url_template", "http_client"}:
                fail(failures, f"{prefix}.HTTP_CALL.match_rule.type", match_rule.get("type"), "url_template or http_client")
            if "?" in str(endpoint.get("identifier") or ""):
                fail(failures, f"{prefix}.HTTP_CALL.identifier", endpoint.get("identifier"), "query parameters belong in match_rule.query_params")
        if endpoint.get("kind") == "SCHEDULED_JOB":
            match_rule = endpoint.get("match_rule") or {}
            if endpoint.get("direction") != "ingress":
                fail(failures, f"{prefix}.SCHEDULED_JOB.direction", endpoint.get("direction"), "ingress")
            if match_rule.get("type") != "schedule":
                fail(failures, f"{prefix}.SCHEDULED_JOB.match_rule.type", match_rule.get("type"), "schedule")
        if endpoint.get("kind") == "DATAMODEL":
            match_rule = endpoint.get("match_rule") or {}
            evidence_text = " ".join((endpoint.get("metadata") or {}).get("evidence") or [])
            identifier_text = str(endpoint.get("identifier") or "")
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.DATAMODEL.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "datamodel":
                fail(failures, f"{prefix}.DATAMODEL.match_rule.type", match_rule.get("type"), "datamodel")
            if not DATAMODEL_FQN_RE.match(identifier_text):
                fail(failures, f"{prefix}.DATAMODEL.identifier", identifier_text, "semantic data FQN like data.prctvmkt.${memberProgramCode}.Guide")
            if match_rule.get("fqn") != identifier_text:
                fail(failures, f"{prefix}.DATAMODEL.match_rule.fqn", match_rule.get("fqn"), "same full FQN as identifier")
            if re.search(r"\b(class|interface)\s+\w+(Repository|Mapper|Dao)\b", evidence_text):
                fail(failures, f"{prefix}.DATAMODEL.evidence", evidence_text, "semantic model evidence, not repository/mapper/dao naming convention")
            if identifier_text.endswith(("Repository", "Mapper", "Dao")):
                fail(failures, f"{prefix}.DATAMODEL.identifier", endpoint.get("identifier"), "semantic model identifier, not implementation class")
        if endpoint.get("kind") in {"DATA_API_CALL", "DATA_API_STREAM"}:
            match_rule = endpoint.get("match_rule") or {}
            identifier_text = str(endpoint.get("identifier") or "")
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "dataapi_model":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.type", match_rule.get("type"), "dataapi_model")
            if not DATAMODEL_FQN_RE.match(identifier_text):
                fail(failures, f"{prefix}.{endpoint.get('kind')}.identifier", identifier_text, "datamodel FQN reached through DataAPI")
            if match_rule.get("fqn") != identifier_text:
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.fqn", match_rule.get("fqn"), "same full FQN as identifier")
            if not match_rule.get("operation"):
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.operation", match_rule.get("operation"), "DataAPI operation")
            if endpoint.get("kind") == "DATA_API_CALL" and match_rule.get("access_mode") not in {"dataapi-http", "dataapi-sdk", "dataapi-sql"}:
                fail(failures, f"{prefix}.DATA_API_CALL.match_rule.access_mode", match_rule.get("access_mode"), "dataapi-http, dataapi-sdk, or dataapi-sql")
            if endpoint.get("kind") == "DATA_API_STREAM" and match_rule.get("access_mode") not in {"dataapi-websocket", "dataapi-fetch", "dataapi-stream-sql"}:
                fail(failures, f"{prefix}.DATA_API_STREAM.match_rule.access_mode", match_rule.get("access_mode"), "dataapi-websocket, dataapi-fetch, or dataapi-stream-sql")
        if endpoint.get("kind") in {"DATA_MODEL_SQL", "ANALYTICS_MODEL_QUERY"}:
            match_rule = endpoint.get("match_rule") or {}
            identifier_text = str(endpoint.get("identifier") or "")
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "data_model_sql":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.type", match_rule.get("type"), "data_model_sql")
            if not DATAMODEL_FQN_RE.match(identifier_text) or identifier_text.startswith("event."):
                fail(failures, f"{prefix}.{endpoint.get('kind')}.identifier", identifier_text, "data.* model FQN reached through SQL/data proxy")
            if match_rule.get("fqn") != identifier_text:
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.fqn", match_rule.get("fqn"), "same full FQN as identifier")
        if endpoint.get("kind") == "DATA_MODEL_SCHEMA":
            match_rule = endpoint.get("match_rule") or {}
            identifier_text = str(endpoint.get("identifier") or "")
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.DATA_MODEL_SCHEMA.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "data_model_schema":
                fail(failures, f"{prefix}.DATA_MODEL_SCHEMA.match_rule.type", match_rule.get("type"), "data_model_schema")
            if not DATAMODEL_FQN_RE.match(identifier_text) or identifier_text.startswith("event."):
                fail(failures, f"{prefix}.DATA_MODEL_SCHEMA.identifier", identifier_text, "data.* model FQN")
        if endpoint.get("kind") in {"DATA_EVENT_SCHEMA", "DATA_EVENT_PUBLISHER"}:
            match_rule = endpoint.get("match_rule") or {}
            identifier_text = str(endpoint.get("identifier") or "")
            if endpoint.get("direction") != "egress":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.direction", endpoint.get("direction"), "egress")
            if match_rule.get("type") != "data_event":
                fail(failures, f"{prefix}.{endpoint.get('kind')}.match_rule.type", match_rule.get("type"), "data_event")
            if not identifier_text.startswith("event."):
                fail(failures, f"{prefix}.{endpoint.get('kind')}.identifier", identifier_text, "event.* FQN")
        if endpoint.get("kind") == "SDK":
            identifier_text = str(endpoint.get("identifier") or "")
            match_rule = endpoint.get("match_rule") or {}
            if re.fullmatch(r"[A-Z][A-Za-z0-9_]*(?:Client|SDK)", identifier_text):
                fail(failures, f"{prefix}.SDK.identifier", endpoint.get("identifier"), "client class alone is not an endpoint; include operation and target object")
            oss_match = re.match(r"^OSS\s+(putObject|getObject|deleteObject|copyObject)\s+(.+)/(.+)$", identifier_text)
            if oss_match:
                bucket = str(match_rule.get("bucket") or oss_match.group(2)).strip().strip("\"'").lower()
                object_key = str(match_rule.get("object_key") or oss_match.group(3)).strip().strip("\"'").lower()
                if bucket in GENERIC_OBJECT_STORAGE_PARTS or object_key in GENERIC_OBJECT_STORAGE_PARTS or "+" in bucket or "+" in object_key:
                    fail(failures, f"{prefix}.SDK.identifier", endpoint.get("identifier"), "resolved object-storage target, not bucket/key parameters or concatenation templates")
            elif not re.match(r"^[A-Z][A-Za-z0-9_]*(?:Client|SDK)\.[A-Za-z_][A-Za-z0-9_]*\s+\S+", identifier_text):
                fail(failures, f"{prefix}.SDK.identifier", endpoint.get("identifier"), "external SDK operation with target object, not internal service type")
        owner = endpoint.get("owner") or {}
        identity = f"{owner.get('service')}|{endpoint.get('direction')}|{endpoint.get('kind')}|{endpoint.get('identifier')}"
        if identity in identity_seen:
            fail(failures, f"{prefix}.duplicate_identity", identity, f"unique endpoint identity; first seen at endpoints[{identity_seen[identity]}]")
        else:
            identity_seen[identity] = index


def verify_service_splits(output_dir: Path, data: dict[str, Any], failures: list[str]) -> None:
    services = data.get("services") or []
    endpoints = data.get("endpoints") or []
    if not services:
        return
    services_dir = output_dir / "services"
    manifest_path = services_dir / "manifest.json"
    if not services_dir.exists():
        fail(failures, "services_dir", str(services_dir), "directory exists")
        return
    if not manifest_path.exists():
        fail(failures, "services_manifest", str(manifest_path), "manifest.json exists")
        return
    manifest = load_json(manifest_path)
    manifest_by_service = {item.get("service"): item for item in manifest}
    expected_services = {service.get("name") for service in services if service.get("name")}
    if set(manifest_by_service) != expected_services:
        fail(failures, "services_manifest.services", sorted(manifest_by_service), f"matches services list {sorted(expected_services)}")

    endpoints_by_service: dict[str, list[dict[str, Any]]] = {}
    for endpoint in endpoints:
        service = (endpoint.get("owner") or {}).get("service")
        if service:
            endpoints_by_service.setdefault(service, []).append(endpoint)

    for service in services:
        name = service.get("name")
        if not name:
            fail(failures, "service.name", service, "non-empty service name")
            continue
        for key in ["root", "dependencies", "scope_roots"]:
            if key not in service:
                fail(failures, f"service.{name}.{key}", None, "required service field present")
        if not service.get("runtime_evidence"):
            fail(failures, f"service.{name}.runtime_evidence", service.get("runtime_evidence"), "runtime boundary evidence present")
        if not service.get("scope_roots"):
            fail(failures, f"service.{name}.scope_roots", service.get("scope_roots"), "at least one scope root")
        split_path = services_dir / service_filename(name) / "endpoints.json"
        split_html_path = services_dir / service_filename(name) / "endpoints_result.html"
        if not split_path.exists():
            fail(failures, f"service_split.{name}", str(split_path), "split endpoints.json exists")
            continue
        if not split_html_path.exists() or split_html_path.stat().st_size == 0:
            fail(failures, f"service_split.{name}.html", str(split_html_path), "split endpoints_result.html exists and is non-empty")
        split = load_json(split_path)
        validate_endpoint_shape(split, failures, f"split:{name}")
        split_eps = split.get("endpoints", [])
        expected_count = len(endpoints_by_service.get(name, []))
        if len(split_eps) != expected_count:
            fail(failures, f"service_split.{name}.endpoint_count", len(split_eps), f"{expected_count}")
        if manifest_by_service.get(name, {}).get("endpoints") != expected_count:
            fail(failures, f"service_manifest.{name}.endpoint_count", manifest_by_service.get(name, {}).get("endpoints"), f"{expected_count}")
        for endpoint in split_eps:
            owner = endpoint.get("owner") or {}
            if owner.get("service") != name:
                fail(failures, f"service_split.{name}.owner.service", owner.get("service"), name)
            if owner.get("service_scope") not in {"runtime", "dependency"}:
                fail(failures, f"service_split.{name}.owner.service_scope", owner.get("service_scope"), "runtime or dependency")

    dependency_eps = [
        endpoint
        for endpoint in endpoints
        if (endpoint.get("owner") or {}).get("service_scope") == "dependency"
    ]
    multi_scope_services = [service for service in services if len(service.get("scope_roots", [])) > 1]
    if multi_scope_services and not dependency_eps:
        fail(failures, "dependency_scope_endpoints", 0, "at least one endpoint attributed from dependency scope")


def endpoint_matches(data: dict[str, Any], direction: str, kind: str, identifier: str) -> list[dict[str, Any]]:
    return [
        endpoint
        for endpoint in data.get("endpoints", [])
        if endpoint.get("direction") == direction
        and endpoint.get("kind") == kind
        and endpoint.get("identifier") == identifier
    ]


def source_file_exists(data: dict[str, Any], relative_path: str) -> bool:
    root = Path(str(data.get("source_root") or ""))
    return (root / relative_path).exists()


def verify_datamodel_contract(
    data: dict[str, Any],
    failures: list[str],
    identifier: str,
    source_file: str | None = None,
) -> None:
    matches = endpoint_matches(data, "egress", "DATAMODEL", identifier)
    if not matches:
        matches = endpoint_matches(data, "egress", "DATA_MODEL_SCHEMA", identifier)
    if not matches:
        fail(failures, f"regression.DATAMODEL.{identifier}", 0, "present with full semantic FQN as DATAMODEL or DATA_MODEL_SCHEMA")
        return
    for endpoint in matches:
        match_rule = endpoint.get("match_rule") or {}
        if endpoint.get("kind") == "DATAMODEL" and match_rule.get("type") != "datamodel":
            fail(failures, f"regression.DATAMODEL.{identifier}.match_rule.type", match_rule.get("type"), "datamodel")
        if endpoint.get("kind") == "DATA_MODEL_SCHEMA" and match_rule.get("type") != "data_model_schema":
            fail(failures, f"regression.DATA_MODEL_SCHEMA.{identifier}.match_rule.type", match_rule.get("type"), "data_model_schema")
        if match_rule.get("fqn") != identifier:
            fail(failures, f"regression.DATAMODEL.{identifier}.match_rule.fqn", match_rule.get("fqn"), identifier)
        evidence = " ".join((endpoint.get("metadata") or {}).get("evidence") or [])
        if identifier not in evidence or not any(prefix in evidence for prefix in ["model.fqn", "fqn", "mainModelFqn", "refModelFqn", "ModelNameEnum"]):
            fail(failures, f"regression.DATAMODEL.{identifier}.evidence", evidence, f"FQN evidence containing {identifier}")
        if source_file and (endpoint.get("source") or {}).get("file") != source_file:
            fail(failures, f"regression.DATAMODEL.{identifier}.source.file", (endpoint.get("source") or {}).get("file"), source_file)


def verify_regression_expectations(data: dict[str, Any], failures: list[str]) -> None:
    root = Path(str(data.get("source_root") or ""))
    preflight = (data.get("audit") or {}).get("preflight") or {}
    capability_hints = preflight.get("capability_hints") or []
    for hint in capability_hints:
        if hint.get("potential_endpoint_kinds") and not hint.get("scan_plan"):
            fail(failures, f"regression.capability_scan_plan.{hint.get('capability')}", "missing", "capability hints include targeted scan plans")
        if hint.get("status") == "confirmed_by_source" and not hint.get("confirmed_endpoint_samples"):
            fail(failures, f"regression.capability_confirmed_samples.{hint.get('capability')}", "missing", "confirmed capability hints include endpoint samples")
    hints_by_name = {hint.get("capability"): hint for hint in capability_hints}
    endpoint_kinds = {endpoint.get("kind") for endpoint in data.get("endpoints", [])}
    if {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"} & endpoint_kinds and "Spring Cloud Stream" in hints_by_name:
        confirmed = set((hints_by_name["Spring Cloud Stream"].get("confirmed_kinds") or {}).keys())
        if not (confirmed & {"MESSAGE_CONSUMER", "MESSAGE_PRODUCER"}):
            fail(failures, "regression.capability.Spring_Cloud_Stream.confirmed", confirmed, "Spring Cloud Stream binding capability confirms message endpoints after targeted scan")
    if {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"} & endpoint_kinds and "Shuyun EventService" in hints_by_name:
        confirmed = set((hints_by_name["Shuyun EventService"].get("confirmed_kinds") or {}).keys())
        if not (confirmed & {"EVENT_BUS_PUBLISHER", "EVENT_BUS_LISTENER"}):
            fail(failures, "regression.capability.Shuyun_EventService.confirmed", confirmed, "Shuyun EventService capability confirms event bus endpoints")
    if {"DATA_API_CALL", "DATA_API_STREAM", "ANALYTICS_MODEL_QUERY"} & endpoint_kinds and "Shuyun DataAPI" in hints_by_name:
        confirmed = set((hints_by_name["Shuyun DataAPI"].get("confirmed_kinds") or {}).keys())
        if not (confirmed & {"DATA_API_CALL", "DATA_API_STREAM", "ANALYTICS_MODEL_QUERY"}):
            fail(failures, "regression.capability.Shuyun_DataAPI.confirmed", confirmed, "Shuyun DataAPI capability confirms data model access endpoints")
    if root.exists():
        has_spectrum_feign = False
        has_tasklog_fqn = False
        for source in root.rglob("*.java"):
            source_text = source.read_text(encoding="utf-8", errors="ignore")
            if "SpectrumFeignClient" in source_text:
                has_spectrum_feign = True
            if 'TaskLog' in source.name and 'FQN' in source_text and 'data.mc.action.TaskLog' in source_text:
                has_tasklog_fqn = True
            if has_spectrum_feign and has_tasklog_fqn:
                break
        if has_spectrum_feign and not any(endpoint.get("kind") == "HTTP_CALL" for endpoint in data.get("endpoints", [])):
            fail(failures, "regression.HTTP_CALL.spectrum_feign", 0, "present when @SpectrumFeignClient contracts exist")
        if has_tasklog_fqn and not endpoint_matches(data, "egress", "DATAMODEL", "data.mc.action.TaskLog"):
            fail(failures, "regression.DATAMODEL.java_fqn_constant.data.mc.action.TaskLog", 0, "present from TaskLog.FQN constant usage")

    datamodel_modes_fixture = "src/main/java/com/example/CdpModelAccess.java"
    if source_file_exists(data, datamodel_modes_fixture):
        expected_modes = [
            ("egress", "DATA_API_CALL", "data.mdm.CohortMeta"),
            ("egress", "ANALYTICS_MODEL_QUERY", "data.cdp.calc.SegmentTaskTarget"),
            ("egress", "DATA_API_CALL", "data.mdm.TagCategory"),
            ("egress", "EVENT_BUS_PUBLISHER", "event.cdp.ImportExportNotify"),
        ]
        for direction, kind, identifier in expected_modes:
            if not endpoint_matches(data, direction, kind, identifier):
                fail(failures, f"regression.{kind}.{identifier}", 0, "present in datamodel_modes fixture")
        if endpoint_matches(data, "egress", "DATA_MODEL_SQL", "data.mdm.CohortMeta"):
            fail(failures, "regression.DATA_MODEL_SQL.deprecated", "present", "absent; SQL should be evidence on DATA_API_CALL/DATA_API_STREAM")
        if any(endpoint.get("kind") in {"DATA_MODEL_SCHEMA", "DATA_EVENT_SCHEMA"} for endpoint in data.get("endpoints", [])):
            fail(failures, "regression.schema_endpoints.deprecated", "present", "absent; schema/init evidence is not a business endpoint")
        if endpoint_matches(data, "egress", "DATAMODEL", "data.redis.ssl.enabled"):
            fail(failures, "regression.DATAMODEL.data.redis.ssl.enabled", "present", "absent; config key is not a datamodel")

    job_event_scheduler = "calc-service-develop/calc-service-develop/calc-scheduler/src/main/java/com/shuyun/calc/service/scheduler/job/JobEventScheduler.java"
    if source_file_exists(data, job_event_scheduler):
        if not endpoint_matches(data, "egress", "MESSAGE_PRODUCER", "calc.service.scheduler.jobEvent.topic.{tenantId}.{client}"):
            fail(failures, "regression.MESSAGE_PRODUCER.jobEvent.kafka", 0, "present from ProducerRecord dynamic topic template")
    calc_job_task = "cdp-develop/cdp-develop/cdp-scheduler/src/main/java/com/shuyun/cdp/calc/task/CalcJobTask.java"
    if source_file_exists(data, calc_job_task):
        if not endpoint_matches(data, "ingress", "MESSAGE_CONSUMER", "calc.service.scheduler.jobEvent.topic.{tenantId}.{group}"):
            fail(failures, "regression.MESSAGE_CONSUMER.jobEvent.kafka", 0, "present from Kafka subscribe dynamic topic template")

    model_enum_file = "siyu-common/src/main/java/com/shuyun/siyu/common/enums/model/ModelNameEnum.java"
    if source_file_exists(data, model_enum_file):
        for identifier in [
            "data.prctvmkt.${memberProgramCode}.Order",
            "data.prctvmkt.${memberProgramCode}.OrderItem",
            "data.prctvmkt.${memberProgramCode}.RefundOrderItem",
            "data.prctvmkt.${memberProgramCode}.Product",
        ]:
            verify_datamodel_contract(data, failures, identifier)
        for old_identifier in ["ORDER", "ORDER_ITEM", "REFUND_ORDER_ITEM", "PRODUCT"]:
            matches = endpoint_matches(data, "egress", "DATAMODEL", old_identifier)
            if matches:
                fail(failures, f"regression.DATAMODEL.bare_model_name.{old_identifier}", len(matches), "absent; identifier must be the model FQN")

    material_tree_controller = "siyu-server/siyu-server-material/src/main/java/com/shuyun/siyu/web/material/app/AppMaterialCategoryController.java"
    if source_file_exists(data, material_tree_controller):
        for identifier in ["GET /material-app/material/category/tree", "GET /guide-app/material/category/tree"]:
            if not endpoint_matches(data, "ingress", "HTTP_API", identifier):
                fail(failures, f"regression.HTTP_API.{identifier}", 0, "present from multi-prefix @RequestMapping expansion")
        bad = [
            endpoint
            for endpoint in endpoint_matches(data, "ingress", "HTTP_API", "GET /tree")
            if ((endpoint.get("source") or {}).get("file") == material_tree_controller)
        ]
        if bad:
            fail(failures, "regression.HTTP_API.GET /tree", len(bad), "absent for AppMaterialCategoryController; class-level prefix must be included")

    wx_cp_message_client = "siyu-sdk/sdk-weixin/siyu-weixin-cp-sdk/src/main/java/com/shuyun/siyu/sdk/wx/cp/client/impl/WxCpMessageClientImpl.java"
    if source_file_exists(data, wx_cp_message_client):
        if not endpoint_matches(data, "egress", "HTTP_CALL", "POST /cgi-bin/message/send"):
            fail(failures, "regression.HTTP_CALL.POST /cgi-bin/message/send", 0, "present from WxCpMessageClient.send")

    cdp_data_service_files = [
        "src/main/java/com/example/CdpDataService.java",
        "siyu-sdk/sdk-shuyun/siyu-kylin-cdp-sdk/src/main/java/com/shuyun/siyu/sdk/cdp/service/CdpDataService.java",
    ]
    if any(source_file_exists(data, source_file) for source_file in cdp_data_service_files):
        if not endpoint_matches(data, "egress", "HTTP_CALL", "POST /data/query/occIds"):
            fail(failures, "regression.HTTP_CALL.POST /data/query/occIds", 0, "present from getApiUrl(MEMBER_POST_QUERY_OCC_ID) + responseContentByPost(url, ...)")

    smart_guide_system_files = [
        "src/main/java/com/example/SmartGuideSystemServer.java",
        "siyu-sdk/sdk-shuyun/siyu-openapi-sdk/siyu-integration-openapi-sdk/src/main/java/com/shuyun/siyu/integration/openapi/server/SmartGuideSystemServer.java",
    ]
    if any(source_file_exists(data, source_file) for source_file in smart_guide_system_files):
        if not endpoint_matches(data, "egress", "HTTP_CALL", "POST {smartGuideConfService.iconUrl[iconCode]}"):
            fail(failures, "regression.HTTP_CALL.POST {smartGuideConfService.iconUrl[iconCode]}", 0, "present as unresolved config-map HTTP contract")

    if source_file_exists(data, "src/main/java/com/example/ConfigBaseUrlClient.java"):
        for identifier, reason in [
            ("POST {kyLinApiConfig.mbspApiUrl}/member/register/wechat", "present from getMbspApiUrl(PATH_CONST) + responseContentByPost(url, ...)"),
            ("GET {kyLinApiConfig.customerUrl}/data/report/guide", "present from getCustomerUrl(PATH_CONST) + responseContentByGet(url)"),
        ]:
            if not endpoint_matches(data, "egress", "HTTP_CALL", identifier):
                fail(failures, f"regression.HTTP_CALL.config_base_url_path.{identifier}", 0, reason)
    if source_file_exists(data, "siyu-sdk/sdk-shuyun/siyu-openapi-sdk/siyu-kylin-openapi-sdk/src/main/java/com/shuyun/siyu/sdk/kylin/service/KyLinMemberService.java"):
        for identifier, reason in [
            ("POST {kyLinApiConfig.mbspApiUrl}/member/register", "present from getMbspApiUrl(KyLinMbspApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT) + responseContentByPost(url, ...)"),
            ("POST {kyLinApiConfig.customerUrl}/wechat/member/register", "present from getCustomerUrl(KyLinApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT_CUSTOMER) + responseContentByPost(url, ...)"),
        ]:
            if not endpoint_matches(data, "egress", "HTTP_CALL", identifier):
                fail(failures, f"regression.HTTP_CALL.config_base_url_path.{identifier}", 0, reason)
    if source_file_exists(data, "siyu-sdk/sdk-shuyun/siyu-openapi-sdk/siyu-kylin-openapi-sdk/src/main/java/com/shuyun/siyu/sdk/kylin/service/KyLinDataReportService.java"):
        identifier = "POST {kyLinApiConfig.customerUrl}/guide/guide/dataQuotaByCode"
        if not endpoint_matches(data, "egress", "HTTP_CALL", identifier):
            fail(failures, f"regression.HTTP_CALL.config_base_url_path.{identifier}", 0, "present from getCustomerUrl(KyLinApiPathConsts.DataReport.GUIDE_DAT_REPORT) + responseContentByPost(url, ...)")

    if source_file_exists(data, "siyu-server/siyu-web-server/src/main/java/com/shuyun/siyu/web/migration/script/OfficialInitJavaMigrate.java"):
        for identifier in ["p_table_name", "CURRENT_TIMESTAMP", "#query_model#"]:
            matches = endpoint_matches(data, "egress", "DB_TABLE", identifier)
            if matches:
                fail(failures, f"regression.DB_TABLE.{identifier}", len(matches), "absent; SQL placeholder/function is not a table endpoint")

    if source_file_exists(data, "siyu-common/src/main/java/org/apache/ibatis/executor/BaseExecutor.java"):
        bad_oss = [
            endpoint
            for endpoint in data.get("endpoints", [])
            if endpoint.get("kind") == "SDK"
            and str(endpoint.get("identifier") or "").startswith("OSS putObject key/")
        ]
        if bad_oss:
            fail(failures, "regression.SDK.localCache.putObject", len(bad_oss), "absent; MyBatis localCache.putObject is not OSS")

    for identifier in ["{system.api.address}", "{system.api.address}/openapi-server/v1", "{system.boss.api.address}"]:
        matches = endpoint_matches(data, "egress", "HTTP_CALL", identifier)
        if matches:
            fail(failures, f"regression.HTTP_CALL.base_url.{identifier}", len(matches), "absent; base URL is metadata, not an endpoint")

    for identifier in [
        "AdminBizClient",
        "ExecutorBizClient",
        "WeiXinMpClient",
        "OSS deleteObject OSS_BUCKET/dir+fileName",
        "OSS getObject bucketName/dir+fileName",
        "OSS putObject OSS_BUCKET/dir+fileName",
        "OSS putObject bucket/key",
    ]:
        matches = endpoint_matches(data, "egress", "SDK", identifier)
        if matches:
            fail(failures, f"regression.SDK.coarse_identifier.{identifier}", len(matches), "absent; SDK endpoint identifier must include concrete operation target")

    if source_file_exists(data, "loyalty-analysis/src/main/kotlin/com/shuyun/loyalty/analysis/RemindScheduler.kt"):
        if not endpoint_matches(data, "ingress", "SCHEDULED_JOB", "RemindJob.executeInternal"):
            fail(failures, "regression.KOTLIN_SCHEDULED.enclosing_type", 0, "RemindJob.executeInternal present from @Scheduled inside second Kotlin class in file")
        if endpoint_matches(data, "ingress", "SCHEDULED_JOB", "RemindRedisConfig.executeInternal"):
            fail(failures, "regression.KOTLIN_SCHEDULED.wrong_enclosing_type", "RemindRedisConfig.executeInternal", "absent; use nearest enclosing Kotlin class")
        if not endpoint_matches(data, "ingress", "EVENT_BUS_LISTENER", "ApplicationReadyEvent"):
            fail(failures, "regression.KOTLIN_EVENT_LISTENER.ApplicationReadyEvent", 0, "present from @EventListener(ApplicationReadyEvent::class)")


def latest_matching_file(output_dir: Path, patterns: list[str]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(output_dir.glob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def require_audit_markers(path: Path, markers: list[str], failures: list[str], context: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lowered = text.lower()
    for marker in markers:
        if marker.lower() not in lowered:
            fail(failures, f"{context}.content.{marker}", str(path), f"audit report includes `{marker}` section/check")


def verify_audit_verdict(path: Path, failures: list[str], context: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    verdict = re.search(r"Audit Verdict:\s*(PASS|FAIL)", text, re.IGNORECASE)
    if not verdict:
        fail(failures, f"{context}.verdict", str(path), "audit report states `Audit Verdict: PASS` or `Audit Verdict: FAIL`")
    elif verdict.group(1).upper() != "PASS":
        fail(failures, f"{context}.verdict", verdict.group(1).upper(), "PASS; audit quality gate failed")


def verify_legacy_source_trace_quality(path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "Source Sampling Audit" in text:
        return
    if "Chain Completeness Audit" in text:
        statuses = re.findall(
            r"\b(TRACE_TO_EGRESS|TRACE_TO_INGRESS|SEMANTIC_SERVICE_FLOW|INTERNAL_CAPABILITY|NEEDS_SOURCE_EXPANSION)\b",
            text,
        )
        if not statuses:
            fail(failures, "required_audit.source_trace.chain_statuses", str(path), "chain audit rows include documented trace statuses")
            return
        counts = Counter(statuses)
        useful = counts["TRACE_TO_EGRESS"] + counts["TRACE_TO_INGRESS"] + counts["SEMANTIC_SERVICE_FLOW"] + counts["INTERNAL_CAPABILITY"]
        if useful == 0:
            fail(failures, "required_audit.source_trace.chain_useful_statuses", dict(counts), "at least one traced, semantic-flow, or internal-capability status")
        if counts["NEEDS_SOURCE_EXPANSION"]:
            fail(failures, "required_audit.source_trace.chain_unresolved", dict(counts), "no sampled endpoint should remain unresolved in a PASS chain audit")
        return
    sample_text = "\n".join(line for line in text.splitlines() if "| true |" in line)
    statuses = re.findall(
        r"\b(TRACE_TO_EGRESS|TRACE_TO_INGRESS|TERMINAL_NO_EGRESS|TERMINAL_NO_INGRESS|"
        r"MISSING_ENDPOINT_IN_JSON|REDUNDANT_ENDPOINT_IN_JSON|NEEDS_SOURCE_EXPANSION)\b",
        sample_text,
    )
    if not statuses:
        fail(failures, "required_audit.source_trace.statuses", str(path), "trace rows include documented source trace statuses")
        return
    counts = Counter(statuses)
    actionable = counts["TRACE_TO_EGRESS"] + counts["TRACE_TO_INGRESS"] + counts["TERMINAL_NO_EGRESS"] + counts["TERMINAL_NO_INGRESS"]
    unresolved = counts["NEEDS_SOURCE_EXPANSION"]
    if actionable == 0:
        fail(failures, "required_audit.source_trace.actionable_statuses", dict(counts), "at least one traced or terminal source status")
    if len(statuses) >= 10 and unresolved / len(statuses) > 0.30:
        fail(
            failures,
            "required_audit.source_trace.unresolved_ratio",
            f"{unresolved}/{len(statuses)}",
            "NEEDS_SOURCE_EXPANSION ratio <= 30%; deepen source tracing instead of blanket unresolved rows",
        )


def verify_audit_reports(output_dir: Path, data: dict[str, Any], aggregate_path: Path, failures: list[str]) -> None:
    endpoint_mtime = aggregate_path.stat().st_mtime
    source_audit = latest_matching_file(output_dir, ["endpoint_llm_trace_audit_*.md", "endpoint_source_trace_audit_*.md"])
    if not source_audit:
        fail(failures, "required_audit.source_trace", None, "fresh endpoint_llm_trace_audit_<YYYYMMDD>.md or endpoint_source_trace_audit_<YYYYMMDD>.md")
    elif source_audit.stat().st_size == 0:
        fail(failures, "required_audit.source_trace.size", str(source_audit), "non-empty source trace audit report")
    elif source_audit.stat().st_mtime < endpoint_mtime:
        fail(failures, "required_audit.source_trace.freshness", str(source_audit), "audit report generated after current endpoints.json")
    else:
        require_audit_markers(
            source_audit,
            ["Chain Completeness Audit", "Capability-Driven Audit", "Rule Gap Discovery", "Audit Verdict"],
            failures,
            "required_audit.source_trace",
        )
        verify_audit_verdict(source_audit, failures, "required_audit.source_trace")
        verify_legacy_source_trace_quality(source_audit, failures)

    audit = data.get("audit") or {}
    graphify_required = bool(audit.get("graphify_used") or audit.get("graphify_index_path"))
    graph_audit = latest_matching_file(output_dir, ["endpoint_graph_edge_trace_audit_*.md", "endpoint_graph_trace_audit_*.md"])
    if graphify_required:
        if not graph_audit:
            fail(failures, "required_audit.graph_edge", None, "fresh endpoint_graph_edge_trace_audit_<YYYYMMDD>.md")
        elif graph_audit.stat().st_size == 0:
            fail(failures, "required_audit.graph_edge.size", str(graph_audit), "non-empty graph edge audit report")
        elif graph_audit.stat().st_mtime < endpoint_mtime:
            fail(failures, "required_audit.graph_edge.freshness", str(graph_audit), "audit report generated after current endpoints.json")
        else:
            require_audit_markers(
                graph_audit,
                ["Endpoint Trace Sampling Audit", "Graph Rule Gap Discovery", "Audit Verdict"],
                failures,
                "required_audit.graph_edge",
            )
            verify_audit_verdict(graph_audit, failures, "required_audit.graph_edge")
    elif graph_audit and "GRAPH_AUDIT_SKIPPED_NO_GRAPHIFY_INDEX" not in graph_audit.read_text(encoding="utf-8", errors="ignore"):
        fail(failures, "required_audit.graph_edge.skip_status", str(graph_audit), "skip report explains no graphify index")


def verify_output(output_dir: Path) -> list[str]:
    failures: list[str] = []
    aggregate_path = output_dir / "endpoints.json"
    aggregate_html_path = output_dir / "endpoints_result.html"
    if not aggregate_path.exists():
        return [f"aggregate_missing: observed={aggregate_path}; expected=endpoints.json exists"]
    if not aggregate_html_path.exists() or aggregate_html_path.stat().st_size == 0:
        fail(failures, "aggregate_html", str(aggregate_html_path), "endpoints_result.html exists and is non-empty")
    elif "<th>Kind</th>" not in aggregate_html_path.read_text(encoding="utf-8", errors="ignore"):
        fail(failures, "aggregate_html.lowest_confidence_kind_column", str(aggregate_html_path), "HTML tables include a Kind column")
    data = load_json(aggregate_path)
    validate_endpoint_shape(data, failures, "aggregate")
    verify_service_splits(output_dir, data, failures)
    verify_regression_expectations(data, failures)
    verify_audit_reports(output_dir, data, aggregate_path, failures)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify endpoint_profiler output directory.")
    parser.add_argument("output_dir", help="Directory containing endpoints.json.")
    args = parser.parse_args()
    failures = verify_output(Path(args.output_dir))
    print("Endpoint profiler verifier")
    print(f"Input: {args.output_dir}")
    if failures:
        print("Result: FAIL")
        print("Failures:")
        for item in failures[:200]:
            print(f"- {item}")
        if len(failures) > 200:
            print(f"- ... {len(failures) - 200} more")
        return 1
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
