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
    async def embeddings(self, model: str, prompt: str, **kwargs) -> dict:
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
        options = dict(kwargs.get("options") or {})
        keep_alive = kwargs.get("keep_alive", 300)

        # 2026-11-15：本機 chat 一定要明給 num_ctx。
        # 預設 40960 會吃掉大量 VRAM（KV cache），在顯存被 ComfyUI 佔用時
        # Ollama 會回空內容（content=""）→ 上層 JSON 解析失敗、記憶靜默丟失。
        # 記憶壓縮的 prompt 約 1.5-4k token，8192 綽綽有餘。
        try:
            num_ctx = int(os.environ.get("XIAOQING_CHAT_NUM_CTX", "8192"))
        except ValueError:
            num_ctx = 8192
        options.setdefault("num_ctx", num_ctx)

        client = self._client()
        # 預設關掉 thinking：qwen3.5 的思考段很容易吃掉整個 num_ctx，
        # 導致 content 是空字串（記憶因此靜默丟失）。記憶抽取不需要長思考。
        # 想開回來：XIAOQING_CHAT_THINK=1
        use_think = os.environ.get("XIAOQING_CHAT_THINK") == "1"

        def _chat():
            kwargs = {
                "model": model,
                "messages": messages,
                "options": options,
                "keep_alive": keep_alive,
            }
            if not use_think:
                kwargs["think"] = False
            try:
                return client.chat(**kwargs)
            except TypeError:
                # 舊版 ollama client 不支援 think 參數
                kwargs.pop("think", None)
                return client.chat(**kwargs)

        response = _chat()
        # 空回應重試一次（第一次常常是模型剛換入、KV cache 還沒就緒）
        if not (response.get("message") or {}).get("content", "").strip():
            print(
                "[llm_backend] 本機模型回空內容，重試一次（num_ctx=%s）" % num_ctx,
                flush=True,
                file=sys.stderr,
            )
            response = _chat()
        return response

    async def embeddings(self, model: str, prompt: str, **kwargs) -> dict:
        """向 Ollama 請求 embedding。

        `options` 可透傳給 llama.cpp（例如 `{"num_ctx": 2048}`）。
        embedding 是短文字輸入，預設 40960 的 context 只會白吃 ~5.5 GB VRAM，
        而輸出向量逐位元相同。`keep_alive` 控制模型在請求後保留多久（秒）；
        不傳則由伺服器端 OLLAMA_KEEP_ALIVE 決定。
        """
        client = self._client()
        payload = {"model": model, "prompt": prompt}
        if kwargs.get("options") is not None:
            payload["options"] = kwargs["options"]
        if kwargs.get("keep_alive") is not None:
            payload["keep_alive"] = kwargs["keep_alive"]
        response = client.embeddings(**payload)
        return response


class MiniMaxBackend(LLMBackend):
    """MiniMax API client — uses Anthropic Messages API format.

    Endpoint: https://api.minimax.io/anthropic/v1/messages
    Auth: x-api-key header + anthropic-version
    Embeddings: Anthropic has no native embeddings API; falls back to Ollama
    if available, otherwise raises.

    2026-11-15 新增：**額度用完自動降級到本機 Ollama**。
    主人按方案有週上限，額度一爆整個記憶系統就停擺（HTTP 429），
    所以 chat() 遇到 429/5xx 時改走本機模型，並在 stderr 留下紀錄。
    關掉：`XIAOQING_LOCAL_FALLBACK=0`。
    """

    DEFAULT_BASE_URL = "https://api.minimax.io/anthropic"
    DEFAULT_VERSION = "2023-06-01"

    #: 這些狀態碼代表「不是內容問題，是額度或服務問題」→ 值得改走本機
    FALLBACK_STATUS = {429, 500, 502, 503, 504, 529}

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        anthropic_version: Optional[str] = None,
        embed_fallback: Optional[LLMBackend] = None,
        chat_fallback: Optional[LLMBackend] = None,
    ):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
        self.base_url = (base_url or os.getenv("MINIMAX_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.anthropic_version = anthropic_version or os.getenv("MINIMAX_ANTHROPIC_VERSION", self.DEFAULT_VERSION)
        self.embed_fallback = embed_fallback or OllamaBackend()
        self.chat_fallback = chat_fallback or OllamaBackend()
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

        try:
            response = await client.post("/v1/messages", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if (
                e.response is not None
                and e.response.status_code in self.FALLBACK_STATUS
                and os.getenv("XIAOQING_LOCAL_FALLBACK", "1") != "0"
            ):
                # 額度爆了／API 掛了 → 改走本機 Ollama，記憶功能不要因此停擺
                local_model = resolve_llm_model(None, "ollama")
                print(
                    f"[llm_backend] MiniMax 回應 HTTP {e.response.status_code}，"
                    f"自動降級到本機 Ollama（{local_model}）",
                    flush=True,
                    file=sys.stderr,
                )
                return await self.chat_fallback.chat(local_model, messages, **kwargs)
            raise
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

    async def embeddings(self, model: str, prompt: str, **kwargs) -> dict:
        """Embeddings — Anthropic Messages API 沒有 embedding 端點。

        MiniMax 自己的 embedding 模型（如 embo-01）走 MiniMax 的
        /v1/embeddings（注意參數是 texts 不是 input）；
        其他模型則委派給 fallback（Ollama）。
        """
        if model == EMBED_MODEL_MINIMAX or model.startswith("embo"):
            return await self._minimax_embeddings(model, prompt)
        return await self.embed_fallback.embeddings(model, prompt, **kwargs)

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
