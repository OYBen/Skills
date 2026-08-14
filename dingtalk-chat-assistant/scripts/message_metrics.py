#!/usr/bin/env python3

import argparse
import codecs
import json
from pathlib import Path


def measure_text(text: str, limit: int) -> dict[str, int | bool]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    character_count = len(normalized)
    return {
        "characterCount": character_count,
        "utf8Bytes": len(normalized.encode("utf-8")),
        "exceedsLimit": character_count > limit,
        "withinLimit": character_count <= limit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure a UTF-8 DingTalk message using Unicode code points."
    )
    parser.add_argument("--file", required=True, help="UTF-8 message file to inspect")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--require-normalized",
        action="store_true",
        help="Fail if the file has a UTF-8 BOM or non-LF line endings.",
    )
    args = parser.parse_args()

    path = Path(args.file)
    raw = path.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    metrics = measure_text(text, args.limit)
    metrics.update(
        {
            "file": str(path.resolve()),
            "limit": args.limit,
            "actualFileBytes": len(raw),
            "hasUtf8Bom": has_bom,
            "hasNonLfLineEndings": text != normalized,
            "readyForAttachment": not has_bom and text == normalized,
        }
    )
    print(json.dumps(metrics, ensure_ascii=True, sort_keys=True))

    if args.require_normalized and not metrics["readyForAttachment"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
