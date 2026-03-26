from typing import List, Optional
from ..models.memory_unit import MemoryUnit
from ..models.topics import TOPICS, is_valid_topic
from ..storage.lancedb import LanceDBStorage
from ..storage.sqlite import SQLiteStorage
from ..storage.markdown import MarkdownBackup
from ..retrieval.bm25 import BM25Retriever


class HybridRetriever:
    def __init__(
        self,
        lancedb: Optional[LanceDBStorage] = None,
        sqlite: Optional[SQLiteStorage] = None,
        markdown_backup: Optional[MarkdownBackup] = None,
    ):
        self.lancedb = lancedb or LanceDBStorage()
        self.sqlite = sqlite or SQLiteStorage()
        self.markdown = markdown_backup or MarkdownBackup()
        self.bm25 = BM25Retriever()
        self._indexed = False

    def sync_bm25(self):
        all_memories = self.sqlite.get_by_session("")
        if not all_memories:
            all_memories = self.sqlite.search("", 1000)
        self.bm25.index(all_memories)
        self._indexed = True

    async def vector_search(self, query: str, top_k: int = 5) -> List[MemoryUnit]:
        return await self.lancedb.search(query, top_k)

    def bm25_search(self, query: str, top_k: int = 5) -> List[MemoryUnit]:
        results = self.bm25.search(query, top_k)
        return [m for m, _ in results]

    async def search(self, query: str, top_k: int = 5) -> dict:
        if not self._indexed:
            self.sync_bm25()
        
        vector_results = await self.vector_search(query, top_k)
        bm25_results = self.bm25_search(query, top_k)
        
        return {
            "vector": vector_results,
            "bm25": bm25_results,
        }

    def _validate_topic(self, memory: MemoryUnit) -> MemoryUnit:
        if memory.topic and not is_valid_topic(memory.topic):
            memory.topic = "general"
        return memory

    async def add_memory(self, memory: MemoryUnit):
        memory = self._validate_topic(memory)
        await self.lancedb.add(memory)
        self.sqlite.add(memory)
        self.markdown.add_memory(memory)
        self.bm25.add(memory)
