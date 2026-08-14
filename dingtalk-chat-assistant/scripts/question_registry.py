#!/usr/bin/env python3

import argparse
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path


STATUS_VALUES = {
    "draft",
    "prepared",
    "sent",
    "answered",
    "ambiguous",
    "needs_follow_up",
    "failed",
    "closed",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    open_dingtalk_id TEXT NOT NULL,
    conversation_id TEXT,
    title TEXT NOT NULL,
    content_sha256 TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    query_since TEXT NOT NULL,
    open_task_id TEXT,
    outbound_message_id TEXT,
    last_checked_at TEXT,
    reply_message_id TEXT,
    reply_at TEXT,
    origin_thread_id TEXT,
    origin_task TEXT,
    error TEXT
)
"""


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_seconds(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime:
    if not value:
        return now_local()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()


def default_state_file() -> Path:
    return (
        Path.home()
        / ".codex"
        / "state"
        / "dingtalk-chat-assistant"
        / "questions.sqlite3"
    )


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA)
    connection.commit()
    return connection


def fetch_question(connection: sqlite3.Connection, question_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM questions WHERE question_id = ?", (question_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown question id: {question_id}")
    return row


def require_status(row: sqlite3.Row, allowed: set[str]) -> None:
    if row["status"] not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"Question {row['question_id']} is {row['status']}; expected {allowed_text}."
        )


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True))


def row_dict(row: sqlite3.Row, state_file: Path) -> dict[str, object]:
    result = dict(row)
    result["stateFile"] = str(state_file.resolve())
    return result


def create_question_id(connection: sqlite3.Connection, created_at: datetime) -> str:
    for _ in range(10):
        candidate = f"Q-{created_at:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        exists = connection.execute(
            "SELECT 1 FROM questions WHERE question_id = ?", (candidate,)
        ).fetchone()
        if exists is None:
            return candidate
    raise RuntimeError("Could not allocate a unique question id.")


def command_new(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    created_at = now_local()
    question_id = create_question_id(connection, created_at)
    query_since = (created_at - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        """
        INSERT INTO questions (
            question_id, status, recipient_name, user_id, open_dingtalk_id,
            title, created_at, query_since, origin_thread_id, origin_task
        ) VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            args.recipient_name,
            args.user_id,
            args.open_dingtalk_id,
            args.title,
            iso_seconds(created_at),
            query_since,
            args.origin_thread_id,
            args.origin_task,
        ),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, question_id), state_file))


