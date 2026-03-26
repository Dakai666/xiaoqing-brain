import jieba
from rank_bm25 import BM25Okapi
from typing import List, Tuple
from ..models.memory_unit import MemoryUnit


class BM25Retriever:
    def __init__(self):
        self.memories: List[MemoryUnit] = []
        self.bm25: BM25Okapi = None
        jieba.initialize()

    def index(self, memories: List[MemoryUnit]):
        self.memories = memories
        if not memories:
            self.bm25 = None
            return
        
        tokenized = [jieba.lcut(m.lossless_text) for m in memories]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[MemoryUnit, float]]:
        if not self.bm25 or not self.memories:
            return []
        
        tokenized_query = jieba.lcut(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.memories[i], scores[i]) for i in top_indices if scores[i] > 0]

    def add(self, memory: MemoryUnit):
        self.memories.append(memory)
        tokenized = [jieba.lcut(m.lossless_text) for m in self.memories]
        self.bm25 = BM25Okapi(tokenized)
