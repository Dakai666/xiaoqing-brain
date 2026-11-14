import os
import sqlite3
import json
from typing import List, Optional
from datetime import datetime
from ..models.memory_unit import MemoryUnit


#: 記憶資料目錄。優先用 XIAOQING_DATA_DIR（opencode.json 已設定），
#: 否則用 brain 套件旁的 data/。**不要用相對路徑**：
#: 相對路徑綁定 CWD，從其他目錄執行會開出一個空庫。
DATA_DIR = os.environ.get(
    "XIAOQING_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)


class SQLiteStorage:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, "memories.db")
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
                    access_count INTEGER DEFAULT 0,
                    is_superseded INTEGER DEFAULT 0,
                    replaced_by TEXT,
                    needs_confirmation INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON memories(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memories(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON memories(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_confidence ON memories(confidence)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intent ON memories(intent_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_superseded ON memories(is_superseded)")

    def supersede(self, memory_id: str, replaced_by_id: str) -> bool:
        """將舊記憶標記為已被新記憶取代（is_superseded = 1）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE memories SET is_superseded = 1, replaced_by = ? WHERE id = ? OR id LIKE ?",
                (replaced_by_id, memory_id, f"{memory_id}%")
            )
            return cursor.rowcount > 0

    def delete(self, memory_id: str) -> bool:
        """永久刪除特定記憶"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ? OR id LIKE ?",
                (memory_id, f"{memory_id}%")
            )
            return cursor.rowcount > 0

    def get_active_memories(self, limit: int = 500) -> List[MemoryUnit]:
        """取得所有未被取代的有效記憶"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE is_superseded = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_all_memories(self, limit: int = 100000) -> List[MemoryUnit]:
        """取得所有記憶（含已被取代的舊記憶）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def add(self, memory: MemoryUnit) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memories (id, lossless_text, keywords, timestamp, date, persons, topic, session_id, provenance, created_at, intent_type, source_reliability, decay_rate, confidence, last_accessed, access_count, is_superseded, replaced_by, needs_confirmation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                memory.access_count,
                1 if memory.is_superseded else 0,
                memory.replaced_by,
                1 if memory.needs_confirmation else 0
            ))
        return memory.id

    def search(self, query: str, top_k: int = 5) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE is_superseded = 0 AND lossless_text LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", top_k)
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_topic(self, topic: str) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM memories WHERE is_superseded = 0 AND topic = ? ORDER BY timestamp DESC", (topic,))
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_person(self, person: str) -> List[MemoryUnit]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memories WHERE is_superseded = 0 AND persons LIKE ? ORDER BY timestamp DESC",
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
            is_superseded=bool(row["is_superseded"]) if "is_superseded" in row.keys() else False,
            replaced_by=row["replaced_by"] if "replaced_by" in row.keys() else None,
            needs_confirmation=bool(row["needs_confirmation"]) if "needs_confirmation" in row.keys() else False,
        )
