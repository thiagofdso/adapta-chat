"""Cliente experimental para validar o novo fluxo de autenticacao e chamadas do Adapta."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import secrets
from datetime import datetime
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple, Union

import httpx

from config import settings
from utils.logger import logger

AGENT_BASE_URL = "https://agent.adapta.one"
API_AGENT_BASE_URL = "https://api-agent.adapta.one"
CLERK_BASE_URL = "https://clerk.agent.adapta.one/v1"
CLERK_API_VERSION = "2025-04-10"
CLERK_JS_VERSION = "5.103.1"
DEFAULT_MODEL = "CLAUDE_4_5_SONNET"

FILE_API_BASE = f"{AGENT_BASE_URL}/api/file"
FILE_UPLOAD_V2_ENDPOINT = f"{API_AGENT_BASE_URL}/api/file/upload"
FILES_LIST_ENDPOINT = f"{AGENT_BASE_URL}/api/files/list/v1"
FILES_DELETE_ENDPOINT = f"{AGENT_BASE_URL}/api/files/delete/v1"
AMPLITUDE_ENDPOINT = "https://api2.amplitude.com/2/httpapi"
AMPLITUDE_API_KEY = "1df174dbd145cff0b8b3a0a1e768bdf7"

FORMATOS_ACEITOS = {
    ".txt",
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
}

FORMATOS_MIME = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

def _generate_uuid7_like() -> str:
    """Gera um UUID v7 (ou modelo compatível quando não suportado pela stdlib)."""
    generator = getattr(uuid, "uuid7", None)
    if callable(generator):
        return str(generator())

    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)

    uuid_int = (timestamp_ms << 80)  # 48 bits de timestamp
    uuid_int |= 0x7 << 76           # versão 7
    uuid_int |= rand_a << 64        # 12 bits adicionais
    uuid_int |= 0x2 << 62           # variant '10'
    uuid_int |= rand_b              # 62 bits finais

    return str(uuid.UUID(int=uuid_int))


@dataclass
class AuthResult:
    """Representa o resultado da autenticacao simulada."""

    session_id: str
    cookies: Dict[str, str]


@dataclass
class ChatCompletionResult:
    """Representa o resultado agregado de uma chamada ao chat."""

    messages: List[Dict[str, str]]


class AdaptaClientV2:
    """Cliente mínimo para validar login, upload de arquivos e chamadas de IA."""

    def __init__(
        self,
        login: Optional[str] = None,
        password: Optional[str] = None,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.login = login or settings.adapta_login
        self.password = password or settings.adapta_password

        if not self.login or not self.password:
            raise ValueError("ADAPTA_LOGIN e ADAPTA_PASSWORD sao obrigatorios.")

        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_id: Optional[str] = None
        self._auth_cookies: Dict[str, str] = {}
        self._bearer_token: Optional[str] = None
        self._bearer_token_exp: float = 0.0
        self._auth_lock = asyncio.Lock()
        self._last_thought: Optional[str] = None
        self._last_chat_id: Optional[str] = None

    async def __aenter__(self) -> "AdaptaClientV2":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def last_chat_id(self) -> Optional[str]:
        return self._last_chat_id

    @property
    def last_thought(self) -> Optional[str]:
        return self._last_thought

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._client_loop = None

    async def simulate_login(self) -> AuthResult:
        """Executa o fluxo mínimo necessário para autenticar o usuário."""
        async with self._auth_lock:
            client = await self._ensure_client()

            await self._fetch_sign_in_page(client)
            await self._start_sign_in_attempt(client)
            payload = await self._complete_password_sign_in(client)

            self._session_id = self._extract_session_id(payload)
            if not self._session_id:
                raise RuntimeError("Nao foi possivel identificar o session_id retornado pela API.")

            await self._touch_session(client, self._session_id)

            cookies = self._collect_auth_cookies(client)
            if cookies:
                client.cookies.update(cookies)
            self._auth_cookies = cookies
            missing = {"__client", "__client_uat", "clerk_active_context"} - set(cookies)
            if missing:
                logger.warning("Cookies esperados nao encontrados: {}", ", ".join(sorted(missing)))

            logger.info("Login concluído com session_id={}", self._session_id)
            return AuthResult(session_id=self._session_id, cookies=cookies)

    async def call_model(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        *,
        model: str = DEFAULT_MODEL,
        files: Optional[List[Dict[str, Any]]] = None,
        ignore_thoughts: Optional[bool] = None,
        tools: Optional[List[str]] = None,
        chat_id: Optional[str] = None,
        isStream: bool = False,
        **kwargs: Any,
    ) -> Union[ChatCompletionResult, AsyncGenerator[Tuple[str, str], None]]:
        """Executa uma chamada ao modelo nos modos agregado ou streaming.

        Quando `isStream=True`, retorna um gerador async emitindo eventos
        incrementais (thought, answer, answer_end). Caso contrário, agrega a
        resposta e devolve um `ChatCompletionResult`. Utilize
        `ignore_thoughts=True` (ou `ignoreThoughts=True`) para ocultar
        pensamentos no modo agregado. Utilize `tools` para indicar ferramentas
        adicionais (cada item deve ser um dos valores aceitos pelo backend):

            🔍 webSearch, webScrape, webCrawl, webSearchScientific, deepResearch
            📄 documentGenerate, ragQuery, fullAnalysis
            📊 analyzeSheet, generateSheet, tableFormatter
            🎨 generateImage, editImage, analyzeImages, chartGeneration, generateDiagram
            🎤 generatePPT, editPPT

        Informe `messages` para enviar o histórico completo no formato aceito
        pelo `BaseContentGenerator` (lista de dicionários com `role`, `content`
        ou `parts`). Se omitido, preencha `prompt` com a mensagem única.
        Passe `chat_id` quando quiser reutilizar um identificador específico;
        caso não seja informado, um UUID v7 é gerado automaticamente.
        """
        if "ignoreThoughts" in kwargs:
            ignore_thoughts = kwargs.pop("ignoreThoughts")
        if kwargs:
            unexpected = ", ".join(kwargs.keys())
            raise TypeError(f"call_model() recebeu argumentos inesperados: {unexpected}")

        if prompt is None and not messages:
            raise ValueError("call_model() requer `prompt` ou `messages`.")

        history_messages = messages

        if isStream:
            async def stream_generator() -> AsyncGenerator[Tuple[str, str], None]:
                async for event_type, payload in self._chat_event_stream(
                    prompt,
                    messages=history_messages,
                    model=model,
                    files=files,
                    include_tool_events=True,
                    tools=tools,
                    chat_id=chat_id,
                ):
                    if event_type in {"thought", "answer", "answer_end"}:
                        yield (event_type, payload)

            return stream_generator()

        if ignore_thoughts is None:
            ignore_thoughts = True

        collected_messages: List[Dict[str, str]] = []
        current_answer_chunks: List[str] = []

        async for event_type, payload in self._chat_event_stream(
            prompt,
            messages=history_messages,
            model=model,
            files=files,
            include_tool_events=True,
            tools=tools,
            chat_id=chat_id,
        ):
            if event_type == "answer":
                current_answer_chunks.append(payload)
                continue

            if event_type == "answer_end":
                if current_answer_chunks:
                    answer_text = "".join(current_answer_chunks)
                    collected_messages.append({"kind": "answer", "text": answer_text})
                    current_answer_chunks = []
                continue

            if event_type == "thought" and not ignore_thoughts:
                collected_messages.append({"kind": "thought", "text": payload})

        if current_answer_chunks:
            answer_text = "".join(current_answer_chunks)
            collected_messages.append({"kind": "answer", "text": answer_text})

        return ChatCompletionResult(messages=collected_messages)

    async def call_message_openai(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        stream: bool = False,
        files: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[str]] = None,
        **_: Any,
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        """Recebe mensagens no formato da API OpenAI e retorna no mesmo padr��o.

        Campos ausentes (tokens, logprobs etc.) s��o preenchidos com valores
        simulados para manter compatibilidade com o contrato esperado.
        """
        if not messages:
            raise ValueError("call_message_openai requer a lista `messages` no formato da OpenAI.")

        selected_model = model or DEFAULT_MODEL
        normalized_messages = self._convert_openai_messages(messages)

        if stream:
            raw_stream = await self.call_model(
                prompt=None,
                messages=normalized_messages,
                model=selected_model,
                files=files,
                tools=tools,
                isStream=True,
                ignore_thoughts=True,
            )
            completion_id = f"chatcmpl-{uuid.uuid4().hex}"
            created = int(time.time())

            async def _openai_stream_wrapper() -> AsyncGenerator[Dict[str, Any], None]:
                async for event_type, payload in raw_stream:
                    if event_type != "answer" and event_type != "answer_end":
                        continue
                    finish_reason = "stop" if event_type == "answer_end" else None
                    delta_content = "" if event_type == "answer_end" else payload
                    yield {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": selected_model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": delta_content} if delta_content else {},
                                "logprobs": None,
                                "finish_reason": finish_reason,
                            }
                        ],
                    }

            return _openai_stream_wrapper()

        chat_result = await self.call_model(
            prompt=None,
            messages=normalized_messages,
            model=selected_model,
            files=files,
            tools=tools,
            isStream=False,
            ignore_thoughts=True,
        )
        answer_text = self._extract_answer_text(chat_result)
        return self._build_openai_response(answer_text, selected_model)

    async def _get_conversations(
        self,
        chat_id: str,
        *,
        page: int = 1,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        """Retorna o hist��rico de mensagens de um chat espec��fico."""
        if not chat_id:
            raise ValueError("chat_id �� obrigatorio para recuperar conversas.")

        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        url = f"{AGENT_BASE_URL}/api/chat/{chat_id}/v1"
        headers = {
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/agentic-chat/{chat_id}",
        }
        params = {"page": page, "limit": limit}

        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()

        payload = response.json() or {}
        data = payload.get("data") or {}
        messages = data.get("messages") or []
        if not isinstance(messages, list):
            logger.warning("Resposta inesperada ao consultar conversas: {}", payload)
            return []
        return messages

    async def _delete_conversations(self, chat_ids: List[str]) -> Dict[str, Any]:
        """Remove chats na plataforma Adapta.one."""
        if not chat_ids:
            return {"success": True, "data": None, "details": {"message": "Nenhum chatId informado."}}

        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()
        logger.debug("Solicitando exclusão de {} chats.", len(chat_ids))

        response = await client.request(
            "DELETE",
            f"{AGENT_BASE_URL}/api/chat/delete/v1",
            headers={
                "accept": "*/*",
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "origin": AGENT_BASE_URL,
                "referer": f"{AGENT_BASE_URL}/agentic-chat",
            },
            json={"chatIds": chat_ids},
        )
        response.raise_for_status()
        payload = response.json()
        logger.debug("Resposta da exclusão de chats: {}", payload)
        return payload

    async def excluir_chat(self, chat_ids: Union[str, List[str]]) -> Dict[str, Any]:
        """Remove um ou mais chats, espelhando o endpoint /api/chat/delete/v1."""
        if isinstance(chat_ids, str):
            chat_ids = [chat_ids]
        elif not isinstance(chat_ids, list):
            raise TypeError("excluir_chat aceita uma string ou lista de strings.")

        normalized = [cid for cid in (chat_ids or []) if cid]
        return await self._delete_conversations(normalized)

    async def upload_arquivo(self, caminho_arquivo: str) -> Dict[str, Any]:
        """Realiza upload do arquivo e retorna metadados compatíveis com a API."""
        file_path = Path(caminho_arquivo)
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")

        extensao = file_path.suffix.lower()
        if extensao not in FORMATOS_ACEITOS:
            raise ValueError(
                f"Formato de arquivo não suportado: {extensao}. "
                f"Formatos aceitos: {', '.join(sorted(FORMATOS_ACEITOS))}"
            )

        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        tamanho_bytes = file_path.stat().st_size
        mime_type = FORMATOS_MIME.get(extensao, "application/octet-stream")
        file_bytes = file_path.read_bytes()

        headers = {
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/",
        }

        files = {
            "file": (file_path.name, file_bytes, mime_type),
        }

        response = await client.post(
            FILE_UPLOAD_V2_ENDPOINT,
            headers=headers,
            files=files,
        )
        response.raise_for_status()
        payload = response.json()
        raw_data = payload.get("data")

        if isinstance(raw_data, dict):
            upload_info = raw_data
        elif isinstance(raw_data, list) and raw_data:
            upload_info = raw_data[0]
        else:
            raise RuntimeError(f"Resposta inesperada do endpoint de upload: {payload}")

        # Alguns endpoints devolvem {"files": [ { ... } ], "currentStorage": ...}
        # nesse caso devemos desembrulhar o primeiro item da lista.
        if isinstance(upload_info, dict) and "files" in upload_info and isinstance(upload_info["files"], list):
            if upload_info["files"]:
                upload_info = upload_info["files"][0]
            else:
                raise RuntimeError(f"Lista de arquivos vazia no payload de upload: {payload}")

        if not isinstance(upload_info, dict):
            raise RuntimeError(f"Formato invalido nos dados de upload: {upload_info}")

        filename = upload_info.get("fileName") or file_path.name
        url = upload_info.get("signedUrl") or upload_info.get("url")
        if not url:
            raise RuntimeError(f"URL assinada nao retornada pelo endpoint: {upload_info}")

        size = (
            upload_info.get("fileSizeInBytes")
            or upload_info.get("sizeInBytes")
            or upload_info.get("size")
            or tamanho_bytes
        )
        media_type = (
            upload_info.get("fileMimeType")
            or upload_info.get("mimeType")
            or upload_info.get("mediaType")
            or mime_type
        )
        path = (
            upload_info.get("filePathOnStorage")
            or upload_info.get("path")
            or upload_info.get("fileKey")
            or file_path.name
        )

        return {
            "filename": filename,
            "url": url,
            "size": size,
            "mediaType": media_type,
            "path": path,
        }

    async def list_files(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recupera os arquivos disponiveis para o usuario autenticado.

        Retorna um dicionario com os campos:
            - files: lista normalizada de arquivos (filename, path, signed_url, size, mime_type, raw).
            - pagination: informacoes de paginacao quando fornecidas pelo backend.
            - raw: payload completo retornado pela API.
        """
        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        params: Dict[str, Any] = {"limit": max(1, limit)}
        if offset:
            params["offset"] = max(0, offset)
        if search:
            params["search"] = search

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {token}",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/agentic-chat",
        }

        response = await client.get(FILES_LIST_ENDPOINT, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()

        files, pagination = self._extract_files_payload(payload)
        return {
            "files": files,
            "pagination": pagination,
            "raw": payload,
        }

    async def download_file(
        self,
        file_reference: Union[str, Dict[str, Any]],
        destination: Union[str, Path],
        *,
        chunk_size: int = 1024 * 128,
        ensure_parent: bool = True,
    ) -> Path:
        """Baixa um arquivo utilizando a URL assinada retornada pela API.

        O `file_reference` pode ser um caminho remoto (path) ou um dicionario
        contendo os metadados normalizados retornados por `list_files()`.
        """
        file_info = await self._resolve_file_reference(file_reference)
        signed_url = (
            file_info.get("signed_url")
            or file_info.get("signedUrl")
            or file_info.get("url")
        )
        if not signed_url:
            raise RuntimeError("Nao foi possivel localizar a URL assinada do arquivo.")

        filename = file_info.get("filename") or Path(file_info.get("path", "")).name
        if not filename:
            raise RuntimeError("Nao foi possivel determinar o nome do arquivo para download.")

        destination_path = Path(destination)
        if destination_path.is_dir() or destination_path.suffix == "":
            destination_path = destination_path / filename
        if ensure_parent:
            destination_path.parent.mkdir(parents=True, exist_ok=True)

        client = await self._ensure_client()
        async with client.stream("GET", signed_url) as response:
            response.raise_for_status()
            with destination_path.open("wb") as file_handle:
                async for chunk in response.aiter_bytes(chunk_size):
                    if chunk:
                        file_handle.write(chunk)

        return destination_path

    async def excluir_arquivos(self, files_paths: List[str]) -> Dict[str, Any]:
        """Remove arquivos informados pela lista de caminhos no storage."""
        if not files_paths:
            return {
                "success": True,
                "details": {"message": "Nenhum arquivo informado para exclusao."},
            }

        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        headers = {
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/agentic-chat",
        }
        response = await client.request(
            "DELETE",
            FILES_DELETE_ENDPOINT,
            headers=headers,
            json={"filesPaths": files_paths},
        )
        response.raise_for_status()
        return response.json()

    async def excluir_arquivo(self, file_path: str) -> Dict[str, Any]:
        """Atalho para excluir um unico arquivo."""
        return await self.excluir_arquivos([file_path])

    def _extract_files_payload(self, payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Normaliza o payload de listagem de arquivos retornado pela API."""
        if not isinstance(payload, dict):
            return ([], {})

        data_section: Any = payload
        pagination: Dict[str, Any] = {}

        nested_data = payload.get("data")
        if isinstance(nested_data, dict):
            data_section = nested_data
        elif isinstance(nested_data, list):
            data_section = nested_data

        if isinstance(data_section, dict):
            pagination_candidate = data_section.get("pagination")
            if isinstance(pagination_candidate, dict):
                pagination = pagination_candidate

            for key in ("data", "files", "items", "results"):
                candidate = data_section.get(key)
                if isinstance(candidate, list):
                    data_section = candidate
                    break

        items: List[Dict[str, Any]] = data_section if isinstance(data_section, list) else []
        normalized = [self._normalize_file_entry(item) for item in items if isinstance(item, dict)]
        return (normalized, pagination)

    def _normalize_file_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Padroniza os campos retornados pela API para facilitar o consumo."""
        path_value = (
            item.get("path")
            or item.get("filePath")
            or item.get("filePathOnStorage")
            or item.get("file_path")
        )
        filename = item.get("filename") or item.get("fileName")
        if not filename and path_value:
            filename = Path(path_value).name

        return {
            "id": item.get("id"),
            "filename": filename,
            "path": path_value,
            "signed_url": item.get("signedUrl") or item.get("signed_url") or item.get("url"),
            "size": item.get("size") or item.get("fileSizeInBytes") or item.get("file_size"),
            "mime_type": item.get("mediaType") or item.get("fileMimeType") or item.get("mimeType"),
            "created_at": item.get("createdAt"),
            "updated_at": item.get("updatedAt") or item.get("lastModified"),
            "raw": item,
        }

    async def _resolve_file_reference(
        self,
        reference: Union[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Encontra os metadados completos do arquivo a partir de path ou dict."""
        if isinstance(reference, dict):
            return reference

        file_path = reference
        filename_hint = Path(file_path).name if file_path else None

        search_term = filename_hint or file_path
        result = await self.list_files(limit=50, search=search_term)
        files: List[Dict[str, Any]] = result.get("files", [])

        for candidate in files:
            if candidate.get("path") == file_path:
                return candidate
            raw = candidate.get("raw", {})
            raw_path = (
                raw.get("filePathOnStorage")
                or raw.get("path")
                or raw.get("filePath")
            )
            if raw_path == file_path:
                return candidate

        if filename_hint:
            for candidate in files:
                if candidate.get("filename") == filename_hint:
                    return candidate

        raise FileNotFoundError(f"Arquivo nao encontrado: {file_path}")

    async def _ensure_client(self) -> httpx.AsyncClient:
        current_loop = asyncio.get_running_loop()
        if self._client is not None:
            if self._client.is_closed or self._client_loop is None or self._client_loop is not current_loop:
                await self._client.aclose()
                self._client = None
                self._client_loop = None

        if self._client is None:
            timeout = httpx.Timeout(timeout=1200.0, connect=15.0, read=1200.0)
            headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
                "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "origin": AGENT_BASE_URL,
            }
            self._client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                transport=self._transport,
            )
            self._client_loop = current_loop

        return self._client

    async def _fetch_sign_in_page(self, client: httpx.AsyncClient) -> None:
        url = f"{AGENT_BASE_URL}/sign-in"
        logger.debug("Buscando pagina de login: {}", url)
        response = await client.get(
            url,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "referer": f"{AGENT_BASE_URL}/",
            },
        )
        response.raise_for_status()

    async def _start_sign_in_attempt(self, client: httpx.AsyncClient) -> None:
        url = f"{CLERK_BASE_URL}/client/sign_ins"
        logger.debug("Iniciando tentativa de login (passkey) em {}", url)
        response = await client.post(
            url,
            params=self._clerk_params(),
            data={
                "locale": "pt-BR",
                "strategy": "passkey",
            },
            headers=self._form_headers(),
        )
        response.raise_for_status()

    async def _complete_password_sign_in(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        url = f"{CLERK_BASE_URL}/client/sign_ins"
        logger.debug("Enviando credenciais para concluir o login em {}", url)
        response = await client.post(
            url,
            params=self._clerk_params(),
            data={
                "locale": "pt-BR",
                "identifier": self.login,
                "password": self.password,
                "strategy": "password",
            },
            headers=self._form_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def _touch_session(self, client: httpx.AsyncClient, session_id: str) -> None:
        url = f"{CLERK_BASE_URL}/client/sessions/{session_id}/touch"
        logger.debug("Atualizando sessao {} em {}", session_id, url)
        response = await client.post(
            url,
            params=self._clerk_params(),
            data={"active_organization_id": ""},
            headers=self._form_headers(referer=f"{AGENT_BASE_URL}/"),
        )
        response.raise_for_status()

    def _collect_auth_cookies(self, client: httpx.AsyncClient) -> Dict[str, str]:
        relevant = {}
        for cookie_name in (
            "__client",
            "__client_uat",
            "clerk_active_session",
            "clerk_active_context",
            "__session",
        ):
            try:
                value = client.cookies.get(cookie_name)
            except httpx.CookieConflict:
                value = next(
                    (cookie.value for cookie in client.cookies.jar if cookie.name == cookie_name),
                    None,
                )
            if not value:
                continue
            if cookie_name == "clerk_active_context" and value.endswith(":"):
                value = value[:-1]
            relevant[cookie_name] = value
        return relevant

    def _clerk_params(self) -> Dict[str, str]:
        return {
            "__clerk_api_version": CLERK_API_VERSION,
            "_clerk_js_version": CLERK_JS_VERSION,
        }

    def _form_headers(self, *, referer: str = f"{AGENT_BASE_URL}/sign-in") -> Dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": AGENT_BASE_URL,
            "referer": referer,
        }

    def _extract_session_id(self, payload: Dict[str, Any]) -> Optional[str]:
        response = payload.get("response") if isinstance(payload, dict) else None
        if isinstance(response, dict):
            session_id = response.get("created_session_id")
            if isinstance(session_id, str) and session_id:
                return session_id

        client_block = payload.get("client") if isinstance(payload, dict) else None
        if isinstance(client_block, dict):
            session_id = client_block.get("last_active_session_id")
            if isinstance(session_id, str) and session_id:
                return session_id

            sessions = client_block.get("sessions")
            if isinstance(sessions, list) and sessions:
                first = sessions[0]
                if isinstance(first, dict):
                    session_id = first.get("id")
                    if isinstance(session_id, str) and session_id:
                        return session_id
        return None

    async def _ensure_authenticated(self) -> None:
        client = await self._ensure_client()
        if not self._session_id:
            await self.simulate_login()
            return

        await self._touch_session(client, self._session_id)

    async def _ensure_bearer_token(self) -> str:
        async with self._auth_lock:
            if self._bearer_token and not self._token_expired():
                return self._bearer_token

            if not self._session_id:
                raise RuntimeError("Sessao nao disponivel para obtencao de token.")

            client = await self._ensure_client()
            token = await self._fetch_production_token(client)
            self._bearer_token = token
            self._bearer_token_exp = self._extract_token_exp(token)
            return token

    async def _fetch_production_token(self, client: httpx.AsyncClient) -> str:
        if not self._session_id:
            raise RuntimeError("Session ID nao disponivel para obter token.")

        url = f"{CLERK_BASE_URL}/client/sessions/{self._session_id}/tokens/Production"
        logger.debug("Obtendo token de produção em {}", url)
        response = await client.post(
            url,
            params=self._clerk_params(),
            headers=self._form_headers(referer=f"{AGENT_BASE_URL}/"),
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("jwt")
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"Resposta de token invalida: {data}")
        return token

    def _extract_token_exp(self, token: str) -> float:
        parts = token.split(".")
        if len(parts) < 2:
            return 0.0
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
            payload_data = json.loads(payload_bytes)
        except (ValueError, json.JSONDecodeError):
            return 0.0
        exp = payload_data.get("exp")
        if isinstance(exp, (int, float)):
            return float(exp) - 30.0  # margem de segurança
        return 0.0

    def _token_expired(self) -> bool:
        return time.time() >= self._bearer_token_exp

    def _convert_openai_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Adapta a lista de mensagens no formato OpenAI para o formato interno."""
        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content")

            # Suporta conte��do como string ou lista de blocos (OpenAI v2).
            payload: Dict[str, Any] = {"role": role}
            if isinstance(content, list):
                payload["content"] = content
            elif content is None:
                payload["content"] = ""
            else:
                payload["content"] = str(content)

            normalized.append(payload)
        return normalized

    def _extract_answer_text(self, result: Any) -> str:
        """Extrai o texto da resposta agregada retornada por call_model."""
        if result is None:
            return ""

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

    def _build_openai_response(self, answer_text: str, model: str) -> Dict[str, Any]:
        """Monta a resposta no padr��o da OpenAI usando dados locais."""
        created_ts = int(time.time())
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        completion_tokens = len(answer_text.split()) if answer_text else 0
        prompt_tokens = 0

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer_text,
                        "refusal": None,
                        "annotations": [],
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "prompt_tokens_details": {
                    "cached_tokens": 0,
                    "audio_tokens": 0,
                },
                "completion_tokens_details": {
                    "reasoning_tokens": 0,
                    "audio_tokens": 0,
                    "accepted_prediction_tokens": 0,
                    "rejected_prediction_tokens": 0,
                },
            },
            "service_tier": "default",
        }

    async def _chat_event_stream(
        self,
        prompt: Optional[str],
        *,
        messages: Optional[List[Dict[str, Any]]] = None,
        model: str,
        files: Optional[List[Dict[str, Any]]] = None,
        include_tool_events: bool,
        tools: Optional[List[str]],
        chat_id: Optional[str] = None,
    ) -> AsyncGenerator[Tuple[str, str], None]:
        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        chat_identifier = chat_id or _generate_uuid7_like()
        #message_id = _generate_uuid7_like()
        self._last_chat_id = chat_identifier
        if chat_id:
            logger.info(f"Reutilizando chat_id={chat_identifier} fornecido para nova requisicao de chat.")
        else:
            logger.info(f"Gerado chat_id={chat_identifier} para nova requisicao de chat.")
        #analytics_tasks = [
        #    asyncio.create_task(self._register_chat_view(chat_id)),
        #    asyncio.create_task(self._send_amplitude_event(chat_id, model)),
        #]

        payload_messages = self._prepare_messages_payload(
            messages=messages,
            prompt=prompt,
            files=files,
        )

        payload = {
            "mandatoryTools": tools or [],
            "chatId": chat_identifier,
            "contextsIds": [],
            "meetingContextsIds": [],
            "modelAi": model,
            "id": chat_identifier,
            "messages": payload_messages,
            "trigger": "submit-message",
        }
        headers = {
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/",
        }

        stream_url = f"{AGENT_BASE_URL}/api/chat/stream/v1"
        thought_parts: List[str] = []
        self._last_thought = None
        pending_surrogate: Optional[str] = None
        try:
            async with client.stream("POST", stream_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line or not raw_line.startswith("data:"):
                        continue

                    payload_str = raw_line[5:].strip()
                    if not payload_str:
                        continue

                    if payload_str == "[DONE]":
                        if pending_surrogate is not None:
                            yield ("answer", "\uFFFD")
                            pending_surrogate = None
                        if include_tool_events:
                            yield ("answer_end", "")
                        break

                    try:
                        event = json.loads(payload_str)
                    except json.JSONDecodeError:
                        logger.warning("Evento SSE invalido recebido: {}", payload_str)
                        continue

                    event_type = event.get("type")

                    if event_type == "tool-output-available":
                        output = event.get("output") or {}
                        analysis = output.get("analysis") or output.get("content")
                        if isinstance(analysis, str) and analysis.strip():
                            analysis = analysis.strip()
                            thought_parts.append(analysis)
                            if include_tool_events:
                                yield ("thought", analysis)

                        table_payload = output.get("table")
                        if isinstance(table_payload, dict):
                            table_text = self._format_table_output(table_payload)
                            if table_text:
                                yield ("answer", table_text)

                        research_text = self._format_deep_research_output(output)
                        if research_text:
                            yield ("answer", research_text)

                        plain_tool_text = self._extract_tool_text_output(output)
                        if plain_tool_text:
                            yield ("answer", plain_tool_text)
                        continue

                    if event_type == "text-delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            safe_text, pending_surrogate = self._coalesce_surrogates(delta, pending_surrogate)
                            if safe_text:
                                yield ("answer", safe_text)
                        continue

                    if event_type == "text-end":
                        if pending_surrogate is not None:
                            yield ("answer", "\uFFFD")
                            pending_surrogate = None
                        if include_tool_events:
                            yield ("answer_end", "")
                        continue
        finally:
            pending_surrogate = None
            print("")
            #if analytics_tasks:
                #await asyncio.gather(*analytics_tasks, return_exceptions=True)

        if thought_parts:
            self._last_thought = "\n\n".join(thought_parts).strip()
        else:
            self._last_thought = None

    def _coalesce_surrogates(
        self,
        chunk: str,
        pending: Optional[str],
    ) -> Tuple[str, Optional[str]]:
        """Agrupa pares surrogates antes de devolver o trecho ao chamador."""
        safe_parts: List[str] = []
        index = 0

        if pending is not None:
            if chunk and self._is_low_surrogate(chunk[0]):
                safe_parts.append(self._surrogate_pair_to_char(pending, chunk[0]))
                index = 1
                pending = None
            else:
                safe_parts.append("\uFFFD")
                pending = None

        while index < len(chunk):
            char = chunk[index]
            if self._is_high_surrogate(char):
                if index + 1 < len(chunk):
                    nxt = chunk[index + 1]
                    if self._is_low_surrogate(nxt):
                        safe_parts.append(self._surrogate_pair_to_char(char, nxt))
                        index += 2
                        continue
                    safe_parts.append("\uFFFD")
                    index += 1
                    continue
                pending = char
                index += 1
                continue

            if self._is_low_surrogate(char):
                safe_parts.append("\uFFFD")
                index += 1
                continue

            safe_parts.append(char)
            index += 1

        return ("".join(safe_parts), pending)

    @staticmethod
    def _is_high_surrogate(char: str) -> bool:
        return 0xD800 <= ord(char) <= 0xDBFF

    @staticmethod
    def _is_low_surrogate(char: str) -> bool:
        return 0xDC00 <= ord(char) <= 0xDFFF

    @staticmethod
    def _surrogate_pair_to_char(high: str, low: str) -> str:
        code_point = 0x10000 + ((ord(high) - 0xD800) << 10) + (ord(low) - 0xDC00)
        return chr(code_point)

    def _prepare_messages_payload(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]],
        prompt: Optional[str],
        files: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Normaliza a estrutura de mensagens aceita pelo endpoint v2."""
        if not messages:
            if prompt is None:
                raise ValueError("Não é possível construir mensagem padrão sem `prompt`.")
            base_messages = self._prepare_user_message(prompt)
            base_messages[-1]["parts"].extend(self._build_file_parts(files))
            return base_messages

        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            parts = message.get("parts")
            if parts:
                normalized_parts = self._normalize_parts(parts)
            else:
                normalized_parts = self._coerce_parts_from_content(message.get("content"))

            if not normalized_parts:
                normalized_parts = [{"type": "text", "text": ""}]

            normalized.append({"role": role, "parts": normalized_parts})

        file_parts = self._build_file_parts(files)
        if file_parts:
            target = next((msg for msg in normalized if msg.get("role") == "user"), None)
            if target:
                target["parts"] = file_parts + target.get("parts", [])
            else:
                normalized[0]["parts"] = file_parts + normalized[0].get("parts", [])

        return normalized

    def _build_default_parts(
        self,
        prompt: str,
        files: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        parts = self._build_file_parts(files)
        parts.append({"type": "text", "text": prompt})
        return parts

    def _prepare_user_message(
        self,
        prompt: str,
        *,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Cria uma mensagem de usuário com base em um prompt e concatena mensagens existentes."""
        base_parts = [{"type": "text", "text": prompt}]
        user_message = {
            "role": "user",
            "parts": base_parts,
        }
        if not messages:
            return [user_message]

        combined = list(messages)
        combined.append(user_message)
        return combined

    def _build_file_parts(self, files: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        file_parts: List[Dict[str, Any]] = []
        if not files:
            return file_parts

        for file_info in files:
            formatted = {
                "type": "file",
                "filename": file_info.get("filename"),
                "url": file_info.get("url"),
                "size": file_info.get("size"),
                "mediaType": file_info.get("mediaType"),
                "path": file_info.get("path"),
            }
            formatted = {k: v for k, v in formatted.items() if v is not None}
            if len(formatted) > 1:  # precisa de algo além de type
                file_parts.append(formatted)
        return file_parts

    def _coerce_parts_from_content(self, content: Any) -> List[Dict[str, Any]]:
        if isinstance(content, list):
            return [part for part in (self._normalize_part(item) for item in content) if part]
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if content is None:
            return []
        return [{"type": "text", "text": str(content)}]

    def _normalize_parts(self, parts: Any) -> List[Dict[str, Any]]:
        if not isinstance(parts, list):
            return self._coerce_parts_from_content(parts)
        normalized = []
        for part in parts:
            formatted = self._normalize_part(part)
            if formatted:
                normalized.append(formatted)
        return normalized

    def _normalize_part(self, part: Any) -> Optional[Dict[str, Any]]:
        if part is None:
            return None
        if isinstance(part, str):
            return {"type": "text", "text": part}
        if isinstance(part, dict):
            part_type = part.get("type") or "text"
            if part_type == "text":
                text = part.get("text")
                if text is None:
                    return None
                return {"type": "text", "text": str(text)}
            if part_type == "file":
                formatted = {
                    "type": "file",
                    "filename": part.get("filename"),
                    "url": part.get("url"),
                    "size": part.get("size"),
                    "mediaType": part.get("mediaType"),
                    "path": part.get("path"),
                }
                formatted = {k: v for k, v in formatted.items() if v is not None}
                return formatted if len(formatted) > 1 else None
            # fallback: manter chaves originais
            cleaned = {k: v for k, v in part.items() if v is not None}
            cleaned["type"] = part_type
            return cleaned
        return {"type": "text", "text": str(part)}

    def _format_table_output(self, table_payload: Dict[str, Any]) -> Optional[str]:
        """Converte a estrutura de tabela retornada pela API em markdown simples."""
        data = table_payload.get("data")
        if not isinstance(data, dict):
            return None

        headers = data.get("headers")
        rows = data.get("rows")

        if not isinstance(headers, list) or not headers:
            return None

        formatted_headers = [self._stringify_table_cell(header) for header in headers]
        header_line = "| " + " | ".join(formatted_headers) + " |"
        separator_line = "| " + " | ".join("---" for _ in formatted_headers) + " |"

        lines = [header_line, separator_line]

        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, list):
                    continue

                formatted_row = [self._stringify_table_cell(cell) for cell in row]
                if len(formatted_row) < len(formatted_headers):
                    formatted_row.extend([""] * (len(formatted_headers) - len(formatted_row)))
                elif len(formatted_row) > len(formatted_headers):
                    formatted_row = formatted_row[: len(formatted_headers)]

                lines.append("| " + " | ".join(formatted_row) + " |")

        return "\n".join(lines) + "\n"

    def _stringify_table_cell(self, value: Any) -> str:
        """Normaliza os valores das celulas para texto plano."""
        if value is None:
            return ""

        if isinstance(value, str):
            text = value
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, list):
            parts = [self._stringify_table_cell(item) for item in value if item is not None]
            text = ", ".join(part for part in parts if part)
        elif isinstance(value, dict):
            for key in ("text", "value", "title", "content"):
                if key in value:
                    return self._stringify_table_cell(value[key])
            text = str(value)
        else:
            text = str(value)

        return text.replace("\r", " ").replace("\n", " ").strip()

    def _format_deep_research_output(self, output: Dict[str, Any]) -> Optional[str]:
        """Formata respostas do deepResearch (resumo, insights e fontes)."""
        data = output.get("data")
        if not isinstance(data, dict):
            return None

        sections: List[str] = []

        summary = self._coerce_research_text(data.get("summary"), preserve_newlines=True)
        if summary:
            sections.append(summary)

        for field, heading in (
            ("insights", "Insights principais"),
            ("keyInsights", "Insights principais"),
            ("keyFindings", "Principais achados"),
            ("highlights", "Destaques"),
        ):
            section_text = self._format_research_list(data.get(field))
            if section_text:
                sections.append(f"{heading}:\n{section_text}")

        results_text = self._format_research_results(data.get("results"))
        if results_text:
            sections.append(f"Resultados encontrados:\n{results_text}")

        sources_text = self._format_research_sources(data.get("sources"))
        if sources_text:
            sections.append(f"Fontes:\n{sources_text}")

        if not sections:
            return None

        combined = "\n\n".join(section.rstrip() for section in sections if section)
        if not combined.endswith("\n"):
            combined += "\n"
        return combined

    def _extract_tool_text_output(self, output: Dict[str, Any]) -> Optional[str]:
        """Extrai blocos de texto retornados diretamente por ferramentas."""
        data = output.get("data")
        if isinstance(data, str):
            text = data.strip()
            return text or None

        if isinstance(data, dict):
            candidates: List[str] = []
            for key in ("text", "content", "body", "summary", "result"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
            if candidates:
                return "\n\n".join(candidates).join("\n\n")

        return None

    def _format_research_list(self, value: Any) -> Optional[str]:
        """Converte listas ou strings genericas em marcadores."""
        if isinstance(value, list):
            lines = []
            for item in value:
                text = self._coerce_research_text(item)
                if text:
                    lines.append(f"- {text}")
            return "\n".join(lines) if lines else None
        if isinstance(value, str):
            text = self._coerce_research_text(value)
            return f"- {text}" if text else None
        return None

    def _format_research_results(self, value: Any) -> Optional[str]:
        """Formata a secao de resultados detalhados (URL, snippet)."""
        if not isinstance(value, list):
            return None

        lines: List[str] = []
        seen_urls: Set[str] = set()
        for entry in value:
            if not isinstance(entry, dict):
                continue
            url = self._coerce_research_text(entry.get("url"))
            title = self._coerce_research_text(entry.get("title"))
            snippet = self._coerce_research_text(entry.get("snippet"), preserve_newlines=True)

            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)

            primary = title or url
            if not primary:
                continue

            line = primary
            if url and url not in primary:
                line = f"{line} - {url}" if line else url

            snippet = snippet.replace("\n", " ").strip() if snippet else ""
            if snippet:
                line = f"{line}\n  {snippet}"

            lines.append(f"- {line}".rstrip())

        return "\n".join(lines[:10]) if lines else None

    def _format_research_sources(self, value: Any) -> Optional[str]:
        """Formata a lista de fontes retornadas pelo deepResearch."""
        if not isinstance(value, list):
            return None

        lines: List[str] = []
        seen: Set[Tuple[str, str]] = set()
        for entry in value:
            if not isinstance(entry, dict):
                continue
            title = self._coerce_research_text(entry.get("title"))
            url = self._coerce_research_text(entry.get("url"))
            description = self._coerce_research_text(entry.get("description"))

            key = (title, url)
            if key in seen:
                continue
            seen.add(key)

            line = title or url
            if url and url not in line:
                line = f"{line} - {url}" if line else url
            if description:
                line = f"{line}\n  {description}"

            lines.append(f"- {line}".rstrip())

        return "\n".join(lines[:10]) if lines else None

    def _coerce_research_text(self, value: Any, *, preserve_newlines: bool = False) -> str:
        """Normaliza valores arbitrarios em texto simples."""
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.replace("\r", "\n").strip()
            if preserve_newlines:
                return text
            return " ".join(text.split())
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            items = [
                self._coerce_research_text(item, preserve_newlines=preserve_newlines)
                for item in value
            ]
            items = [item for item in items if item]
            if preserve_newlines:
                return "\n".join(items)
            return ", ".join(items)
        if isinstance(value, dict):
            for key in ("text", "summary", "description", "content", "value", "title", "snippet"):
                if key in value:
                    return self._coerce_research_text(value[key], preserve_newlines=preserve_newlines)
            return ""
        return str(value)

    async def logout(self) -> None:
        """Efetua o logout encerrando a sessao atual."""
        if not self._session_id:
            return

        client = await self._ensure_client()

        try:
            await self._touch_session(client, self._session_id)
        except httpx.HTTPError as exc:
            logger.debug("Falha ao tocar sessao antes do logout: {}", exc)

        await self._notify_logout_navigation(client)
        await self._delete_session(client)

        self._session_id = None
        self._bearer_token = None
        self._bearer_token_exp = 0.0
        self._auth_cookies.clear()
        client.cookies.clear()

    async def _notify_logout_navigation(self, client: httpx.AsyncClient) -> None:
        """Reproduz a chamada observada no front após o logout."""
        headers = {
            "accept": "text/x-component",
            "content-type": "text/plain;charset=UTF-8",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/agentic-chat",
        }
        try:
            await client.post(
                f"{AGENT_BASE_URL}/agentic-chat",
                headers=headers,
                content="[]",
            )
        except httpx.HTTPError as exc:
            logger.debug("Falha ao notificar navegação de logout: {}", exc)

    async def _delete_session(self, client: httpx.AsyncClient) -> None:
        params = {
            "__clerk_api_version": CLERK_API_VERSION,
            "_clerk_js_version": CLERK_JS_VERSION,
            "_method": "DELETE",
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/",
        }
        try:
            await client.post(
                f"{CLERK_BASE_URL}/client/sessions",
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.debug("Falha ao encerrar sessão: {}", exc)

    async def _register_chat_view(self, chat_id: str) -> None:
        """Registra o chat recém criado no endpoint de analytics do Adapta."""
        client = await self._ensure_client()
        timestamp_ms = int(time.time() * 1000)
        payload = {
            "o": f"{AGENT_BASE_URL}/agentic-chat/{chat_id}",
            "sv": "0.1.3",
            "sdkn": "@vercel/analytics/next",
            "sdkv": "1.5.0",
            "ts": timestamp_ms,
            "dp": f"/agentic-chat/{chat_id}",
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/agentic-chat/{chat_id}",
        }

        try:
            await client.post(
                f"{AGENT_BASE_URL}/_vercel/insights/view",
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.debug("Falha ao registrar chat view: {}", exc)

    async def _send_amplitude_event(self, chat_id: str, model: str) -> None:
        """Replica a chamada de métricas para o Amplitude observada no front."""
        client = await self._ensure_client()
        timestamp_ms = int(time.time() * 1000)
        event = {
            "user_id": self.login,
            "device_id": "2457e3a6-62b2-45bf-b4c1-fd9ace4fac44",
            "session_id": timestamp_ms,
            "time": timestamp_ms,
            "platform": "Web",
            "language": "pt-BR",
            "ip": "$remote",
            "insert_id": str(uuid.uuid4()),
            "event_type": "chat_interaction_one_plus",
            "event_properties": {
                "model": model,
                "userId": self.login,
                "chatId": chat_id,
            },
            "event_id": 0,
            "library": "amplitude-ts/2.24.0",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            ),
        }
        from datetime import datetime

        payload = {
            "api_key": AMPLITUDE_API_KEY,
            "events": [event],
            "options": {},
            "client_upload_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }
        headers = {
            "accept": "*/*",
            "content-type": "text/plain;charset=UTF-8",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/",
        }
        try:
            await client.post(
                AMPLITUDE_ENDPOINT,
                headers=headers,
                content=json.dumps(payload),
            )
        except httpx.HTTPError as exc:
            logger.debug("Falha ao enviar métrica para o Amplitude: {}", exc)

async def _main() -> None:
    async with AdaptaClientV2() as client:
        result = await client.simulate_login()
        masked = {
            key: value if len(value) <= 10 else f"{value[:4]}...{value[-4:]}"
            for key, value in result.cookies.items()
        }
        print(f"Session ID: {result.session_id}")
        print(f"Cookies coletados: {masked}")

        #pergunta = "gere uma tabela comparando scrum e xp"
        pergunta = "pesquise na internet tecnicas para estudo de tabuada"
        chat_ids: List[str] = []

        print("\n--- Streaming em tempo real ---")

        stream = await client.call_model(prompt = pergunta, isStream=True)
        async for kind, trecho in stream:
            if kind == "thought":
                print("\n\n\nPensando...\n\n\n")
                print(trecho, end='', flush=True)
                print("\n\n\nPensamento Concluido\n\n\n")
            elif kind == "answer":
                print(trecho, end='', flush=True)
        stream_chat_id = client.last_chat_id
        if stream_chat_id:
            chat_ids.append(stream_chat_id)
            print(f"Chat ID (stream): {stream_chat_id}")

        print("\n--- Resposta agregada (isStream=False) ---")

        #aggregate = await client.call_model(pergunta, isStream=False)
        #for message in aggregate.messages:
        #    prefix = "[Pensamento]" if message["kind"] == "thought" else "[Resposta]"
        #    print(prefix, message["text"])

        await client.logout()
        print("\nLogout concluido.")


if __name__ == "__main__":
    asyncio.run(_main())
