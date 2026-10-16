import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / "wardrobe.sqlite3"
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, record TEXT NOT NULL,
                    wardrobe TEXT NOT NULL DEFAULT 'personal'
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    constraints TEXT NOT NULL DEFAULT '{}',
                    wardrobe TEXT NOT NULL DEFAULT 'personal'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL, record TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    record TEXT NOT NULL
                );
            """)
            for table in ("items", "conversations"):
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "wardrobe" not in columns:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN wardrobe TEXT NOT NULL DEFAULT 'personal'"
                    )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS items_wardrobe ON items(wardrobe)"
            )

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=15)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def items(self, wardrobe="personal"):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT record FROM items WHERE wardrobe = ? ORDER BY rowid DESC",
                (wardrobe,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def item_page(self, wardrobe, category, search, offset, limit):
        filters = ["wardrobe = ?"]
        parameters = [wardrobe]
        if category:
            filters.append("json_extract(record, '$.category') = ?")
            parameters.append(category)
        if search:
            filters.append(
                "lower(json_extract(record, '$.name') || ' ' || "
                "json_extract(record, '$.color') || ' ' || "
                "json_extract(record, '$.subtype')) LIKE ?"
            )
            parameters.append(f"%{search.lower()}%")
        condition = " AND ".join(filters)
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM items WHERE {condition}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT record FROM items WHERE {condition} ORDER BY id LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return [json.loads(row[0]) for row in rows], total

    def count_items(self, wardrobe):
        with self.connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM items WHERE wardrobe = ?", (wardrobe,)
            ).fetchone()[0]

    def item(self, item_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_item(self, item):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO items(id, record, wardrobe) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET record=excluded.record, wardrobe=excluded.wardrobe",
                (item["id"], json.dumps(item), item.get("wardrobe", "personal")),
            )

    def save_items(self, items):
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO items(id, record, wardrobe) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET record=excluded.record, wardrobe=excluded.wardrobe",
                [
                    (item["id"], json.dumps(item), item.get("wardrobe", "personal"))
                    for item in items
                ],
            )

    def delete_item(self, item_id):
        with self.connect() as connection:
            connection.execute("DELETE FROM items WHERE id = ?", (item_id,))

    def reset_constraints(self, wardrobe="personal"):
        with self.connect() as connection:
            connection.execute(
                "UPDATE conversations SET constraints = '{}' WHERE wardrobe = ?",
                (wardrobe,),
            )

    def create_conversation(self, wardrobe="personal"):
        conversation_id = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO conversations(id, created_at, wardrobe) VALUES (?, ?, ?)",
                (conversation_id, timestamp(), wardrobe),
            )
        return self.conversation(conversation_id)

    def latest_conversation(self, wardrobe="personal"):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM conversations WHERE wardrobe = ? ORDER BY created_at DESC LIMIT 1",
                (wardrobe,),
            ).fetchone()
        return self.conversation(row[0]) if row else None

    def conversation(self, conversation_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT constraints, wardrobe FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if not row:
                return None
            messages = connection.execute(
                "SELECT record FROM messages WHERE conversation_id = ? ORDER BY sequence",
                (conversation_id,),
            ).fetchall()
        return {
            "id": conversation_id,
            "wardrobe": row[1],
            "constraints": json.loads(row[0]),
            "messages": [json.loads(message[0]) for message in messages],
        }

    def save_exchange(self, conversation_id, text, reply, constraints):
        user_message = {
            "id": str(uuid4()),
            "role": "user",
            "text": text,
            "outfits": [],
            "created_at": timestamp(),
        }
        assistant_message = {
            "id": str(uuid4()),
            "role": "assistant",
            "text": reply["message"],
            "outfits": reply["outfits"],
            "created_at": timestamp(),
        }
        with self.connect() as connection:
            for message in (user_message, assistant_message):
                connection.execute(
                    "INSERT INTO messages(conversation_id, record) VALUES (?, ?)",
                    (conversation_id, json.dumps(message)),
                )
            connection.execute(
                "UPDATE conversations SET constraints = ? WHERE id = ?",
                (json.dumps(constraints), conversation_id),
            )
        return assistant_message

    def save_benchmark(self, result):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO benchmarks(id, created_at, record) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                (result["id"], result["created_at"], json.dumps(result)),
            )

    def benchmark(self, benchmark_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record FROM benchmarks WHERE id = ?", (benchmark_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def latest_benchmark(self):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record FROM benchmarks ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return json.loads(row[0]) if row else None


def public_item(item):
    return {
        key: value
        for key, value in item.items()
        if key not in ("embedding", "filename", "thumbnail")
    }
