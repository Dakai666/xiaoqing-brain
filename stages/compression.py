import json
from typing import List, Optional
from ..models.memory_unit import MemoryUnit
from ..utils.llm_backend import get_llm_backend, LLMBackend


COMPRESSION_PROMPT = """從對話中提取值得保存的資訊，轉換為 JSON 格式的記憶單元。

每個記憶單元包含：
- lossless_text: 完整、無歧義的表述
- keywords: 關鍵詞列表
- persons: 涉及的人名
- topic: 主題分類

對話：{input}

JSON 輸出："""


class CompressionStage:
    def __init__(
        self,
        model: str = "qwen3.5:2b",
        keep_alive: int = 300,
        backend: Optional[LLMBackend] = None,
    ):
        self.model = model
        self.keep_alive = keep_alive
        self.backend = backend

    def _get_backend(self) -> LLMBackend:
        return self.backend or get_llm_backend()

    async def process(self, input_text: str) -> List[MemoryUnit]:
        prompt = COMPRESSION_PROMPT.format(input=input_text)
        backend = self._get_backend()
        
        response = await backend.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        
        content = response["message"]["content"]
        
        try:
            content = content.strip()
            
            if content.startswith("<think>"):
                content = content.split("</think>")[-1].strip()
            
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            # Handle various JSON wrappers
            data = json.loads(content)
            
            # Unwrap common wrappers
            if isinstance(data, dict):
                if "memory_units" in data:
                    data = data["memory_units"]
                elif "memory_unit" in data:
                    data = data["memory_unit"]
                elif "data" in data:
                    data = data["data"]
            
            memories = []
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    unit_data = item.get("memory_unit", item)
                    if isinstance(unit_data, dict) and "lossless_text" in unit_data:
                        if not isinstance(unit_data.get("persons"), list):
                            unit_data["persons"] = []
                        if not isinstance(unit_data.get("keywords"), list):
                            kw = unit_data.get("keywords", "")
                            unit_data["keywords"] = [kw] if kw else []
                        memories.append(MemoryUnit(**unit_data))
            return memories
        except (json.JSONDecodeError, Exception) as e:
            print(f"Parse error: {e}, content: {content[:200]}")
            return []
