import asyncio
import atexit
import threading
from typing import Any, Optional

from utils.logger import logger


async def shutdown_adapta_client(client: Any, *, label: str = "adapta_client") -> None:
    """Executes logout + close safeguards for an Adapta client instance."""
    if client is None:
        return

    session_id = getattr(client, "session_id", None)
    if isinstance(session_id, str) and session_id:
        logger.info("Encerrando sessao {} para {}", session_id, label)
    else:
        logger.info("Encerrando sessao (id desconhecido) para {}", label)

    logout = getattr(client, "logout", None)
    if callable(logout):
        try:
            await logout()
            logger.info("Logout concluido para {}", label)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao executar logout para {}: {}", label, exc)

    close = getattr(client, "close", None)
    if callable(close):
        try:
            await close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao fechar cliente {}: {}", label, exc)


class LogoutGuard:
    """Registers graceful shutdown hooks that guarantee logout/close."""

    def __init__(self, client: Any, *, label: str = "adapta_client") -> None:
        self._client = client
        self._label = label
        self._lock = threading.Lock()
        self._registered = False
        self._closed = False

    def register(self) -> None:
        if self._registered:
            return
        self._registered = True
        atexit.register(self._run_sync_cleanup)

    async def close_now(self) -> None:
        if self._mark_closed():
            return
        await shutdown_adapta_client(self._client, label=self._label)

    def _run_sync_cleanup(self) -> None:
        if self._mark_closed():
            return

        async def _runner() -> None:
            await shutdown_adapta_client(self._client, label=self._label)

        try:
            asyncio.run(_runner())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_runner())
            finally:
                loop.close()

    def _mark_closed(self) -> bool:
        with self._lock:
            if self._closed:
                return True
            self._closed = True
            return False
