import json
from typing import List, Optional
from ..models.memory_unit import MemoryUnit
from ..utils.llm_backend import get_llm_backend, LLMBackend


SYNTHESIS_PROMPT = """你是一個語義合成系統。你的任務是整合同 session 內的多個記憶片段，產生更緊湊、統一的表述。

## 輸入
以下是來自同一 session 的多個記憶片段：
{memories}

## 規則
1. 合併重複資訊（如「喜歡喝咖啡」+「偏好熱咖啡」→ 統一表述）
2. 保留差異化資訊（不同面向不應合併）
3. 每個輸出記憶必須使用完整表述（禁止代詞）
4. 維持時間順序（重要）

## 輸出格式（JSON陣列）
每個記憶單元包含：
- lossless_text: 整合後的完整表述
- keywords: 關鍵詞列表（3-5個）
- persons: 涉及的人名列表
- topic: 主題分類

## 輸出（JSON陣列）"""


class SynthesisStage:
    def __init__(
        self,
        model: str = "qwen3.5:2b",
        buffer_size: int = 5,
        keep_alive: int = 300,
        backend: Optional[LLMBackend] = None,
    ):
        self.model = model
        self.buffer_size = buffer_size
        self.buffer: List[MemoryUnit] = []
        self.keep_alive = keep_alive
        self.backend = backend

    def _get_backend(self) -> LLMBackend:
        return self.backend or get_llm_backend()

    def add(self, memory: MemoryUnit) -> None:
        self.buffer.append(memory)

    def should_synthesize(self) -> bool:
        return len(self.buffer) >= self.buffer_size

    def clear(self) -> List[MemoryUnit]:
        self.buffer.clear()
        return []

    async def process(self, memories: Optional[List[MemoryUnit]] = None) -> List[MemoryUnit]:
        if memories is None:
            memories = self.buffer
        
        if len(memories) < 2:
            return memories
        
        memories_text = "\n".join([
            f"- {m.lossless_text} (關鍵詞: {', '.join(m.keywords)})"
            for m in memories
        ])
        
        prompt = SYNTHESIS_PROMPT.format(memories=memories_text)
        backend = self._get_backend()
        
        try:
            response = await backend.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            
            content = response["message"]["content"].strip()
            
            if content.startswith("<think>"):
                content = content.split("</think>")[-1].strip()
            
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            data = json.loads(content)
            
            synthesized = []
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and "lossless_text" in item:
                    unit_data = item.get("memory_unit", item)
                    if isinstance(unit_data, dict) and "lossless_text" in unit_data:
                        if not isinstance(unit_data.get("persons"), list):
                            unit_data["persons"] = []
                        if not isinstance(unit_data.get("keywords"), list):
                            kw = unit_data.get("keywords", "")
                            unit_data["keywords"] = [kw] if kw else []
                        synthesized.append(MemoryUnit(**unit_data))
            
            return synthesized if synthesized else memories
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"Synthesis error: {e}, content: {content[:200]}")
            return memories

    async def synthesize_if_needed(self) -> List[MemoryUnit]:
        if not self.should_synthesize():
            return []
        
        result = await self.process()
        self.clear()
        return result
