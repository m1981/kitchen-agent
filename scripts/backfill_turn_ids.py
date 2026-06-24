"""
scripts/backfill_turn_ids.py
=============================
One-time migration: assign turn_id to UI history messages that are missing it.

Run:
    cd kitchen-agent
    .venv/bin/python scripts/backfill_turn_ids.py

Idempotent — messages that already have a turn_id are left unchanged.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings


def backfill(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT id, ui_history_json FROM sessions")
    rows = cursor.fetchall()

    updated_sessions = 0
    updated_messages = 0

    for row in rows:
        session_id = row["id"]
        ui_json = row["ui_history_json"]

        if not ui_json or ui_json == "[]":
            continue

        try:
            messages = json.loads(ui_json)
        except json.JSONDecodeError:
            print(f"  SKIP {session_id}: invalid JSON")
            continue

        changed = False
        for msg in messages:
            if msg.get("role") in ("user", "assistant") and not msg.get("turn_id"):
                msg["turn_id"] = str(uuid.uuid4())
                updated_messages += 1
                changed = True

        if changed:
            new_json = json.dumps(messages)
            conn.execute(
                "UPDATE sessions SET ui_history_json = ? WHERE id = ?",
                (new_json, session_id),
            )
            updated_sessions += 1
            print(f"  FIXED {session_id}: {sum(1 for m in messages if m.get('turn_id'))} messages with turn_id")

    conn.commit()
    conn.close()

    print(f"\nDone: {updated_sessions} sessions updated, {updated_messages} messages got turn_id")


if __name__ == "__main__":
    db_path = settings.db_path
    print(f"Backfilling turn_ids in {db_path}")
    backfill(db_path)
