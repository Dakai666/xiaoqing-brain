import os
import re
import sys
import httpx
from typing import List, Optional
from abc import ABC, abstractmethod

#: MiniMax 的 embedding 模型（走 /v1/embeddings，不走 Ollama）
EMBED_MODEL_MINIMAX = "embo-01"

#: 各 backend 的預設 LLM 模型名
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"

#: Ollama 模型 tag 形式，例如 qwen3.5:9b、qwen3:8b
_OLLAMA_TAG = re.compile(r"^[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$")


def is_ollama_model(model: Optional[str]) -> bool:
    """判斷模型名看起來是不是 Ollama tag（名稱:tag）。"""
    return bool(model and _OLLAMA_TAG.match(model.strip()))


def resolve_llm_model(model: Optional[str], backend: str) -> str:
    """回傳與 backend 相容的模型名稱。

    模型名跟 backend 不符時自動改用該 backend 的預設模型。這是為了避免
    MiniMax API 收到 Ollama tag（或反過來）而回 HTTP 400 "unknown model"。
    """
    model = (model or "").strip()
    if backend == "minimax":
        if model and not is_ollama_model(model):
            return model
        if model:
            print(
                f"[llm_backend] 模型 '{model}' 是 Ollama tag，但目前走 MiniMax API，"
                f"自動改用 '{DEFAULT_MINIMAX_MODEL}'",
                flush=True,
                file=sys.stderr,
            )
        return DEFAULT_MINIMAX_MODEL

    # ollama
    if model and is_ollama_model(model):
        return model
    if model:
        print(
            f"[llm_backend] 模型 '{model}' 不是 Ollama tag，但目前走本機 Ollama，"
            f"自動改用 '{DEFAULT_OLLAMA_MODEL}'",
            flush=True,
            file=sys.stderr,
        )
    return DEFAULT_OLLAMA_MODEL


class LLMBackend(ABC):
    @abstractmethod
    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        pass

    @abstractmethod
    async def embeddings(self, model: str, prompt: str) -> dict:
        pass


class OllamaBackend(LLMBackend):
    def __init__(self, base_url: Optional[str] = None):
        env_url = os.environ.get("OLLAMA_BASE_URL")
        if env_url:
            self.base_url = env_url
        else:
            self.base_url = base_url or "http://127.0.0.1:11434"

    def _client(self):
        import ollama
        return ollama.Client(host=self.base_url)

    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        options = kwargs.get("options", {})
        keep_alive = kwargs.get("keep_alive", 300)

        client = self._client()
        response = client.chat(
            model=model,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
        )
        return response

    async def embeddings(self, model: str, prompt: str) -> dict:
        client = self._client()
        response = client.embeddings(model=model, prompt=prompt)
        return response


class MiniMaxBackend(LLMBackend):
    """MiniMax API client — uses Anthropic Messages API format.

    Endpoint: https://api.minimax.io/anthropic/v1/messages
    Auth: x-api-key header + anthropic-version
    Embeddings: Anthropic has no native embeddings API; falls back to Ollama
    if available, otherwise raises.
    """

    DEFAULT_BASE_URL = "https://api.minimax.io/anthropic"
    DEFAULT_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        anthropic_version: Optional[str] = None,
        embed_fallback: Optional[LLMBackend] = None,
    ):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
        self.base_url = (base_url or os.getenv("MINIMAX_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.anthropic_version = anthropic_version or os.getenv("MINIMAX_ANTHROPIC_VERSION", self.DEFAULT_VERSION)
        self.embed_fallback = embed_fallback or OllamaBackend()
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                    "content-type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    def _convert_messages(self, messages: List[dict]) -> tuple[Optional[str], List[dict]]:
        """Split OpenAI-style messages into (system, anthropic_messages)."""
        system_parts = []
        anthropic_msgs = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                anthropic_msgs.append({"role": "assistant", "content": content})
            else:
                anthropic_msgs.append({"role": "user", "content": content})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, anthropic_msgs

    async def chat(self, model: str, messages: List[dict], **kwargs) -> dict:
        client = self._get_client()
        system, anthropic_msgs = self._convert_messages(messages)

        options = kwargs.get("options", {})
        payload = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": anthropic_msgs,
            "temperature": options.get("temperature", 0.7),
        }
        if system:
            payload["system"] = system
        if "thinking" in options:
            payload["thinking"] = options["thinking"]

        response = await client.post("/v1/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        text_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return {
            "message": {
                "content": "".join(text_parts),
                "role": "assistant",
            },
            "stop_reason": data.get("stop_reason"),
            "usage": data.get("usage", {}),
            "raw": data,
        }

    async def embeddings(self, model: str, prompt: str) -> dict:
        """Embeddings — Anthropic Messages API 沒有 embedding 端點。

        MiniMax 自己的 embedding 模型（如 embo-01）走 MiniMax 的
        /v1/embeddings（注意參數是 texts 不是 input）；
        其他模型則委派給 fallback（Ollama）。
        """
        if model == EMBED_MODEL_MINIMAX or model.startswith("embo"):
            return await self._minimax_embeddings(model, prompt)
        return await self.embed_fallback.embeddings(model, prompt)

    async def _minimax_embeddings(self, model: str, prompt: str) -> dict:
        client = self._get_client()
        root = self.base_url
        for suffix in ("/anthropic",):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
        response = await client.post(
            f"{root}/v1/embeddings",
            json={"model": model, "texts": [prompt], "type": "db"},
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        vectors = data.get("vectors") or []
        if not vectors:
            raise RuntimeError(f"MiniMax embeddings 未回傳向量: {data}")
        return {"embedding": vectors[0]}

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


def configure_llm_backend(model: Optional[str] = None) -> tuple[LLMBackend, str]:
    """依環境設定 LLM backend 與模型，回傳 (backend, model)。

    有設 MINIMAX_API_KEY → MiniMax API；否則 → 本機 Ollama。
    模型名會依 backend 校正（見 :func:`resolve_llm_model`）。
    """
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if api_key:
        backend: LLMBackend = MiniMaxBackend(api_key)
        kind = "minimax"
    else:
        backend = OllamaBackend()
        kind = "ollama"
    set_llm_backend(backend)
    resolved = resolve_llm_model(model, kind)
    print(
        f"[llm_backend] backend={kind} model={resolved}",
        flush=True,
        file=sys.stderr,
    )
    return backend, resolved
