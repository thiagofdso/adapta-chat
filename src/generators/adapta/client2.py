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
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

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
DIRECT_UPLOAD_ENDPOINT = f"{FILE_API_BASE}/direct-upload-url"
METADATA_ENDPOINT = f"{FILE_API_BASE}/metadata"
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
                logger.warning("Cookies esperados nao encontrados: %s", ", ".join(sorted(missing)))

            logger.info("Login concluído com session_id=%s", self._session_id)
            return AuthResult(session_id=self._session_id, cookies=cookies)

    async def chat_completion_stream(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """Executa uma chamada streaming retornando eventos (kind, texto).

        kind:
            - "thought": trechos classificados como pensamento/analysis.
            - "answer": fragmentos incrementais da resposta.
            - "answer_end": indicador de término de um bloco de resposta.
        """
        async for event_type, payload in self._chat_event_stream(
            prompt, model=model, files=files, include_tool_events=True
        ):
            if event_type in {"thought", "answer", "answer_end"}:
                yield (event_type, payload)

    async def chat_completion(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        files: Optional[List[Dict[str, Any]]] = None,
        ignore_thoughts: Optional[bool] = None,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """Executa a chamada agregada retornando os eventos em ordem.

        Use `ignore_thoughts=True` (ou `ignoreThoughts=True`) para ocultar trechos
        classificados como pensamento.
        """
        if "ignoreThoughts" in kwargs:
            ignore_thoughts = kwargs.pop("ignoreThoughts")
        if kwargs:
            unexpected = ", ".join(kwargs.keys())
            raise TypeError(f"chat_completion() recebeu argumentos inesperados: {unexpected}")
        if ignore_thoughts is None:
            ignore_thoughts = False

        messages: List[Dict[str, str]] = []
        current_answer_chunks: List[str] = []

        async for event_type, payload in self._chat_event_stream(
            prompt,
            model=model,
            files=files,
            include_tool_events=True,
        ):
            if event_type == "answer":
                current_answer_chunks.append(payload)
                continue

            if event_type == "answer_end":
                if current_answer_chunks:
                    answer_text = "".join(current_answer_chunks)
                    messages.append({"kind": "answer", "text": answer_text})
                    current_answer_chunks = []
                continue

            if event_type == "thought":
                if not ignore_thoughts:
                    messages.append({"kind": "thought", "text": payload})

        # Finaliza eventual resposta que não tenha recebido answer_end
        if current_answer_chunks:
            answer_text = "".join(current_answer_chunks)
            messages.append({"kind": "answer", "text": answer_text})

        return ChatCompletionResult(messages=messages)

    async def delete_chats(self, chat_ids: List[str]) -> Dict[str, Any]:
        """Remove chats na plataforma Adapta.one."""
        if not chat_ids:
            return {"success": True, "data": None, "details": {"message": "Nenhum chatId informado."}}

        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()
        logger.debug("Solicitando exclusão de %d chats.", len(chat_ids))

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
        logger.debug("Resposta da exclusão de chats: %s", payload)
        return payload

    async def upload_file(self, caminho_arquivo: str) -> Dict[str, Any]:
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

        request_headers = {
            "accept": "application/json",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": AGENT_BASE_URL,
            "referer": f"{AGENT_BASE_URL}/",
        }

        inicial_payload = {
            "originalFilename": file_path.name,
            "mimeType": mime_type,
            "sizeInBytes": tamanho_bytes,
            "toCompany": False,
        }

        response = await client.post(
            DIRECT_UPLOAD_ENDPOINT,
            headers=request_headers,
            json=inicial_payload,
        )
        response.raise_for_status()
        upload_data = response.json().get("data") or {}

        upload_url = upload_data.get("uploadUrl")
        file_key = upload_data.get("fileKey")
        required_headers = upload_data.get("requiredHeaders") or {}
        if not upload_url or not file_key:
            raise RuntimeError(f"Dados insuficientes para upload: {upload_data}")

        upload_headers = dict(required_headers)
        upload_headers.setdefault("Content-Type", mime_type)

        file_bytes = file_path.read_bytes()
        put_response = await client.put(upload_url, headers=upload_headers, content=file_bytes)
        put_response.raise_for_status()

        metadata_payload = {
            "fileKey": file_key,
            "sizeInBytes": tamanho_bytes,
            "mimeType": mime_type,
            "originalFilename": file_path.name,
            "toCompany": False,
        }

        metadata_response = await client.post(
            METADATA_ENDPOINT,
            headers=request_headers,
            json=metadata_payload,
        )
        metadata_response.raise_for_status()
        metadata = metadata_response.json().get("data") or metadata_response.json()

        return {
            "id": metadata.get("id"),
            "path": metadata.get("path") or metadata.get("fileKey"),
            "url": metadata.get("url"),
            "signed_url": metadata.get("signedUrl") or metadata.get("signed_url") or metadata.get("url"),
            "size": metadata.get("sizeInBytes") or metadata.get("size") or tamanho_bytes,
            "mediaType": metadata.get("mediaType") or metadata.get("mimeType") or mime_type,
            "filename": metadata.get("originalFilename") or metadata.get("filename") or file_path.name,
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

    async def delete_files(self, files_paths: List[str]) -> Dict[str, Any]:
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

    async def delete_file(self, file_path: str) -> Dict[str, Any]:
        """Atalho para excluir um unico arquivo."""
        return await self.delete_files([file_path])

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
        if self._client is None or self._client.is_closed:
            if self._client is not None:
                await self._client.aclose()

            timeout = httpx.Timeout(timeout=60.0, connect=15.0, read=60.0)
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

        return self._client

    async def _fetch_sign_in_page(self, client: httpx.AsyncClient) -> None:
        url = f"{AGENT_BASE_URL}/sign-in"
        logger.debug("Buscando pagina de login: %s", url)
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
        logger.debug("Iniciando tentativa de login (passkey) em %s", url)
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
        logger.debug("Enviando credenciais para concluir o login em %s", url)
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
        logger.debug("Atualizando sessao %s em %s", session_id, url)
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
        logger.debug("Obtendo token de produção em %s", url)
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

    async def _chat_event_stream(
        self,
        prompt: str,
        *,
        model: str,
        files: Optional[List[Dict[str, Any]]] = None,
        include_tool_events: bool,
    ) -> AsyncGenerator[Tuple[str, str], None]:
        client = await self._ensure_client()
        await self._ensure_authenticated()
        token = await self._ensure_bearer_token()

        chat_id = _generate_uuid7_like()
        message_id = _generate_uuid7_like()
        self._last_chat_id = chat_id
        logger.info("Gerado chat_id=%s message_id=%s para nova requisicao de chat.", chat_id, message_id)
        analytics_tasks = [
            asyncio.create_task(self._register_chat_view(chat_id)),
            asyncio.create_task(self._send_amplitude_event(chat_id, model)),
        ]

        parts: List[Dict[str, Any]] = []
        if files:
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
                parts.append(formatted)
        parts.append({"type": "text", "text": prompt})

        payload = {
            "mandatoryTools": [],
            "chatId": chat_id,
            "contextsIds": [],
            "meetingContextsIds": [],
            "modelAi": model,
            "id": chat_id,
            "messages": [
                {
                    "role": "user",
                    "parts": parts,
                    "id": message_id,
                }
            ],
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
                        if include_tool_events:
                            yield ("answer_end", "")
                        break

                    try:
                        event = json.loads(payload_str)
                    except json.JSONDecodeError:
                        logger.warning("Evento SSE invalido recebido: %s", payload_str)
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
                        continue

                    if event_type == "text-delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            yield ("answer", delta)
                        continue

                    if event_type == "text-end":
                        if include_tool_events:
                            yield ("answer_end", "")
                        continue
        finally:
            if analytics_tasks:
                await asyncio.gather(*analytics_tasks, return_exceptions=True)

        if thought_parts:
            self._last_thought = "\n\n".join(thought_parts).strip()
        else:
            self._last_thought = None

    async def logout(self) -> None:
        """Efetua o logout encerrando a sessao atual."""
        if not self._session_id:
            return

        client = await self._ensure_client()

        try:
            await self._touch_session(client, self._session_id)
        except httpx.HTTPError as exc:
            logger.debug("Falha ao tocar sessao antes do logout: %s", exc)

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
            logger.debug("Falha ao notificar navegação de logout: %s", exc)

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
            logger.debug("Falha ao encerrar sessão: %s", exc)

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
            logger.debug("Falha ao registrar chat view: %s", exc)

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
            logger.debug("Falha ao enviar métrica para o Amplitude: %s", exc)

async def _main() -> None:
    async with AdaptaClientV2() as client:
        result = await client.simulate_login()
        masked = {
            key: value if len(value) <= 10 else f"{value[:4]}...{value[-4:]}"
            for key, value in result.cookies.items()
        }
        print(f"Session ID: {result.session_id}")
        print(f"Cookies coletados: {masked}")

        local_file = Path("teste.txt")
        uploaded_from_local = False
        uploaded: Dict[str, Any]
        uploaded_path: Optional[str] = None

        if local_file.exists():
            try:
                uploaded = await client.upload_file(str(local_file))
                uploaded_from_local = True
                uploaded_path = uploaded.get("path")
                print(f"Upload concluido para {uploaded_path}")
            except Exception as exc:
                print(f"Falha ao enviar teste.txt: {exc}")
                uploaded = {}
        else:
            print("Arquivo teste.txt nao encontrado; utilizando arquivo de referencia padrao.")
            uploaded = {}

        if not uploaded:
            uploaded = {
                "filename": "Ajustes-Manual.txt",
                "url": (
                    "https://adapta-one-prod.s3.sa-east-1.amazonaws.com/"
                    "thiagofdso.ufpa%40gmail.com/txt/Ajustes-Manual.txt?"
                    "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
                    "X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&"
                    "X-Amz-Credential=AKIA3FLD6RMYLYFE2L2Q%2F20251030%2Fsa-east-1%2Fs3%2Faws4_request&"
                    "X-Amz-Date=20251030T042638Z&"
                    "X-Amz-Expires=43200&"
                    "X-Amz-Signature=4a1d3223bc6f0a9b6b03929892a4a4aba6917faf8520feec97b07e7e903042ed&"
                    "X-Amz-SignedHeaders=host&"
                    "x-amz-checksum-mode=ENABLED&"
                    "x-id=GetObject"
                ),
                "size": 35777,
                "mediaType": "text/plain",
                "path": "thiagofdso.ufpa@gmail.com/txt/Ajustes-Manual.txt",
            }
            uploaded_path = uploaded.get("path")

        list_result = await client.list_files(limit=10, search=uploaded.get("filename"))
        files_listed = list_result.get("files", [])
        print(f"\nArquivos retornados: {len(files_listed)} (exibindo ate 3)")
        for entry in files_listed[:3]:
            print(f" - {entry.get('filename')} ({entry.get('path')})")

        matched_entry: Optional[Dict[str, Any]] = None
        if uploaded_path:
            for entry in files_listed:
                if entry.get("path") == uploaded_path:
                    matched_entry = entry
                    break

        download_source = matched_entry or uploaded
        try:
            download_dir = Path("downloads")
            download_name = download_source.get("filename") or "arquivo-baixado.txt"
            download_path = download_dir / download_name
            downloaded_file = await client.download_file(download_source, download_path)
            print(f"Arquivo baixado para {downloaded_file}")
        except Exception as exc:
            print(f"Download nao realizado: {exc}")

        chat_file_payload = {
            "filename": download_source.get("filename"),
            "url": download_source.get("url") or download_source.get("signed_url"),
            "size": download_source.get("size"),
            "mediaType": download_source.get("mediaType") or download_source.get("mime_type"),
            "path": download_source.get("path"),
        }
        chat_file_payload = {k: v for k, v in chat_file_payload.items() if v is not None}

        pergunta = "quantos topicos tem o manual"

        chat_ids: List[str] = []

        print("\n--- Streaming em tempo real ---")
        async for kind, trecho in client.chat_completion_stream(pergunta, files=[chat_file_payload]):
            if kind == "thought":
                print(f"[stream/pensamento] {trecho}")
            elif kind == "answer":
                print(f"[stream/resposta] {trecho}")
            elif kind == "answer_end":
                print("[stream] --- fim da resposta ---")
        stream_chat_id = client.last_chat_id
        if stream_chat_id:
            chat_ids.append(stream_chat_id)
            print(f"Chat ID (stream): {stream_chat_id}")

        agregado = await client.chat_completion(pergunta, files=[chat_file_payload])
        agregado_chat_id = client.last_chat_id
        if agregado_chat_id:
            chat_ids.append(agregado_chat_id)
        print("\n--- Mensagens agregadas ---")
        if agregado_chat_id:
            print(f"Chat ID (agregado): {agregado_chat_id}")
        for idx, msg in enumerate(agregado.messages, start=1):
            print(f"{idx:02d}. ({msg['kind']}) {msg['text']}")

        agregado_sem_pensamento = await client.chat_completion(
            pergunta,
            files=[chat_file_payload],
            ignoreThoughts=True,
        )
        agregado_sem_chat_id = client.last_chat_id
        if agregado_sem_chat_id:
            chat_ids.append(agregado_sem_chat_id)
        print("\n--- Mensagens agregadas (ignoreThoughts=True) ---")
        if agregado_sem_chat_id:
            print(f"Chat ID (agregado sem pensamento): {agregado_sem_chat_id}")
        for idx, msg in enumerate(agregado_sem_pensamento.messages, start=1):
            print(f"{idx:02d}. ({msg['kind']}) {msg['text']}")

        if chat_ids:
            unique_chat_ids = list(dict.fromkeys(chat_ids))
            delete_result = await client.delete_chats(unique_chat_ids)
            print("\n--- Exclusao de chats ---")
            print(f"Chat IDs removidos: {unique_chat_ids}")
            print(f"Resposta da API: {delete_result}")
        else:
            print("\nNenhum chat_id gerado para excluir.")

        if uploaded_from_local and uploaded_path:
            try:
                removal = await client.delete_file(uploaded_path)
                print(f"\nArquivo remoto teste.txt removido: {removal}")
            except Exception as exc:
                print(f"\nNao foi possivel remover teste.txt: {exc}")

        await client.logout()
        print("\nLogout concluido.")


if __name__ == "__main__":
    asyncio.run(_main())
