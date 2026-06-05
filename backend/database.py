import aiosqlite
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat.db"


async def init_db():
    """Initialize the SQLite database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                agents_config TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                role TEXT NOT NULL,
                agent_name TEXT,
                provider TEXT,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            )
        """)
        await db.commit()


async def save_room(room_id: str, name: str, agents_config: list[dict]):
    """Save or update a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO rooms (id, name, agents_config, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (room_id, name, json.dumps(agents_config), time.time()),
        )
        await db.commit()


async def get_room(room_id: str) -> dict | None:
    """Get a room by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "agents_config": json.loads(row["agents_config"]),
                    "created_at": row["created_at"],
                }
    return None


async def list_rooms() -> list[dict]:
    """List all rooms."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rooms ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "agents_config": json.loads(row["agents_config"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]


async def delete_room(room_id: str):
    """Delete a room and its messages."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
        await db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        await db.commit()


async def save_message(
    room_id: str,
    role: str,
    content: str,
    agent_name: str | None = None,
    provider: str | None = None,
):
    """Save a message to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO messages (room_id, role, agent_name, provider, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room_id, role, agent_name, provider, content, time.time()),
        )
        await db.commit()


async def get_messages(room_id: str, limit: int = 100) -> list[dict]:
    """Get recent messages for a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM messages
            WHERE room_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (room_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "role": row["role"],
                    "agent_name": row["agent_name"],
                    "provider": row["provider"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ]