def command_prepare(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"draft", "prepared"})
    content_hash = hashlib.sha256(Path(args.content_file).read_bytes()).hexdigest()
    connection.execute(
        "UPDATE questions SET status = 'prepared', content_sha256 = ?, error = NULL "
        "WHERE question_id = ?",
        (content_hash, args.question_id),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_mark_sent(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"prepared", "sent"})
    sent_at = parse_time(args.sent_at)
    query_since = (sent_at - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        """
        UPDATE questions
        SET status = 'sent', sent_at = ?, query_since = ?,
            open_task_id = COALESCE(?, open_task_id),
            conversation_id = COALESCE(?, conversation_id), error = NULL
        WHERE question_id = ?
        """,
        (
            iso_seconds(sent_at),
            query_since,
            args.open_task_id,
            args.conversation_id,
            args.question_id,
        ),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_mark_outbound(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"sent", "ambiguous", "needs_follow_up", "answered"})
    connection.execute(
        "UPDATE questions SET outbound_message_id = ? WHERE question_id = ?",
        (args.message_id, args.question_id),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_mark_checked(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"sent", "ambiguous", "needs_follow_up", "answered"})
    checked_at = parse_time(args.checked_at)
    connection.execute(
        "UPDATE questions SET last_checked_at = ? WHERE question_id = ?",
        (iso_seconds(checked_at), args.question_id),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_mark_reply(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"sent", "ambiguous", "needs_follow_up", "answered"})
    reply_at = parse_time(args.reply_at)
    status = {
        "answered": "answered",
        "ambiguous": "ambiguous",
        "needs-follow-up": "needs_follow_up",
    }[args.classification]
    connection.execute(
        """
        UPDATE questions
        SET status = ?, reply_message_id = ?, reply_at = ?, last_checked_at = ?
        WHERE question_id = ?
        """,
        (
            status,
            args.message_id,
            iso_seconds(reply_at),
            iso_seconds(now_local()),
            args.question_id,
        ),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_mark_failed(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"draft", "prepared"})
    connection.execute(
        "UPDATE questions SET status = 'failed', error = ? WHERE question_id = ?",
        (args.error, args.question_id),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_close(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    row = fetch_question(connection, args.question_id)
    require_status(row, {"answered", "ambiguous", "needs_follow_up", "sent"})
    connection.execute(
        "UPDATE questions SET status = 'closed' WHERE question_id = ?",
        (args.question_id,),
    )
    connection.commit()
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_get(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    emit(row_dict(fetch_question(connection, args.question_id), state_file))


def command_list(
    connection: sqlite3.Connection, args: argparse.Namespace, state_file: Path
) -> None:
    if args.status:
        rows = connection.execute(
            "SELECT * FROM questions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (args.status, args.limit),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM questions ORDER BY created_at DESC LIMIT ?", (args.limit,)
        ).fetchall()
    emit(
        {
            "items": [row_dict(row, state_file) for row in rows],
            "stateFile": str(state_file.resolve()),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track DingTalk product-manager confirmation questions."
    )
    parser.add_argument("--state-file", type=Path, default=default_state_file())
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--recipient-name", required=True)
    new_parser.add_argument("--user-id", required=True)
    new_parser.add_argument("--open-dingtalk-id", required=True)
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--origin-thread-id")
    new_parser.add_argument("--origin-task")

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--question-id", required=True)
    prepare_parser.add_argument("--content-file", required=True)

    sent_parser = subparsers.add_parser("mark-sent")
    sent_parser.add_argument("--question-id", required=True)
    sent_parser.add_argument("--open-task-id")
    sent_parser.add_argument("--conversation-id")
    sent_parser.add_argument("--sent-at")

    outbound_parser = subparsers.add_parser("mark-outbound")
    outbound_parser.add_argument("--question-id", required=True)
    outbound_parser.add_argument("--message-id", required=True)

    checked_parser = subparsers.add_parser("mark-checked")
    checked_parser.add_argument("--question-id", required=True)
    checked_parser.add_argument("--checked-at")

    reply_parser = subparsers.add_parser("mark-reply")
    reply_parser.add_argument("--question-id", required=True)
    reply_parser.add_argument("--message-id", required=True)
    reply_parser.add_argument("--reply-at")
    reply_parser.add_argument(
        "--classification",
        choices=["answered", "ambiguous", "needs-follow-up"],
        required=True,
    )

    failed_parser = subparsers.add_parser("mark-failed")
    failed_parser.add_argument("--question-id", required=True)
    failed_parser.add_argument("--error", required=True)

    close_parser = subparsers.add_parser("close")
    close_parser.add_argument("--question-id", required=True)

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("--question-id", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=sorted(STATUS_VALUES))
    list_parser.add_argument("--limit", type=int, default=50, choices=range(1, 101))

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    state_file = args.state_file
    connection = connect(state_file)
    try:
        commands = {
            "new": command_new,
            "prepare": command_prepare,
            "mark-sent": command_mark_sent,
            "mark-outbound": command_mark_outbound,
            "mark-checked": command_mark_checked,
            "mark-reply": command_mark_reply,
            "mark-failed": command_mark_failed,
            "close": command_close,
            "get": command_get,
            "list": command_list,
        }
        commands[args.command](connection, args, state_file)
    except (OSError, sqlite3.Error, ValueError) as error:
        emit({"error": str(error), "stateFile": str(state_file.resolve())})
        return 2
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
