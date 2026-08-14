#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


WATERMARKS = {
    "generated": "\u3010AI\u751f\u6210\u3011",
    "assisted": "\u3010AI\u8f85\u52a9\u53d1\u9001\u3011",
}


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def apply_watermark(text: str, mode: str) -> str:
    normalized = normalize_text(text)
    body = normalized
    for marker in WATERMARKS.values():
        if body == marker:
            body = ""
            break
        if body.startswith(marker + "\n"):
            body = body[len(marker) :].lstrip("\n")
            break

    if not body.strip():
        raise ValueError("Message body is empty after removing an existing watermark.")
    return f"{WATERMARKS[mode]}\n\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply a visible provenance watermark to a DingTalk message."
    )
    parser.add_argument("--input", required=True, help="UTF-8 source message file")
    parser.add_argument("--output", required=True, help="UTF-8 watermarked output file")
    parser.add_argument(
        "--mode",
        choices=sorted(WATERMARKS),
        required=True,
        help="generated for AI-authored text; assisted for verbatim user text",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    source = input_path.read_bytes().decode("utf-8-sig")
    watermarked = apply_watermark(source, args.mode)
    encoded = watermarked.encode("utf-8")
    output_path.write_bytes(encoded)

    print(
        json.dumps(
            {
                "characterCount": len(watermarked),
                "input": str(input_path.resolve()),
                "mode": args.mode,
                "output": str(output_path.resolve()),
                "utf8Bytes": len(encoded),
                "watermark": WATERMARKS[args.mode],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
