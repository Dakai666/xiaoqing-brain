import os
import httpx
import json
from typing import List, Optional
from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        pass
    
    @abstractmethod
    async def embeddings(self, model: str, prompt: str) -> dict:
        pass


class OllamaBackend(LLMBackend):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
    
    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        import ollama
        options = kwargs.get("options", {})
        keep_alive = kwargs.get("keep_alive", 300)
        
        response = ollama.chat(
            model=model,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
        )
        return response
    
    async def embeddings(self, model: str, prompt: str) -> dict:
        import ollama
        response = ollama.embeddings(model=model, prompt=prompt)
        return response


class MiniMaxBackend(LLMBackend):
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.minimax.io/v1"):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
        self.base_url = base_url
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client
    
    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        client = self._get_client()
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("options", {}).get("temperature", 0.7),
            "thinking": {"type": "disabled"},
        }
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        return {
            "message": {
                "content": data["choices"][0]["message"]["content"]
            }
        }
    
    async def embeddings(self, model: str, prompt: str) -> dict:
        client = self._get_client()
        
        payload = {
            "model": model,
            "texts": [prompt],
            "type": "db_compute",
        }
        
        response = await client.post("/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()
        
        if "vectors" in data and data["vectors"]:
            return {"embedding": data["vectors"][0]}
        
        raise ValueError(f"Unexpected embeddings response: {data}")
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


_llm_backend: Optional[LLMBackend] = None


def set_llm_backend(backend: LLMBackend):
    global _llm_backend
    _llm_backend = backend


def get_llm_backend() -> LLMBackend:
    global _llm_backend
    if _llm_backend is None:
        api_key = os.getenv("MINIMAX_API_KEY", "")
        if api_key:
            _llm_backend = MiniMaxBackend(api_key)
        else:
            _llm_backend = OllamaBackend()
    return _llm_backend
