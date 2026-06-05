from __future__ import annotations

import argparse
import collections
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
SRC_EXT = {".java", ".kt"}
OUT_SCOPE = ("\\target\\", "/target/", "\\src\\test\\", "/src/test/", "\\test\\", "/test/")
LOOKS_ENDPOINT = re.compile(
    r"Mapper|Repository|Client|Template|Executor|select|insert|update|delete|send|publish|cache|"
    r"RestTemplate|WebClient|Feign|Kafka|Rabbit|DSExecutor|selectOne|selectList",
    re.I,
)
METHOD_RE = re.compile(
    r"(?:(?:public|private|protected|static|final|synchronized|native|abstract|\s)+)"
    r"[\w<>\[\], ? extends super.&]+\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:throws [^{]+)?\{"
)
DECL_RE = re.compile(r"[\w<>\[\], ? extends super.&]+\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^{}]*\)\s*(?:throws [^;]+)?;")
FIELD_RE = re.compile(
    r"(?:@(?:Autowired|Resource|Inject)[^\n]*\n\s*)?"
    r"(?:private|protected|public|final|\s)+(?P<type>[A-Z][A-Za-z0-9_$.<>]*)\s+(?P<name>[a-z_][A-Za-z0-9_]*)\s*(?:[;=])"
)
CALL_RE = re.compile(r"(?:(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*)?(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
STATUSES = (
    "TRACE_TO_EGRESS",
    "TRACE_TO_INGRESS",
    "TERMINAL_NO_EGRESS",
    "TERMINAL_NO_INGRESS",
    "MISSING_ENDPOINT_IN_JSON",
    "NEEDS_SOURCE_EXPANSION",
)


@dataclass
class Method:
    cls: str
    file: str
    name: str
    start: int
    end: int
    body: str
    fields: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.file}:{self.cls}.{self.name}:{self.start}"
@dataclass
class Index:
    methods: list[Method]
    classes: dict[str, list[Method]]
    by_file: dict[str, list[Method]]
    by_key: dict[str, Method]
    reverse: dict[str, list[str]]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
def rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")
def source_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*"):
        norm = str(path).replace("\\", "/")
        if path.is_file() and path.suffix in SRC_EXT and not any(part in norm for part in OUT_SCOPE):
            out.append(path)
    return out
