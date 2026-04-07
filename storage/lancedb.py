import os
import lancedb
import pyarrow as pa
from typing import List, Optional
from ..models.memory_unit import MemoryUnit


EMBED_MODEL_OLLAMA = "qwen3-embedding:4b"
EMBED_MODEL_MINIMAX = "embo-01"


class LanceDBStorage:
    def __init__(
        self,
        db_path: str = "./data/lancedb",
        embed_model: Optional[str] = None,
        embed_dim: int = 2560,
    ):
        self.db_path = db_path
        self.embed_dim = embed_dim
        
        api_key = os.getenv("MINIMAX_API_KEY", "")
        if api_key and embed_model is None:
            self.embed_model = EMBED_MODEL_MINIMAX
            self.use_minimax = True
        else:
            self.embed_model = embed_model or EMBED_MODEL_OLLAMA
            self.use_minimax = False
        
        self.db = lancedb.connect(db_path)
        self._ensure_table()

    def _ensure_table(self):
        if "memories" not in self.db.table_names():
            self.db.create_table("memories", schema=self._schema())

    def _schema(self):
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("lossless_text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.embed_dim)),
            pa.field("keywords", pa.list_(pa.string())),
            pa.field("timestamp", pa.string()),
            pa.field("date", pa.string()),
            pa.field("persons", pa.list_(pa.string())),
            pa.field("topic", pa.string()),
            pa.field("session_id", pa.string()),
            pa.field("intent_type", pa.string()),
            pa.field("source_reliability", pa.float64()),
            pa.field("decay_rate", pa.string()),
            pa.field("confidence", pa.float64()),
            pa.field("last_accessed", pa.string()),
            pa.field("access_count", pa.int64()),
            pa.field("is_superseded", pa.bool_()),
            pa.field("replaced_by", pa.string()),
            pa.field("needs_confirmation", pa.bool_()),
        ])

    async def _embed(self, text: str) -> List[float]:
        if self.use_minimax:
            try:
                from ..utils.llm_backend import get_llm_backend
                backend = get_llm_backend()
                response = await backend.embeddings(self.embed_model, text)
                return response["embedding"]
            except Exception as e:
                print(f"MiniMax embeddings failed ({e}), falling back to Ollama")
        
        import ollama
        response = ollama.embeddings(model=EMBED_MODEL_OLLAMA, prompt=text)
        return response["embedding"]

    async def add(self, memory: MemoryUnit) -> str:
        vector = await self._embed(memory.lossless_text)
        data = {
            "id": memory.id,
            "lossless_text": memory.lossless_text,
            "vector": vector,
            "keywords": memory.keywords,
            "timestamp": memory.timestamp,
            "date": memory.date,
            "persons": memory.persons,
            "topic": memory.topic,
            "session_id": memory.session_id,
            "intent_type": memory.intent_type.value,
            "source_reliability": memory.source_reliability,
            "decay_rate": memory.decay_rate.value,
            "confidence": memory.confidence,
            "last_accessed": memory.last_accessed,
            "access_count": memory.access_count,
            "is_superseded": memory.is_superseded,
            "replaced_by": memory.replaced_by,
            "needs_confirmation": memory.needs_confirmation,
        }
        self.db["memories"].add([data])
        return memory.id

    async def search(self, query: str, top_k: int = 5) -> List[MemoryUnit]:
        query_vector = await self._embed(query)
        results = self.db["memories"].search(query_vector, vector_column_name="vector").limit(top_k).to_list()
        
        memories = []
        for r in results:
            memories.append(MemoryUnit(
                id=r["id"],
                lossless_text=r["lossless_text"],
                keywords=r["keywords"],
                timestamp=r["timestamp"],
                date=r.get("date", r["timestamp"][:10] if r.get("timestamp") else ""),
                persons=r["persons"],
                topic=r["topic"],
                session_id=r["session_id"],
                intent_type=r.get("intent_type", "fact"),
                source_reliability=r.get("source_reliability", 1.0),
                decay_rate=r.get("decay_rate", "normal"),
                confidence=r.get("confidence", 1.0),
                last_accessed=r.get("last_accessed"),
                access_count=r.get("access_count", 0),
                is_superseded=r.get("is_superseded", False),
                replaced_by=r.get("replaced_by"),
                needs_confirmation=r.get("needs_confirmation", False),
            ))
        return memories

    async def get_by_topic(self, topic: str) -> List[MemoryUnit]:
        results = self.db["memories"].search(None, vector_column_name="vector").where(f"topic = '{topic}'").limit(100).to_list()
        return [self._row_to_memory(r) for r in results]

    async def get_by_person(self, person: str) -> List[MemoryUnit]:
        results = self.db["memories"].search(None, vector_column_name="vector").limit(100).to_list()
        filtered = [r for r in results if person in r.get("persons", [])]
        return [self._row_to_memory(r) for r in filtered]

    async def get_by_date_range(self, start_date: str, end_date: Optional[str] = None) -> List[MemoryUnit]:
        if end_date:
            results = self.db["memories"].search(None, vector_column_name="vector").where(f"date >= '{start_date}' AND date <= '{end_date}'").limit(100).to_list()
        else:
            results = self.db["memories"].search(None, vector_column_name="vector").where(f"date = '{start_date}'").limit(100).to_list()
        return [self._row_to_memory(r) for r in results]

    def _row_to_memory(self, row: dict) -> MemoryUnit:
        return MemoryUnit(
            id=row["id"],
            lossless_text=row["lossless_text"],
            keywords=row["keywords"],
            timestamp=row["timestamp"],
            date=row.get("date", row["timestamp"][:10] if row.get("timestamp") else ""),
            persons=row["persons"],
            topic=row["topic"],
            session_id=row["session_id"],
            intent_type=row.get("intent_type", "fact"),
            source_reliability=row.get("source_reliability", 1.0),
            decay_rate=row.get("decay_rate", "normal"),
            confidence=row.get("confidence", 1.0),
            last_accessed=row.get("last_accessed"),
            access_count=row.get("access_count", 0),
            is_superseded=row.get("is_superseded", False),
            replaced_by=row.get("replaced_by"),
            needs_confirmation=row.get("needs_confirmation", False),
        )
