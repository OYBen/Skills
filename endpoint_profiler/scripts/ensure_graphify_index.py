from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def graph_paths(root: Path) -> list[Path]:
    return [
        root / "graphify-out" / "graph.json",
        root / "graph.json",
        root.parent / f"{root.name}-graphify-out" / "graphify-out" / "graph.json",
        root.parent / f"{root.name}-graphify-out" / "graph.json",
    ]


def find_graph(root: Path) -> Path | None:
    candidates = graph_paths(root)
    for parent in {root.parent, root.parent.parent}:
        candidates.extend(parent.glob("*graphify*out*/graphify-out/graph.json"))
        candidates.extend(parent.glob("*graphify*out*/graph.json"))
    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def graph_has_content(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    nodes = data.get("nodes") or data.get("vertices") or []
    edges = data.get("edges") or data.get("links") or []
    return bool(nodes or edges)


def run_graphify(root: Path, mode: str) -> None:
    exe = shutil.which("graphify")
    if exe:
        cmd = [exe, str(root), "--no-viz"]
        if mode:
            cmd += ["--mode", mode]
    else:
        cmd = [sys.executable, "-m", "graphify", str(root), "--no-viz"]
        if mode:
            cmd += ["--mode", mode]
    subprocess.run(cmd, cwd=str(root), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure a usable graphify-out/graph.json exists before endpoint profiling.")
    parser.add_argument("input_dir", help="Source root to graphify.")
    parser.add_argument("--mode", default="", choices=["", "deep"], help="Optional graphify extraction mode.")
    parser.add_argument("--no-generate", action="store_true", help="Only locate an existing graph; do not run graphify.")
    args = parser.parse_args()
    root = Path(args.input_dir).resolve()
    graph = find_graph(root)
    if graph and graph_has_content(graph):
        print(str(graph))
        return 0
    if args.no_generate:
        print("")
        return 2
    run_graphify(root, args.mode)
    graph = find_graph(root)
    if not graph or not graph_has_content(graph):
        raise SystemExit("Graphify generation did not produce a usable graph.json")
    print(str(graph))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
