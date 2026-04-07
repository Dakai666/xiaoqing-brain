import sqlite3
import json
from typing import List, Optional
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
                    date TEXT,
                    persons TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    provenance TEXT,
                    created_at TEXT NOT NULL,
                    intent_type TEXT DEFAULT 'fact',
                    source_reliability REAL DEFAULT 1.0,
                    decay_rate TEXT DEFAULT 'normal',
                    confidence REAL DEFAULT 1.0,
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON memories(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memories(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON memories(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_confidence ON memories(confidence)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intent ON memories(intent_type)")

    def add(self, memory: MemoryUnit) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memories (id, lossless_text, keywords, timestamp, date, persons, topic, session_id, provenance, created_at, intent_type, source_reliability, decay_rate, confidence, last_accessed, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.id,
                memory.lossless_text,
                json.dumps(memory.keywords),
                memory.timestamp,
                memory.date,
                json.dumps(memory.persons),
                memory.topic,
                memory.session_id,
                memory.provenance,
                datetime.now().isoformat(),
                memory.intent_type.value,
                memory.source_reliability,
                memory.decay_rate.value,
                memory.confidence,
                memory.last_accessed,
                memory.access_count
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

    def get_by_date_range(self, start_date: str, end_date: Optional[str] = None) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if end_date:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE date >= ? AND date <= ? ORDER BY timestamp DESC",
                    (start_date, end_date)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE date = ? ORDER BY timestamp DESC",
                    (start_date,)
                )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_today_memories(self) -> List[MemoryUnit]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_by_date_range(today)

    def update_confidence(self, memory_id: str, confidence: float) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE memories SET confidence = ? WHERE id = ?",
                (confidence, memory_id)
            )
            return cursor.rowcount > 0

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryUnit:
        from ..models.memory_unit import DecayRate, IntentType
        decay_rate_val = row["decay_rate"] if "decay_rate" in row.keys() else "normal"
        confidence_val = row["confidence"] if "confidence" in row.keys() else 1.0
        intent_type_val = row["intent_type"] if "intent_type" in row.keys() else "fact"
        source_reliability_val = row["source_reliability"] if "source_reliability" in row.keys() else 1.0
        return MemoryUnit(
            id=row["id"],
            lossless_text=row["lossless_text"],
            keywords=json.loads(row["keywords"]),
            timestamp=row["timestamp"],
            date=row["date"] if row["date"] else row["timestamp"][:10],
            persons=json.loads(row["persons"]),
            topic=row["topic"],
            session_id=row["session_id"],
            provenance=row["provenance"],
            intent_type=IntentType(intent_type_val),
            source_reliability=float(source_reliability_val),
            decay_rate=DecayRate(decay_rate_val),
            confidence=float(confidence_val),
            last_accessed=row["last_accessed"] if "last_accessed" in row.keys() else None,
            access_count=int(row["access_count"]) if "access_count" in row.keys() else 0,
        )
