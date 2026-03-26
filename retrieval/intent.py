import json
from typing import Optional
from ..models.memory_unit import MemoryUnit
from ..retrieval.hybrid import HybridRetriever
from ..utils.llm_backend import get_llm_backend, LLMBackend


INTENT_ANALYSIS_PROMPT = """分析用戶的查詢意圖，判斷應該用什麼方式檢索記憶。

## 用戶查詢
{query}

## 輸出格式（JSON）
{{
    "intent_type": "simple|complex|clarifying",
    "search_keywords": ["關鍵詞1", "關鍵詞2"],
    "filters": {{
        "topic": "personal|preference|technical|...",
        "persons": ["人名"],
        "time_range": "today|week|month|all"
    }},
    "explanation": "為什麼這樣判斷"
}}"""


class IntentRetriever:
    def __init__(
        self,
        hybrid_retriever: HybridRetriever,
        model: str = "qwen3.5:2b",
        keep_alive: int = 300,
        backend: Optional[LLMBackend] = None,
    ):
        self.hybrid = hybrid_retriever
        self.model = model
        self.keep_alive = keep_alive
        self.backend = backend

    def _get_backend(self) -> LLMBackend:
        return self.backend or get_llm_backend()

    async def analyze_intent(self, query: str) -> dict:
        prompt = INTENT_ANALYSIS_PROMPT.format(query=query)
        backend = self._get_backend()
        
        try:
            response = await backend.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            
            content = response["message"]["content"].strip()
            
            if not content:
                raise ValueError("Empty response from model")
            
            if content.startswith("<think>"):
                content = content.split("</think>")[-1].strip()
            
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            if not content:
                raise ValueError("Empty content after parsing")
            
            return json.loads(content)
        except (json.JSONDecodeError, ValueError, Exception) as e:
            print(f"Intent analysis error: {e}")
            return {
                "intent_type": "simple",
                "search_keywords": query.split(),
                "filters": {},
                "explanation": "fallback to simple search"
            }

    async def search(self, query: str, top_k: int = 5) -> dict:
        intent = await self.analyze_intent(query)
        
        if intent["intent_type"] == "simple":
            return await self._simple_search(query, top_k)
        elif intent["intent_type"] == "complex":
            return await self._complex_search(query, intent, top_k)
        else:
            return {"results": [], "intent": intent, "message": "需要澄清"}

    async def _simple_search(self, query: str, top_k: int) -> dict:
        results = await self.hybrid.search(query, top_k)
        return {
            "results": results["vector"] + results["bm25"],
            "intent": {"intent_type": "simple", "query": query},
            "method": "hybrid"
        }

    async def _complex_search(self, query: str, intent: dict, top_k: int) -> dict:
        keywords = intent.get("search_keywords", [])
        filters = intent.get("filters", {})
        
        all_results = []
        
        for keyword in keywords:
            results = await self.hybrid.search(keyword, top_k)
            all_results.extend(results["vector"])
        
        if filters.get("topic"):
            topic_results = await self.hybrid.lancedb.get_by_topic(filters["topic"])
            all_results.extend(topic_results)
        
        if filters.get("persons"):
            for person in filters["persons"]:
                person_results = await self.hybrid.lancedb.get_by_person(person)
                all_results.extend(person_results)
        
        seen = set()
        unique_results = []
        for m in all_results:
            if m.id not in seen:
                seen.add(m.id)
                unique_results.append(m)
        
        return {
            "results": unique_results[:top_k],
            "intent": intent,
            "method": "multi-dimensional"
        }