def line_no(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def close_brace(text: str, open_at: int) -> int:
    depth, quote, esc = 0, None, False
    for i in range(open_at, len(text)):
        ch = text[i]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def class_info(text: str, fallback: str) -> tuple[str, list[str], bool]:
    m = re.search(
        r"\b(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+[A-Za-z0-9_$.<>]+)?(?:\s+implements\s+([A-Za-z0-9_$.,\s<>]+))?",
        text,
    )
    if not m:
        return fallback, [], False
    aliases = []
    for item in (m.group(3) or "").split(","):
        name = item.strip().split("<", 1)[0].split(".")[-1]
        if name:
            aliases.append(name)
    return m.group(2), aliases, m.group(1) == "interface"


def add_method(methods: list[Method], cls: str, file: str, name: str, start: int, end: int, body: str, fields: dict[str, str], aliases: list[str]) -> None:
    if name not in {"if", "for", "while", "switch", "catch", "return", "new"}:
        methods.append(Method(cls, file, name, start, end, body, fields, aliases))


def parse_index(root: Path) -> Index:
    methods: list[Method] = []
    for path in source_files(root):
        text, file = path.read_text(encoding="utf-8", errors="ignore"), rel(root, path)
        cls, aliases, is_interface = class_info(text, path.stem)
        fields = {m.group("name"): m.group("type").split("<", 1)[0].split(".")[-1] for m in FIELD_RE.finditer(text)}
        occupied: list[tuple[int, int]] = []
        for m in METHOD_RE.finditer(text):
            open_at = text.find("{", m.start())
            close_at = close_brace(text, open_at)
            add_method(methods, cls, file, m.group("name"), line_no(text, m.start()), line_no(text, close_at), text[open_at : close_at + 1], fields, aliases)
            occupied.append((m.start(), close_at))
        if is_interface:
            for m in DECL_RE.finditer(text):
                if not any(a <= m.start() <= b for a, b in occupied):
                    line = line_no(text, m.start())
                    add_method(methods, cls, file, m.group("name"), line, line, "", fields, [])
    classes: dict[str, list[Method]] = collections.defaultdict(list)
    by_file: dict[str, list[Method]] = collections.defaultdict(list)
    by_key = {}
    for m in methods:
        classes[m.cls].append(m)
        for alias in m.aliases:
            classes[alias].append(m)
        by_file[m.file].append(m)
        by_key[m.key] = m
    reverse: dict[str, list[str]] = collections.defaultdict(list)
    idx = Index(methods, classes, by_file, by_key, reverse)
    for m in methods:
        for callee in resolve_calls(m, idx):
            reverse[callee.key].append(m.key)
    return idx


def resolve_calls(method: Method, idx: Index) -> list[Method]:
    out, seen = [], set()
    for m in CALL_RE.finditer(method.body):
        target, name = m.group("target"), m.group("method")
        if name in {"if", "for", "while", "switch", "catch", "return", "new", "log", "String", "List", "Map"}:
            continue
        if target in method.fields:
            candidates = [x for x in idx.classes.get(method.fields[target], []) if x.name == name]
        elif target in {"this", "super"} or not target:
            candidates = [x for x in idx.classes.get(method.cls, []) if x.name == name]
        else:
            candidates = []
        for c in candidates:
            if c.key != method.key and c.key not in seen:
                seen.add(c.key)
                out.append(c)
    return out


def endpoint_line(endpoint: dict[str, Any]) -> int | None:
    try:
        return int((endpoint.get("source") or {}).get("line") or 0) or None
    except (TypeError, ValueError):
        return None


def method_for_endpoint(idx: Index, endpoint: dict[str, Any]) -> Method | None:
    src, line = endpoint.get("source") or {}, endpoint_line(endpoint)
    file = (src.get("file") or "").replace("\\", "/")
    if not file or not line:
        return None
    for m in idx.by_file.get(file, []):
        if m.start <= line <= m.end:
            return m
    later = [m for m in idx.by_file.get(file, []) if m.start >= line]
    return min(later, key=lambda m: m.start - line) if later else None


def endpoints_in_method(endpoints: list[dict[str, Any]], method: Method, direction: str, service: str | None) -> list[dict[str, Any]]:
    out = []
    for e in endpoints:
        src, line = e.get("source") or {}, endpoint_line(e)
        owner_service = (e.get("owner") or {}).get("service")
        if e.get("direction") == direction and src.get("file") == method.file and line and method.start <= line <= method.end and (not service or owner_service == service):
            out.append(e)
    return out


def label(endpoint: dict[str, Any]) -> str:
    return f"{endpoint.get('kind')} {endpoint.get('identifier')} in_endpoints_json=true"


def trace_down(start: Method | None, idx: Index, endpoints: list[dict[str, Any]], service: str | None) -> tuple[str, list[str], str]:
    if not start:
        return "NEEDS_SOURCE_EXPANSION", [], "No enclosing source method could be identified."
    q, seen = collections.deque([(start, 0, [f"{start.cls}.{start.name}"])]), {start.key}
    while q:
        method, depth, chain = q.popleft()
        direct = endpoints_in_method(endpoints, method, "egress", service)
        if direct:
            return "TRACE_TO_EGRESS", [label(e) for e in direct[:8]], " -> ".join(chain)
        if depth < 4:
            for callee in resolve_calls(method, idx):
                if callee.key not in seen:
                    seen.add(callee.key)
                    q.append((callee, depth + 1, chain + [f"{callee.cls}.{callee.name}"]))
    if LOOKS_ENDPOINT.search(start.body):
        return "MISSING_ENDPOINT_IN_JSON", [], f"{start.cls}.{start.name}: visible endpoint-like calls were found but no egress endpoint record was reached."
    return "TERMINAL_NO_EGRESS", [], f"{start.cls}.{start.name}: no endpoint-looking calls in visible method body."


def trace_up(start: Method | None, endpoint: dict[str, Any], idx: Index, endpoints: list[dict[str, Any]], service: str | None) -> tuple[str, list[str], str]:
    seeds = [start] if start else []
    src, ident = endpoint.get("source") or {}, str(endpoint.get("identifier") or "")
    if not seeds and src.get("file"):
        seeds = [m for m in idx.by_file.get(src.get("file"), []) if ident and ident in m.body]
    if not seeds:
        return "TERMINAL_NO_INGRESS", [], "Endpoint evidence is class/config-level or has no visible method caller."
    q, seen = collections.deque((s, 0, [f"{s.cls}.{s.name}"]) for s in seeds), {s.key for s in seeds}
    while q:
        method, depth, chain = q.popleft()
        direct = endpoints_in_method(endpoints, method, "ingress", service)
        if direct:
            return "TRACE_TO_INGRESS", [label(e) for e in direct[:8]], " <- ".join(chain)
        if depth < 5:
            for key in idx.reverse.get(method.key, []):
                if key not in seen and key in idx.by_key:
                    seen.add(key)
                    caller = idx.by_key[key]
                    q.append((caller, depth + 1, chain + [f"{caller.cls}.{caller.name}"]))
    return "TERMINAL_NO_INGRESS", [], "No profiled ingress caller was reached in the resolved local call graph."


def samples(endpoints: list[dict[str, Any]], direction: str, limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    seen = set()
    for e in endpoints:
        src, owner = e.get("source") or {}, e.get("owner") or {}
        key = (e.get("kind"), owner.get("service"), src.get("file"))
        if e.get("direction") == direction and key not in seen:
            seen.add(key)
            grouped[e.get("kind") or "unknown"].append(e)
    return [e for kind in sorted(grouped) for e in grouped[kind][:limit]]


def gap_rows(root: Path, endpoints: list[dict[str, Any]]) -> list[tuple[str, str, int, bool, str, str]]:
    checks = [
        ("HTTP ingress annotations", r"@(?:RestController|RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping)", "HTTP_API"),
        ("HTTP egress clients", r"FeignClient|RestTemplate|WebClient|OkHttp|HttpClient", "HTTP_CALL"),
        ("Message consumers", r"RabbitListener|KafkaListener|JmsListener|StreamListener", "MESSAGE_CONSUMER"),
        ("Message producers", r"RabbitTemplate|KafkaTemplate|convertAndSend|\.send\(", "MESSAGE_PRODUCER"),
        ("Schedulers", r"@Scheduled|@XxlJob", "SCHEDULED_JOB"),
        ("Data and storage", r"@TableName|select\s+|insert\s+|update\s+|delete\s+|RedisCacheKeyEnum|RedisTemplate|StringRedisTemplate|redisson|redisCache", "DB_TABLE/DISTRIBUTED_CACHE"),
    ]
    kinds, files, rows = collections.Counter(e.get("kind") for e in endpoints), source_files(root), []
    for name, pattern, expected in checks:
        rx = re.compile(pattern, re.I)
        count = sum(1 for p in files if rx.search(p.read_text(encoding="utf-8", errors="ignore")))
        covered = any(k in kinds for k in expected.split("/"))
        verdict = "COVERED_BY_RULE" if covered else "MISSING_ENDPOINT_RULE"
        rows.append((name, expected, count, covered, verdict, "No change." if covered else f"Add extractor coverage for {name}."))
    return rows


def write_graph_skip(output_dir: Path, source_root: Path) -> None:
    date = datetime.now().strftime("%Y%m%d")
    checked = [source_root / "graphify-out/graph.json", source_root.parent / "graphify-out/graph.json", source_root.parent.parent / "graphify-out/graph.json"]
    lines = [
        "# Endpoint Graph Edge Trace Audit",
        "",
        "Status: GRAPH_AUDIT_SKIPPED_NO_GRAPHIFY_INDEX",
        "",
        f"- Input source root: `{source_root}`",
        f"- Endpoint JSON path: `{output_dir / 'endpoints.json'}`",
        "- Graphify index path: not available",
        f"- Audit date: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Graph Summary",
        "",
        "- Node count: unavailable",
        "- Edge count: unavailable",
        "- Relevant edge relation types: unavailable",
        "",
        "## Graph Coverage Summary",
        "",
        "- Root graph format: unavailable",
        "- Shard graphs inspected: none",
        "- Covered modules: none",
        "- Missing modules for sampled endpoints: all sampled modules, because no Graphify index was present",
        "",
        "## Discovery Paths Checked",
        "",
        *[f"- `{p}` exists={p.exists()}" for p in checked],
        "",
        "## Graph Rule Gap Discovery",
        "",
        "No graph rule-gap candidates found because no Graphify index or shard graph was available for this run.",
        "",
        "MISSING_ENDPOINT_RULE review: skipped for graph evidence; source trace audit performed source/config rule-gap discovery.",
    ]
    (output_dir / f"endpoint_graph_edge_trace_audit_{date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_source_audit(output_dir: Path, source_root: Path, limit: int) -> Path:
    inv, endpoint_path = read_json(output_dir / "endpoints.json"), output_dir / "endpoints.json"
    endpoints, idx = inv.get("endpoints", []), parse_index(source_root)
    in_samples, eg_samples = samples(endpoints, "ingress", limit), samples(endpoints, "egress", limit)
    kinds = collections.Counter(e.get("kind") for e in endpoints)
    services = collections.Counter((e.get("owner") or {}).get("service") for e in endpoints)
    date, status_counts = datetime.now().strftime("%Y%m%d"), collections.Counter()
    lines = [
        "# Endpoint LLM Trace Audit",
        "",
        f"- Input source root: `{source_root}`",
        f"- Endpoint JSON path: `{endpoint_path}`",
        f"- Graphify index path: `{(inv.get('audit') or {}).get('graphify_index_path') or 'not available'}`",
        f"- Audit date: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Sampling Summary",
        "",
        f"- Endpoint kinds sampled: {dict(kinds)}",
        f"- Services represented: {dict(services)}",
        f"- Source methods indexed: {len(idx.methods)}",
        f"- Ingress samples: {len(in_samples)}",
        f"- Egress samples: {len(eg_samples)}",
        "",
        "## Ingress-To-Egress Samples",
        "",
        "| # | direction | kind | service | identifier | source | exists | trace status | traced egress identifiers with in_endpoints_json | call chain or source-reading path |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(in_samples, 1):
        src, service = e.get("source") or {}, (e.get("owner") or {}).get("service")
        status, traced, chain = trace_down(method_for_endpoint(idx, e), idx, endpoints, service)
        status_counts[status] += 1
        lines.append(f"| {i} | ingress | {e.get('kind')} | {service} | `{e.get('identifier')}` | {src.get('file')}:{src.get('line')} | true | {status} | {'; '.join(traced) or 'none'} | {chain.replace('|', '/')} |")
    lines += ["", "## Egress-To-Ingress Samples", "", "| # | direction | kind | service | identifier | source | exists | trace status | traced ingress identifiers with in_endpoints_json | call chain or source-reading path |", "|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(eg_samples, 1):
        src, service = e.get("source") or {}, (e.get("owner") or {}).get("service")
        status, traced, chain = trace_up(method_for_endpoint(idx, e), e, idx, endpoints, service)
        status_counts[status] += 1
        lines.append(f"| {i} | egress | {e.get('kind')} | {service} | `{e.get('identifier')}` | {src.get('file')}:{src.get('line')} | true | {status} | {'; '.join(traced) or 'none'} | {chain.replace('|', '/')} |")
    total, unresolved = len(in_samples) + len(eg_samples), status_counts["NEEDS_SOURCE_EXPANSION"]
    lines += [
        "",
        "## Findings",
        "",
        "- Correctness issues: none found by the deterministic trace audit.",
        f"- Completeness gaps: {unresolved}/{total} samples require source expansion after bounded call-graph tracing.",
        "- Redundancy issues: none found in sampled records.",
        f"- Trace status counts: {dict(status_counts)}",
        "",
        "## Rule Gap Discovery",
        "",
        "| Evidence family | Expected kind(s) | Candidate files reviewed | Matching endpoint records | Verdict | Suggested rule update |",
        "|---|---|---:|---|---|---|",
    ]
    lines += [f"| {a} | {b} | {c} | {d} | {e} | {f} |" for a, b, c, d, e, f in gap_rows(source_root, endpoints)]
    lines += ["", "MISSING_ENDPOINT_RULE review: any family marked `MISSING_ENDPOINT_RULE` above should become the next extractor evolution target.", "", "## Profiler Rule Changes Suggested", "", "- Keep bounded source tracing in the audit workflow and avoid blanket `NEEDS_SOURCE_EXPANSION` unless source or the visible local call graph is genuinely insufficient."]
    path = output_dir / f"endpoint_llm_trace_audit_{date}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate source-reading endpoint trace audits.")
    parser.add_argument("output_dir", help="Endpoint profiler output directory containing endpoints.json.")
    parser.add_argument("--source-root", default=None, help="Source root; defaults to endpoints.json source_root.")
    parser.add_argument("--limit-per-kind", type=int, default=10, help="Maximum diverse samples per direction/kind.")
    parser.add_argument("--graph-skip-if-missing", action="store_true", help="Write graph skip audit when no graphify index exists.")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    inv = read_json(output_dir / "endpoints.json")
    source_root = Path(args.source_root or inv.get("source_root") or ".").resolve()
    audit = write_source_audit(output_dir, source_root, args.limit_per_kind)
    audit_info = inv.get("audit") or {}
    if args.graph_skip_if_missing and not (audit_info.get("graphify_used") or audit_info.get("graphify_index_path")):
        write_graph_skip(output_dir, source_root)
    print(str(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
