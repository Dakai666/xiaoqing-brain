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
        all_memories = self.sqlite.get_active_memories(1000)
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

        # 向量檢索失敗（例如 embedding 額度用盡、模型未就緒）時降級為純 BM25，
        # 寧可檢索品質差，也不要整個查詢掛掉。
        try:
            vector_results = await self.vector_search(query, top_k)
        except Exception as e:
            print(f"[HybridRetriever] 向量檢索失敗，降級為 BM25: {e}", flush=True)
            vector_results = []
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
        try:
            await self.lancedb.add(memory)
        except Exception as e:
            # 向量層失敗（例如 embedding 模型未就緒、額度用盡）時降級：
            # 記憶仍要寫進 SQLite / BM25 / markdown，否則整段互動就白記了。
            print(
                f"[HybridRetriever] 向量寫入失敗，已降級為 SQLite/BM25/markdown: {e}",
                flush=True,
            )
        self.sqlite.add(memory)
        self.markdown.add_memory(memory)
        self.bm25.add(memory)
