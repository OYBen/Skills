#!/usr/bin/env python3

import argparse
import getpass
import json
import os
import sys
from pathlib import Path


def default_output() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "trusted-recipient.local.json"


def require_value(label: str, *, secret: bool = False) -> str:
    if secret:
        value = getpass.getpass(f"{label}: ").strip()
    else:
        print(f"{label}: ", end="", file=sys.stderr, flush=True)
        value = input().strip()
    if not value or value.startswith("<") or value.endswith(">"):
        raise ValueError(f"{label} must be a resolved value")
    return value


def validated_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Trusted recipient input must be a JSON object")
    result = {}
    for key in ("name", "userId", "openDingTalkId"):
        item = str(value.get(key, "")).strip()
        if not item or item.startswith("<") or item.endswith(">"):
            raise ValueError(f"{key} must be a resolved value")
        result[key] = item
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the local trusted DingTalk recipient configuration."
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Read name and both DingTalk IDs from a local UTF-8 JSON file.",
    )
    parser.add_argument("--output", type=Path, default=default_output())
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.from_file:
            payload = validated_payload(
                json.loads(args.from_file.read_text(encoding="utf-8-sig"))
            )
        else:
            payload = validated_payload(
                {
                    "name": require_value("Trusted recipient name"),
                    "userId": require_value("Trusted recipient userId", secret=True),
                    "openDingTalkId": require_value(
                        "Trusted recipient openDingTalkId", secret=True
                    ),
                }
            )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
        try:
            output.chmod(0o600)
        except OSError:
            pass
        print(
            json.dumps(
                {"configured": True, "output": str(output)},
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except (EOFError, KeyboardInterrupt, OSError, ValueError) as error:
        print(json.dumps({"configured": False, "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
