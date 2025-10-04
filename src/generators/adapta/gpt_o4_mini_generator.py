"""Gerador de conteúdo usando o modelo O4-Mini via API Adapta.one."""

from typing import List, Optional, Dict
from pathlib import Path

from ..base import BaseContentGenerator
from .client import AdaptaClient
from config import settings


class GptO4MiniGenerator(BaseContentGenerator):
    """Gerador de conteúdo usando o modelo O4-Mini via Adapta.one."""
    
    def __init__(self, prompts_dir: Optional[Path] = None, cookies_str: Optional[str] = None,session_id: Optional[str] = None):
        super().__init__(prompts_dir)
        
        if cookies_str is None:
            cookies_str = settings.adapta_cookies_str

        if session_id is None:
            session_id = settings.adapta_session_id

        self.client = AdaptaClient(
            cookies_str=cookies_str,
            timeout=600.0,
            connect_timeout=120.0,
            read_timeout=600.0,
            session_id=session_id
        )
        self.model_name = "O4_MINI"
        self._client_initialized = False
    
    async def _ensure_client_initialized(self):
        if not self._client_initialized:
            await self.client._ensure_client()
            self._client_initialized = True
    
    async def summarize(self, text: str) -> str:
        try:
            await self._ensure_client_initialized()
            prompt = self._load_prompt("summarize")
            formatted_prompt = prompt.format(text=text)
            messages = [{"role": "user", "content": formatted_prompt}]
            result = await self.client.call_model(messages, self.model_name, new_line=True)
            if result is None:
                raise Exception("Falha ao gerar resumo com O4-Mini")
            return result
        except Exception as e:
            raise Exception(f"Erro ao gerar resumo com O4-Mini: {e}")
    
    async def diagram(self, text: str) -> str:
        try:
            await self._ensure_client_initialized()
            prompt = self._load_prompt("diagram")
            formatted_prompt = prompt.format(text=text)
            messages = [{"role": "user", "content": formatted_prompt}]
            result = await self.client.call_model(messages, self.model_name, new_line=True)
            if result is None:
                raise Exception("Falha ao gerar diagrama com O4-Mini")
            return result
        except Exception as e:
            raise Exception(f"Erro ao gerar diagrama com O4-Mini: {e}")
    
    async def create_mindmap(self, texts: List[str]) -> str:
        try:
            await self._ensure_client_initialized()
            prompt = self._load_prompt("mindmap")
            formatted_prompt = prompt.format(texts="\n\n".join(texts))
            messages = [{"role": "user", "content": formatted_prompt}]
            result = await self.client.call_model(messages, self.model_name, new_line=True)
            if result is None:
                raise Exception("Falha ao gerar mapa mental com O4-Mini")
            return result
        except Exception as e:
            raise Exception(f"Erro ao gerar mapa mental com O4-Mini: {e}")
    
    async def generate_content(self, prompt: str, text: str) -> str:
        try:
            await self._ensure_client_initialized()
            full_prompt = f"{prompt}\n\nTexto: {text}"
            messages = [{"role": "user", "content": full_prompt}]
            result = await self.client.call_model(messages, self.model_name, new_line=True)
            if result is None:
                raise Exception("Falha ao gerar conteúdo personalizado com O4-Mini")
            return result
        except Exception as e:
            raise Exception(f"Erro ao gerar conteúdo personalizado com O4-Mini: {e}")
    
    async def call_model_with_messages(self, messages: List[Dict[str, str]], searchType: Optional[str] = None, tool: Optional[str] = None, chat_id: Optional[str] = None) -> str:
        try:
            await self._ensure_client_initialized()
            result = await self.client.call_model(messages, self.model_name, new_line=True, searchType=searchType, tool=tool, chat_id=chat_id)
            if result is None:
                raise Exception("Falha ao chamar modelo O4-Mini com mensagens")
            return result
        except Exception as e:
            raise Exception(f"Erro ao chamar modelo O4-Mini com mensagens: {e}")
    
    async def health_check(self) -> bool:
        try:
            await self._ensure_client_initialized()
            return await self.client.health_check()
        except Exception:
            return False
    
    def get_supported_models(self) -> List[str]:
        return ["O4_MINI"]
    
    def get_provider_name(self) -> str:
        return "GptO4MiniGenerator"
