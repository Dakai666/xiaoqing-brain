import sqlite3
import json
from typing import List
from datetime import datetime
from ..models.memory_unit import MemoryUnit


class SQLiteStorage:
    def __init__(self, db_path: str = "./data/memories.db"):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    lossless_text TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    persons TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    provenance TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON memories(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memories(session_id)")

    def add(self, memory: MemoryUnit) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memories (id, lossless_text, keywords, timestamp, persons, topic, session_id, provenance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.id,
                memory.lossless_text,
                json.dumps(memory.keywords),
                memory.timestamp,
                json.dumps(memory.persons),
                memory.topic,
                memory.session_id,
                memory.provenance,
                datetime.now().isoformat()
            ))
        return memory.id

    def search(self, query: str, top_k: int = 5) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE lossless_text LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", top_k)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_topic(self, topic: str) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM memories WHERE topic = ? ORDER BY timestamp DESC", (topic,))
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_person(self, person: str) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE persons LIKE ? ORDER BY timestamp DESC",
                (f"%{person}%",)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_session(self, session_id: str) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryUnit:
        return MemoryUnit(
            id=row["id"],
            lossless_text=row["lossless_text"],
            keywords=json.loads(row["keywords"]),
            timestamp=row["timestamp"],
            persons=json.loads(row["persons"]),
            topic=row["topic"],
            session_id=row["session_id"],
            provenance=row["provenance"],
        )
