"""Cliente assíncrono para a API Adapta.one.

Este módulo implementa um cliente assíncrono para comunicação com a API Adapta.one,
fornecendo autenticação, gerenciamento de sessão e métodos para chamadas de IA.
"""

import asyncio
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import httpx

from config import settings
from utils.logger import logger


# Formatos de arquivo aceitos para upload
FORMATOS_ACEITOS = {
    '.txt', '.docx', '.pdf', '.xlsx', '.xls', '.csv', '.png', '.jpg', '.jpeg'
}

FORMATOS_MIME = {
    '.txt': 'text/plain',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pdf': 'application/pdf',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
}


class AdaptaClient:
    """Cliente assíncrono para a API Adapta.one.
    
    Fornece métodos para autenticação, gerenciamento de sessão e chamadas
    para diferentes modelos de IA através da API Adapta.one.
    """
    
    def __init__(
        self,
        cookies_str: Optional[str] = None,
        user_id: Optional[str] = None,
        timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        rate_limit_max_requests: int = 1,
        rate_limit_interval: float = 30.0,
    ):
        """Inicializa o cliente Adapta.
        
        Args:
            cookies_str: String de cookies do navegador.
            user_id: ID do usuário.
            timeout: Timeout geral em segundos (None = sem timeout).
            connect_timeout: Timeout de conexão em segundos (None = sem timeout).
            read_timeout: Timeout de leitura em segundos (None = sem timeout).
            rate_limit_max_requests: Quantidade maxima de atualizacoes de sessao permitidas no intervalo configurado.
            rate_limit_interval: Intervalo em segundos utilizado no controle de rate limit das atualizacoes de sessao.
        """
        self.cookies_str = cookies_str
        self.user_id = user_id or "user_2yPVNPe0Wc1yTd83pzslODn0it2"
        self.clerk_base_url = "https://clerk.adapta.one/v1"
        self.client: Optional[httpx.AsyncClient] = None
        self.session_id: Optional[str] = None
        
        # Configurações de timeout
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        
        # Parse dos cookies se fornecidos
        if cookies_str:
            sanitized_cookies = cookies_str.strip().strip("'\"")
            self.cookies = self._parse_cookies(sanitized_cookies)
        else:
            self.cookies = {}

        if session_id:
            self.session_id = session_id.strip().strip("'\"")
            #logger.info(f"Usando session_id fornecida: {self.session_id}")

        # Headers padrão
        self.headers = self._default_headers()

        if rate_limit_max_requests < 1:
            raise ValueError("rate_limit_max_requests deve ser maior ou igual a 1")
        if rate_limit_interval <= 0:
            raise ValueError("rate_limit_interval deve ser maior que 0")

        self._rate_limit_max_requests = rate_limit_max_requests
        self._rate_limit_interval = rate_limit_interval
        self._session_update_events: Deque[float] = deque()
        self.last_session_update_at: Optional[datetime] = None
        self._update_session_lock: Optional[asyncio.Lock] = None

    def _default_headers(self) -> Dict[str, str]:
        """Retorna os headers padrão para as requisições.
        
        Returns:
            Headers padrão para requisições HTTP.
        """
        return {
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-encoding": "br",
            "priority": "u=1, i",
            "origin": "https://app.adapta.one",
            "referer": "https://app.adapta.one/",
            "sec-ch-ua": 'Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site"
        }
    
    def _get_update_session_lock(self) -> asyncio.Lock:
        """Retorna (criando sob demanda) o lock usado na atualizacao de sessao."""
        if self._update_session_lock is None:
            self._update_session_lock = asyncio.Lock()
        return self._update_session_lock
    
    def _parse_cookies(self, cookies_str: str) -> Dict[str, str]:
        """Converte uma string de cookies em um dicionário.

        Args:
            cookies_str: String de cookies.

        Returns:
            Dicionário de cookies.

        Raises:
            ValueError: Se a string de cookies for inválida.
        """
        cookies: Dict[str, str] = {}
        for raw_pair in cookies_str.split(';'):
            pair = raw_pair.strip()
            if not pair:
                continue
            if '=' not in pair:
                logger.warning(f"Entrada de cookie inválida ignorada: {pair}")
                continue
            key, value = pair.split('=', 1)
            key = key.strip().strip("'\"")
            value = value.strip().strip("'\"")
            if key:
                cookies[key] = value
        if not cookies:
            raise ValueError(f"String de cookies invalida: {cookies_str}")
        return cookies

    async def __aenter__(self):
        """Context manager entry."""
        await self._ensure_client()
        await self._update_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self) -> None:
        """Garante que o cliente HTTP est inicializado e aberto."""
        if self.client is None or self.client.is_closed:
            if self.client is not None:
                await self.client.aclose()
            if self.timeout is None and self.connect_timeout is None and self.read_timeout is None:
                timeout_config = None
            else:
                timeout_config = httpx.Timeout(
                    timeout=self.timeout or 300.0,
                    connect=self.connect_timeout or 60.0,
                    read=self.read_timeout or 300.0,
                )

            self.client = httpx.AsyncClient(
                timeout=timeout_config,
                follow_redirects=True,
            )

            if not self.session_id:
                await self._update_credentials()

    async def _update_credentials(self) -> None:
        """Atualiza as credenciais do cliente, incluindo o session_id."""
        if not self.client:
            logger.error("Cliente HTTP não inicializado")
            raise ValueError("Cookies não estão disponíveis")

        try:
            if not self.cookies:
                logger.error("Nenhum cookie disponível para atualizar credenciais")
                raise ValueError("Cookies não estão disponíveis")

            logger.debug(f"Cookies disponíveis: {list(self.cookies.keys())}")

            client_url = f"{self.clerk_base_url}/client?__clerk_api_version=2025-04-10&_clerk_js_version=5.101.1"
            logger.debug(f"Fazendo requisição para: {client_url}")

            response = await self.client.get(
                client_url,
                headers=self.headers,
                cookies=self.cookies,
            )
            logger.debug(f"Resposta da API: Status {response.status_code}")

            response.raise_for_status()

            client_data = response.json()
            logger.debug(
                f"Estrutura da resposta: {list(client_data.keys()) if isinstance(client_data, dict) else 'Não é dict'}"
            )

            if "response" not in client_data:
                logger.error(f"Campo 'response' não encontrado na resposta: {client_data}")
                raise KeyError("Campo 'response' não encontrado na resposta da API")

            response_data = client_data["response"]
            logger.debug(
                f"Estrutura do response: {list(response_data.keys()) if isinstance(response_data, dict) else 'Não é dict'}"
            )

            if "last_active_session_id" not in response_data:
                logger.error(f"Campo 'last_active_session_id' não encontrado: {response_data}")
                raise KeyError("Campo 'last_active_session_id' não encontrado na resposta")

            self.session_id = response_data["last_active_session_id"]

            if not self.session_id:
                logger.error("Session ID obtido está vazio")
                raise ValueError("Session ID está vazio")

            logger.debug(f"Credenciais atualizadas. Session ID: {self.session_id}")

        except httpx.HTTPError as e:
            logger.error(f"Erro HTTP ao atualizar credenciais: {e}")
            if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                logger.error(f"Status code: {e.response.status_code}")
                logger.error(f"Resposta: {e.response.text[:500]}")
            raise
        except KeyError as e:
            logger.error(f"Erro ao extrair session_id da resposta: {e}")
            raise
        except ValueError as e:
            logger.error(f"Erro de validação: {e}")
            raise
        except Exception as e:
            logger.error(f"Erro inesperado ao atualizar credenciais: {e}")
            logger.error(f"Tipo do erro: {type(e).__name__}")
            raise

    async def _update_session(self) -> None:
        """Atualiza o cookie __session com o token JWT atualizado respeitando o rate limit."""
        if not self.client or not self.session_id:
            logger.error("Cliente ou session_id não inicializado")
            raise RuntimeError("Cliente ou session_id não inicializado")

        lock = self._get_update_session_lock()
        async with lock:
            current_monotonic = time.monotonic()
            while (
                self._session_update_events
                and current_monotonic - self._session_update_events[0] >= self._rate_limit_interval
            ):
                self._session_update_events.popleft()

            if len(self._session_update_events) >= self._rate_limit_max_requests:
                logger.debug(
                    "Rate limit de atualização de sessão atingido para o usuário %s; mantendo cookies atuais.",
                    self.user_id,
                )
                return

            try:
                touch_url = (
                    f"{self.clerk_base_url}/client/sessions/{self.session_id}/touch?"
                    "__clerk_api_version=2025-04-10&_clerk_js_version=5.101.1"
                )
                touch_headers = self.headers.copy()
                touch_headers["content-type"] = "application/x-www-form-urlencoded"

                response = await self.client.post(
                    touch_url,
                    headers=touch_headers,
                    cookies=self.cookies,
                    content="active_organization_id=",
                )
                response.raise_for_status()

                session_data = response.json()
                session_jwt = session_data["client"]["sessions"][0]["last_active_token"]["jwt"]

                if not session_jwt:
                    raise ValueError("Token JWT obtido está vazio")

                self.cookies["__session"] = session_jwt
                self.cookies["__session_xcsZUTdN"] = session_jwt
                self._session_update_events.append(current_monotonic)
                self.last_session_update_at = datetime.now(timezone.utc)

                logger.debug("Sessão atualizada com sucesso. Token: {}...", session_jwt[:20])

            except httpx.HTTPError as e:
                logger.error(f"Erro ao atualizar sessão: {e}")
                raise
            except KeyError as e:
                logger.error(f"Erro ao extrair token da resposta: {e}")
                raise
            except ValueError as e:
                logger.error(f"Token inválido: {e}")
                raise


    def _generate_random_id(self) -> str:
        """Gera um ID aleatório no formato UUID4.
        
        Returns:
            ID aleatório formatado.
        """
        uuid_obj = uuid.uuid4()
        uuid_str = str(uuid_obj)
        return f"{uuid_str[:8]}-{uuid_str[9:13]}-{uuid_str[14:18]}-{uuid_str[19:23]}-{uuid_str[24:]}"
    
    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> httpx.Response:
        """Faz uma requisição HTTP assíncrona.
        
        Args:
            method: Método HTTP (GET, POST, etc.).
            url: URL da requisição.
            headers: Headers adicionais.
            **kwargs: Argumentos adicionais para httpx.
            
        Returns:
            Resposta HTTP.
            
        Raises:
            httpx.HTTPError: Se a requisição falhar.
        """
        await self._ensure_client()
        await self._update_session()
        
        if not self.client:
            logger.error("Cliente HTTP não inicializado")
            raise RuntimeError("Cliente HTTP não inicializado")
        
        # Validar se o token está presente
        if '__session' not in self.cookies or not self.cookies['__session']:
            logger.error("Token de sessão não está disponível")
            raise ValueError("Token de sessão não está disponível")
        
        request_headers = self.headers.copy()
        if headers:
            request_headers.update(headers)
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=request_headers,
                cookies=self.cookies,
                **kwargs
            )
            response.raise_for_status()
            return response
            
        except httpx.HTTPError as e:
            logger.error(f"Erro na requisição {method} {url}: {e}")
            raise
    
    @staticmethod
    def is_formato_aceito(extensao: str) -> bool:
        """Verifica se uma extensão de arquivo é aceita para upload.
        
        Args:
            extensao: Extensão do arquivo (ex: '.txt', '.pdf').
            
        Returns:
            True se o formato for aceito, False caso contrário.
        """
        return extensao.lower() in FORMATOS_ACEITOS
    
    @staticmethod
    def get_formatos_aceitos() -> set[str]:
        """Retorna o conjunto de formatos aceitos para upload.
        
        Returns:
            Conjunto com as extensões aceitas.
        """
        return FORMATOS_ACEITOS.copy()
    
    @staticmethod
    def _prepare_files_payload(file_ids: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Normaliza a lista de arquivos para o payload de conversa."""
        if not file_ids:
            return []

        normalized: List[Dict[str, Any]] = []
        for item in file_ids:
            if isinstance(item, dict):
                payload_item = dict(item)
                file_id = payload_item.get("id") or payload_item.get("fileId") or payload_item.get("file_id")
                if file_id and "id" not in payload_item:
                    payload_item["id"] = str(file_id)
                normalized.append(payload_item)
            else:
                normalized.append({"id": str(item)})
        return normalized

    async def obter_arquivos(self) -> List[Dict[str, Any]]:
        """Recupera a lista de arquivos disponíveis para o usuário autenticado."""
        await self._ensure_client()
        await self._update_session()

        headers = self.headers.copy()
        headers['referer'] = "https://app.adapta.one/"
        headers['authorization'] = f"Bearer {self.cookies['__session']}"
        headers['x-user-id'] = self.user_id
        if self.session_id:
            headers['x-session-id'] = self.session_id

        response = await self._make_request(
            "GET",
            "https://api.adapta.one/api/file",
            headers=headers
        )

        payload = response.json()
        arquivos = payload.get("data", [])
        logger.debug(f"{len(arquivos)} arquivos retornados pelo endpoint de arquivos.")
        return arquivos

    async def _resolve_files_payload(self, file_refs: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Garante que os arquivos usados em conversas tenham metadados completos."""
        if not file_refs:
            return []

        prepared = self._prepare_files_payload(file_refs)
        missing_metadata = [item for item in prepared if not item or len(item.keys()) == 1]

        if not missing_metadata:
            return prepared

        arquivos_disponiveis = await self.obter_arquivos()
        arquivos_por_id = {str(arq.get("id")): arq for arq in arquivos_disponiveis if arq.get("id")}

        resolved: List[Dict[str, Any]] = []
        for item in prepared:
            file_id = item.get("id")
            if file_id and file_id in arquivos_por_id:
                resolved.append(arquivos_por_id[file_id])
            else:
                if len(item.keys()) > 1:
                    resolved.append(item)
                else:
                    logger.warning(f"Arquivo com ID {file_id} não encontrado para anexar na conversa.")
        return resolved

    async def _resolve_messages_payload(
        self,
        messages: List[Dict[str, Any]],
        default_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normaliza os arquivos presentes dentro de cada mensagem."""
        resolved_messages: List[Dict[str, Any]] = []

        for message in messages:
            msg_copy = dict(message)
            message_files = msg_copy.get("files")
            if message_files:
                msg_copy["files"] = await self._resolve_files_payload(message_files)
            elif default_files and msg_copy.get("role") == "user":
                msg_copy["files"] = default_files
            resolved_messages.append(msg_copy)

        return resolved_messages
    
    async def upload_arquivo(self, caminho_arquivo: str) -> Optional[Dict[str, Any]]:
        """Carrega um arquivo para a API e retorna o ID do arquivo.
        
        Args:
            caminho_arquivo: O caminho para o arquivo a ser carregado.
            
        Returns:
            Dicionário com informações do arquivo carregado ou None em caso de erro.
            
        Raises:
            ValueError: Se o formato do arquivo não for suportado.
        """
        try:
            file_path = Path(caminho_arquivo)
            if not file_path.exists():
                logger.error(f"Arquivo não encontrado: {caminho_arquivo}")
                return None
            
            # Validação de formatos aceitos
            extensao = file_path.suffix.lower()
            
            if not self.is_formato_aceito(extensao):
                logger.error(f"Formato de arquivo não suportado: {extensao}. Formatos aceitos: {', '.join(self.get_formatos_aceitos())}")
                raise ValueError(f"Formato de arquivo não suportado: {extensao}. Formatos aceitos: {', '.join(self.get_formatos_aceitos())}")
            
            url = "https://api.adapta.one/api/file/direct-upload-url"
            await self._ensure_client()
            await self._update_session()
            
            arquivo_headers = self.headers.copy()
            arquivo_headers['origin'] = "https://app.adapta.one"
            arquivo_headers['referer'] = "https://app.adapta.one/"
            arquivo_headers['authorization'] = f"Bearer {self.cookies['__session']}"
            arquivo_headers['content-type'] = 'application/json'
            arquivo_headers['x-user-id'] = self.user_id

            tamanho_bytes = file_path.stat().st_size
            mime_type = FORMATOS_MIME.get(extensao, 'application/octet-stream')

            inicio_payload = {
                "originalFilename": file_path.name,
                "mimeType": mime_type,
                "sizeInBytes": tamanho_bytes,
                "toCompany": False
            }

            response = await self._make_request(
                "POST",
                url,
                headers=arquivo_headers,
                json=inicio_payload
            )
            
            data = response.json()
            upload_data = data.get("data")
            if not upload_data:
                logger.error(f"Resposta inválida da API ao solicitar URL de upload: {data}")
                return None

            upload_url = upload_data.get("uploadUrl")
            file_key = upload_data.get("fileKey")
            required_headers = upload_data.get("requiredHeaders") or {}

            if not upload_url or not file_key:
                logger.error(f"Dados essenciais ausentes na resposta de upload: {upload_data}")
                return None

            if not self.client:
                logger.error("Cliente HTTP não inicializado para upload S3")
                raise RuntimeError("Cliente HTTP não inicializado para upload S3")

            upload_headers = dict(required_headers)
            upload_headers.setdefault("Content-Type", mime_type)

            file_bytes = file_path.read_bytes()

            try:
                put_response = await self.client.put(
                    upload_url,
                    headers=upload_headers,
                    content=file_bytes
                )
                put_response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(f"Erro ao enviar arquivo para storage S3: {e}")
                raise

            metadata_payload = {
                "fileKey": file_key,
                "sizeInBytes": tamanho_bytes,
                "mimeType": mime_type,
                "originalFilename": file_path.name,
                "toCompany": False
            }

            metadata_response = await self._make_request(
                "POST",
                "https://api.adapta.one/api/file/metadata",
                headers=arquivo_headers,
                json=metadata_payload
            )

            metadata_data = metadata_response.json()
            #print(metadata_data)
            logger.debug(f"Arquivo finalizado com sucesso: {metadata_data}")
            return metadata_data.get("data", metadata_data)
                
        except FileNotFoundError:
            logger.error(f"Arquivo não encontrado: {caminho_arquivo}")
            return None
        except ValueError as e:
            # Re-raise ValueError para formatos não suportados
            raise
        except Exception as e:
            logger.error(f"Erro ao carregar arquivo: {e}")
            return None
    
    async def excluir_arquivo(self, id_arquivo: str) -> Optional[str]:
        """Exclui um arquivo da API pelo seu ID.
        
        Args:
            id_arquivo: ID do arquivo a ser excluído.
            
        Returns:
            Status da operação ou None em caso de erro.
        """
        try:
            url = f'https://api.adapta.one/api/file/{id_arquivo}'
            await self._ensure_client()
            await self._update_session()
            
            arquivo_headers = self.headers.copy()
            arquivo_headers['origin'] = "https://app.adapta.one"
            arquivo_headers['referer'] = "https://app.adapta.one/"
            arquivo_headers['authorization'] = f"Bearer {self.cookies['__session']}"
            
            response = await self._make_request("DELETE", url, headers=arquivo_headers)
            data = response.json()
            
            resultado = data.get("data", data.get("status", data))
            logger.debug(f"Arquivo excluído com sucesso. Resultado: {resultado}")
            return resultado
            
        except Exception as e:
            logger.error(f"Erro ao excluir arquivo: {e}")
            return None
    
    async def call_model(
        self,
        messages: List[Dict[str, str]],
        model: str = "GPT_5",
        new_line: bool = True,
        searchType: Optional[str] = None,
        tool: Optional[str] = None,
        chat_id: Optional[str] = None,
        file_ids: Optional[List[Any]] = None
    ) -> Optional[str]:
        """Chama um modelo específico da API Adapta.one.
        
        Args:
            messages: Lista de mensagens para o modelo.
            model: Nome do modelo (GPT, GEMINI, CLAUDE, etc.).
            new_line: Se True, mantém quebras de linha; caso contrário, substitui por espaços.
            searchType: O tipo de pesquisa a ser realizada (ex: 'normal', 'scientific').
            tool: A ferramenta a ser usada (ex: 'PERFORM_RESEARCH').
            chat_id: O ID do chat a ser usado para manter a conversa.
            file_ids: Lista opcional de IDs de arquivos a serem anexados na requisição.
            
        Returns:
            Conteúdo da resposta extraído ou None se houver erro.
        """
        try:
            logger.debug(f"Iniciando call_model para modelo: {model}")
            logger.debug(f"Número de mensagens: {len(messages)}")

            arquivos_resolvidos = await self._resolve_files_payload(file_ids)
            mensagens_resolvidas = await self._resolve_messages_payload(messages, arquivos_resolvidos)
            
            response = await self._create_conversation_with_retry(
                mensagens_resolvidas,
                model,
                searchType=searchType,
                tool=tool,
                chat_id=chat_id,
                files_payload=arquivos_resolvidos
            )
            
            if response:
                logger.debug(f"Conversa criada com sucesso. Status: {response.status_code}")
                logger.debug(f"Tamanho da resposta: {len(response.text)} caracteres")
                
                if response.status_code == 200:
                    content = self._extract_content(response.text, new_line)
                    if content:
                        logger.debug(f"Conteúdo extraído com sucesso: {len(content)} caracteres")
                        return content
                    else:
                        logger.error("Conteúdo extraído está vazio")
                        return None
                else:
                    logger.error(f"Status code não é 200: {response.status_code}")
                    return None
            else:
                logger.error("Resposta da conversa é None")
                return None
            
        except Exception as e:
            logger.error(f"Erro ao chamar modelo {model}: {e}")
            logger.error(f"Tipo do erro: {type(e).__name__}")
            return None
    
    async def _create_conversation(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        searchType: Optional[str] = None,
        tool: Optional[str] = None,
        chat_id: Optional[str] = None,
        files_payload: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[httpx.Response]:
        """Cria uma nova conversa na API.
        
        Args:
            messages: Lista de mensagens da conversa.
            model: Modelo de IA a ser usado.
            searchType: O tipo de pesquisa a ser realizada.
            tool: A ferramenta a ser usada.
            chat_id: O ID do chat a ser usado para manter a conversa.
            files_payload: Lista opcional com os arquivos anexados ao chat.
            
        Returns:
            Resposta da API ou None em caso de erro.
        """
        try:
            logger.debug(f"Iniciando criação de conversa para modelo: {model}")
            
            await self._ensure_client()
            logger.debug("Cliente HTTP garantido")
            
            await self._update_session()
            logger.debug("Sessão atualizada")
            
            # Verificar token após atualização
            if '__session' not in self.cookies:
                logger.error("Token __session não encontrado após atualização de sessão")
                raise ValueError("Token de sessão não está disponível")
            
            token = self.cookies['__session']
            logger.debug(f"Token disponível: {token[:20]}... ({len(token)} caracteres)")
            
            # Use provided chat_id or generate a new one
            current_chat_id = chat_id if chat_id else self._generate_random_id()
            logger.debug(f"Chat ID usado: {current_chat_id}")

            arquivos_payload = files_payload or []
            mensagens_payload = messages
            
            payload = {
                "messages": mensagens_payload,
                "files": arquivos_payload,
                "chatAiModel": model,
                "chatId": current_chat_id,
                "chatType": "CHAT",
                "agentId": None,
                "folderId": None,
                "tool": tool or None, # Use provided tool or default to None
                "imageModel": "FLUX",
                "imageAspectRatio": "ONE_TO_ONE",
                "searchType": searchType or None, # Use provided searchType or default to None
                "flowType": None,
                "shouldEditMessage": False,
                "shouldGenerateNewFileFromSheetAssistant": False,
                "enhanceResponse": False,
            }
            
            logger.debug(f"Payload preparado: {len(messages)} mensagens, modelo: {model}")
            
            headers = self.headers.copy()
            headers['content-type'] = 'application/json'
            headers['referer'] = "https://app.adapta.one/"
            headers['authorization'] = f"Bearer {token}"
            headers['x-user-id'] = self.user_id
            
            logger.debug(f"Headers preparados: {list(headers.keys())}")
            logger.debug(f"Authorization header: Bearer {token[:20]}...")
            
            #url = "https://api.adapta.one/api/chat/conversation"
            url = "https://api.adapta.one/api/preview/chat/conversation"
            logger.debug(f"URL da requisição: {url}")
            
            if not self.client:
                logger.error("Cliente HTTP não inicializado")
                raise RuntimeError("Cliente HTTP não inicializado")
            
            # Validar se o token está presente
            if '__session' not in self.cookies or not self.cookies['__session']:
                logger.error("Token de sessão não está disponível antes da requisição")
                raise ValueError("Token de sessão não está disponível")
            
            logger.debug("Iniciando requisição HTTP...")
            
            try:
                response = await self.client.request(
                    method="POST",
                    url=url,
                    headers=headers,
                    cookies=self.cookies,
                    json=payload
                )
                logger.debug(f"Resposta recebida: Status {response.status_code}")
                
                response.raise_for_status()
                logger.debug("Requisição bem-sucedida")
                
                # Apaga a conversa APENAS se o chat_id foi gerado por esta chamada (não persistente)
                if not chat_id:
                    logger.debug("Iniciando exclusão da conversa temporária...")
                    try:
                        await self._delete_conversations([current_chat_id])
                        logger.debug("Conversa temporária excluída com sucesso")
                    except Exception as delete_error:
                        logger.warning(f"Erro ao excluir conversa temporária {current_chat_id} (não crítico): {delete_error}")
                        logger.warning(f"Tipo do erro de exclusão: {type(delete_error).__name__}")
                
                return response
                
            except httpx.TimeoutException as e:
                logger.error(f"Timeout na requisição: {e}")
                logger.error(f"Detalhes do timeout: {type(e).__name__}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"Erro HTTP na requisição: {e.response.status_code} - {e.response.text[:200]}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Erro de requisição: {e}")
                logger.error(f"Tipo do erro de requisição: {type(e).__name__}")
                raise
            except Exception as e:
                logger.error(f"Erro inesperado na requisição: {e}")
                logger.error(f"Tipo do erro inesperado: {type(e).__name__}")
                raise
            
        except Exception as e:
            logger.error(f"Erro ao criar conversa: {e}")
            logger.error(f"Tipo do erro: {type(e).__name__}")
            return None
    
    async def _delete_conversations(self, chat_ids: List[str]) -> None:
        """Apaga conversas especificadas pelos seus IDs.
        
        Args:
            chat_ids: Lista de IDs das conversas a serem apagadas.
        """
        try:
            logger.debug(f"Iniciando exclusão de conversas: {chat_ids}")
            
            await self._ensure_client()
            logger.debug("Cliente HTTP garantido para exclusão")
            
            await self._update_session()
            logger.debug("Sessão atualizada para exclusão")
            
            headers = self.headers.copy()
            headers['content-type'] = 'application/json'
            headers['referer'] = "https://app.adapta.one/"
            headers['authorization'] = f"Bearer {self.cookies['__session']}"
            if self.session_id:
                headers['x-session-id'] = self.session_id
            headers['x-user-id'] = self.user_id
            
            logger.debug(f"Headers para exclusão preparados: {list(headers.keys())}")
            
            payload = {"chatIds": chat_ids}
            url = "https://api.adapta.one/api/chat/delete"
            
            logger.debug(f"URL de exclusão: {url}")
            logger.debug(f"Payload de exclusão: {payload}")
            
            if not self.client:
                logger.error("Cliente HTTP não inicializado para exclusão")
                raise RuntimeError("Cliente HTTP não inicializado")
            
            # Validar se o token está presente
            if '__session' not in self.cookies or not self.cookies['__session']:
                logger.error("Token de sessão não está disponível para exclusão")
                raise ValueError("Token de sessão não está disponível")
            
            logger.debug("Iniciando requisição de exclusão...")
            
            try:
                response = await self.client.request(
                    method="DELETE",
                    url=url,
                    headers=headers,
                    cookies=self.cookies,
                    json=payload
                )
                logger.debug(f"Resposta de exclusão recebida: Status {response.status_code}")
                
                response.raise_for_status()
                logger.debug("Exclusão bem-sucedida")
                
            except httpx.TimeoutException as e:
                logger.error(f"Timeout na exclusão: {e}")
                logger.error(f"Detalhes do timeout de exclusão: {type(e).__name__}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"Erro HTTP na exclusão: {e.response.status_code} - {e.response.text[:200]}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Erro de requisição na exclusão: {e}")
                logger.error(f"Tipo do erro de requisição na exclusão: {type(e).__name__}")
                raise
            except Exception as e:
                logger.error(f"Erro inesperado na exclusão: {e}")
                logger.error(f"Tipo do erro inesperado na exclusão: {type(e).__name__}")
                raise
            
        except Exception as e:
            logger.warning(f"Erro ao apagar conversas: {e}")
            logger.warning(f"Tipo do erro: {type(e).__name__}")
    
    def _extract_content(self, response_text: str, new_line: bool = True) -> Optional[str]:
        """Extrai o conteúdo da resposta da API.
        
        Args:
            response_text: Texto da resposta da API.
            new_line: Se True, mantém quebras de linha; caso contrário, substitui por espaços.
            
        Returns:
            Conteúdo extraído ou None se não encontrar.
        """
        content_parts = []
        
        for line in response_text.strip().splitlines():
            if line.startswith("0:\""):
                content = line[3:-1]  # Remove "0:", aspas e espaços extras
                if new_line:
                    content_parts.append(content.replace('\\n', '\n').replace('\\"', '\"'))
                else:
                    content_parts.append(content.replace('\\n', ' ').replace('\\"', ' '))
        
        return ''.join(content_parts) if content_parts else None
    
    async def health_check(self) -> bool:
        """Verifica se o cliente está funcionando corretamente.
        
        Returns:
            True se o cliente estiver funcionando, False caso contrário.
        """
        try:
            await self._ensure_client()
            if not self.session_id:
                await self._update_credentials()
            return True
        except Exception as e:
            logger.error(f"Health check falhou: {e}")
            return False
    
    async def _create_conversation_with_retry(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        max_retries: int = 3,
        delay: float = 1.0,
        searchType: Optional[str] = None,
        tool: Optional[str] = None,
        chat_id: Optional[str] = None,
        files_payload: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[httpx.Response]:
        """Cria uma nova conversa na API com retry automático.
        
        Args:
            messages: Lista de mensagens da conversa.
            model: Modelo de IA a ser usado.
            max_retries: Número máximo de tentativas.
            delay: Delay entre tentativas em segundos.
            searchType: O tipo de pesquisa a ser realizada.
            tool: A ferramenta a ser usada.
            chat_id: O ID do chat a ser usado para manter a conversa.
            file_ids: Lista opcional de IDs de arquivos anexados ao chat.
            
        Returns:
            Resposta da API ou None se todas as tentativas falharem.
        """
        last_error = None

        # Alterna entre os modelos Claude e Gemini nas retentativas quando um deles for solicitado
        alternate_cycle = None
        if model in {"CLAUDE_4", "GEMINI"}:
            other_model = "GEMINI" if model == "CLAUDE_4" else "CLAUDE_4"
            alternate_cycle = [model, other_model]
        
        for attempt in range(max_retries):
            current_model = model
            if alternate_cycle:
                current_model = alternate_cycle[attempt % len(alternate_cycle)]

            try:
                logger.debug(
                    f"Tentativa {attempt + 1}/{max_retries} para criar conversa usando modelo {current_model}"
                )
                
                response = await self._create_conversation(
                    messages,
                    current_model,
                    searchType=searchType,
                    tool=tool,
                    chat_id=chat_id,
                    files_payload=files_payload
                )
                
                if response:
                    logger.debug(f"Conversa criada com sucesso na tentativa {attempt + 1}")
                    return response
                else:
                    logger.error(f"Tentativa {attempt + 1} falhou: resposta é None")
                    
            except Exception as e:
                last_error = e
                logger.error(f"Tentativa {attempt + 1} falhou: {e}")
                
                if attempt < max_retries - 1:
                    logger.debug(f"Aguardando {delay} segundos antes da próxima tentativa...")
                    await asyncio.sleep(delay)
                    # Aumenta o delay exponencialmente
                    delay *= 1.5
        
        logger.error(f"Todas as {max_retries} tentativas falharam. Último erro: {last_error}")
        return None 
