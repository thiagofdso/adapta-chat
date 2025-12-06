"""Base abstractions for generators backed by AdaptaClientV2."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, Iterable, List, Optional, Sequence, Tuple, Union
import secrets
import time
import uuid

from utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - used only for typing hints
    from generators_v2.adapta.client import AdaptaClientV2


class BaseContentGenerator:
    """Shared helpers for generators that rely exclusively on AdaptaClientV2."""

    DEFAULT_TOOLS: Dict[str, Sequence[str]] = {
        "normal": ("webSearch",),
        "scientific": ("webSearchScientific",),
        "deep_research": ("deepResearch",),
    }

    def __init__(
        self,
        *,
        model_name: str,
        client: Optional["AdaptaClientV2"] = None,
        prompts_dir: Optional[Path] = None,
    ) -> None:
        if prompts_dir is None:
            current_file = Path(__file__)
            prompts_dir = current_file.parent.parent / "prompts"

        self.prompts_dir = Path(prompts_dir)
        self._validate_prompts_directory()

        if client is None:
            from .adapta.client import AdaptaClientV2  # Local import to avoid circular dependency

            self.client = AdaptaClientV2()
        else:
            self.client = client
        self.model_name = model_name

    # ------------------------------------------------------------------
    # Public high-level actions
    # ------------------------------------------------------------------
    async def summarize(self, text: str) -> str:
        prompt = self._load_prompt("summarize").format(text=text)
        return await self._call_with_prompt(prompt)

    async def diagram(self, text: str) -> str:
        prompt = self._load_prompt("diagram").format(text=text)
        return await self._call_with_prompt(prompt)

    async def create_mindmap(self, texts: List[str]) -> str:
        prompt = self._load_prompt("mindmap").format(texts="\n\n".join(texts))
        return await self._call_with_prompt(prompt)

    async def preprocess_mindmap(self, texts: List[str]) -> str:
        prompt = self._load_prompt("preprocess_mindmap").format(texts="\n\n".join(texts))
        return await self._call_with_prompt(prompt)

    async def generate_content(self, prompt: str, text: str) -> str:
        combined = f"{prompt}\n\nTexto: {text}"
        return await self._call_with_prompt(combined)

    async def call_model_with_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        chat_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[Iterable[str]] = None,
        stream: bool = False,
        ignore_thoughts: Optional[bool] = None,
        search_mode: Optional[str] = None,
    ) -> Union[str, AsyncGenerator[Tuple[str, str], None]]:
        """Delegates the supplied conversation to the AdaptaClientV2."""
        if not messages:
            raise ValueError("messages deve conter pelo menos um item para chamar o modelo.")

        payload_messages = [dict(message) for message in messages]
        payload_files = self._normalize_files(files)
        payload_tools = self._normalize_tools(search_mode, tools)

        result = await self.client.call_model(
            prompt=None,
            messages=payload_messages,
            model=self.model_name,
            files=payload_files,
            tools=payload_tools or None,
            chat_id=chat_id,
            isStream=stream,
            ignore_thoughts=ignore_thoughts,
        )
        if stream:
            return result

        return self._extract_answer_text(result)

    async def call_message_openai(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        """Wrapper que espelha o contrato da API OpenAI usando o cliente Adapta."""
        if not messages:
            raise ValueError("messages deve conter pelo menos um item no formato OpenAI.")

        selected_model = model or self.model_name
        return await self.client.call_message_openai(
            messages=messages,
            model=selected_model,
            stream=stream,
            **kwargs,
        )

    async def health_check(self) -> bool:
        candidate = getattr(self.client, "health_check", None)
        if callable(candidate):
            return await candidate()

        ensure_client = getattr(self.client, "_ensure_client", None)
        ensure_auth = getattr(self.client, "_ensure_authenticated", None)
        simulate_login = getattr(self.client, "simulate_login", None)

        try:
            if callable(ensure_client):
                await ensure_client()
            if callable(ensure_auth):
                await ensure_auth()
            elif callable(simulate_login):
                await simulate_login()
            return True
        except Exception as exc:
            logger.error("Health check failed for {}: {}", self.get_provider_name(), exc)
            return False

    def get_supported_models(self) -> List[str]:
        return [self.model_name]

    def get_provider_name(self) -> str:
        return self.__class__.__name__

    def generate_chat_id(self) -> str:
        """Gera um identificador compatível com UUIDv7 para ordenação temporal."""
        uuid7_factory = getattr(uuid, "uuid7", None)
        if callable(uuid7_factory):
            return str(uuid7_factory())

        timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
        rand_a = secrets.randbits(12)
        rand_b = secrets.randbits(62)

        uuid_int = (timestamp_ms << 80)
        uuid_int |= 0x7 << 76
        uuid_int |= rand_a << 64
        uuid_int |= 0x2 << 62
        uuid_int |= rand_b

        return str(uuid.UUID(int=uuid_int))

    # ------------------------------------------------------------------
    # Helper routines
    # ------------------------------------------------------------------
    async def _call_with_prompt(
        self,
        prompt: str,
        *,
        chat_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[Iterable[str]] = None,
        stream: bool = False,
        ignore_thoughts: Optional[bool] = None,
        search_mode: Optional[str] = None,
    ) -> Union[str, AsyncGenerator[Tuple[str, str], None]]:
        messages = [{"role": "user", "content": prompt}]
        return await self.call_model_with_messages(
            messages,
            chat_id=chat_id,
            files=files,
            tools=tools,
            stream=stream,
            ignore_thoughts=ignore_thoughts,
            search_mode=search_mode,
        )

    def _normalize_tools(
        self,
        search_mode: Optional[str],
        tools: Optional[Iterable[str]],
    ) -> List[str]:
        ordered: List[str] = []

        if search_mode:
            mapped = self.DEFAULT_TOOLS.get(search_mode, (search_mode,))
            ordered.extend(mapped if isinstance(mapped, (list, tuple)) else (mapped,))

        if tools:
            if isinstance(tools, str):
                ordered.append(tools)
            else:
                ordered.extend(str(tool) for tool in tools if tool)

        normalized: List[str] = []
        seen: set[str] = set()
        for item in ordered:
            if not item:
                continue
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    def _normalize_files(
        self,
        files: Optional[Sequence[Dict[str, Any]]],
    ) -> Optional[List[Dict[str, Any]]]:
        if not files:
            return None

        normalized: List[Dict[str, Any]] = []
        for file_info in files:
            if not isinstance(file_info, dict):
                logger.warning("Ignorando arquivo anexado com formato inválido: {}", file_info)
                continue
            normalized.append(file_info)

        return normalized or None

    def _extract_answer_text(self, result: Any) -> str:
        if result is None:
            raise RuntimeError("Resposta vazia retornada pelo cliente Adapta.")

        if isinstance(result, str):
            return result

        messages = getattr(result, "messages", None)
        if isinstance(messages, list):
            answers = [
                entry.get("text", "")
                for entry in messages
                if isinstance(entry, dict) and entry.get("kind") == "answer"
            ]
            if any(chunk.strip() for chunk in answers):
                return "".join(answers)

            fallbacks = [
                entry.get("text", "")
                for entry in messages
                if isinstance(entry, dict) and entry.get("text")
            ]
            if fallbacks:
                return "".join(fallbacks)

        return str(result)

    def _validate_prompts_directory(self) -> None:
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Diretório de prompts não encontrado: {self.prompts_dir}")

    def _load_prompt(self, prompt_name: str) -> str:
        prompt_file = self.prompts_dir / f"{prompt_name}.txt"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Arquivo de prompt não encontrado: {prompt_file}")
        return prompt_file.read_text(encoding="utf-8")
