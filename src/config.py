﻿"""Modulo de configuracao."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes da aplicacao carregadas do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Configuracoes do Adapta.one
    adapta_cookies_str: str = Field(..., description="Cookies de autenticacao do Adapta.one")
    adapta_session_id: Optional[str] = Field(
        default=None,
        description="ID de sessao do Adapta.one a partir da variavel ADAPTA_SESSION_ID",
    )

class SettingsManager:
    """Gerencia o carregamento dinamico das configuracoes."""

    def __init__(self, env_path: Optional[Path] = None) -> None:
        self._env_path = env_path or Path(__file__).resolve().parents[1] / ".env"
        self._lock = Lock()
        self._settings = self._load_settings()
        self._env_timestamp = self._get_env_timestamp()

    def _get_env_timestamp(self) -> Optional[float]:
        try:
            return self._env_path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _load_settings(self) -> Settings:
        load_dotenv(self._env_path, override=True)
        return Settings()

    def _refresh_if_needed(self) -> None:
        current = self._get_env_timestamp()
        if current != self._env_timestamp:
            with self._lock:
                current = self._get_env_timestamp()
                if current != self._env_timestamp:
                    self._settings = self._load_settings()
                    self._env_timestamp = current

    def reload(self) -> Settings:
        """Recarrega explicitamente as configuracoes a partir do .env."""
        with self._lock:
            self._settings = self._load_settings()
            self._env_timestamp = self._get_env_timestamp()
            return self._settings

    def __getattr__(self, item: str) -> Any:
        self._refresh_if_needed()
        return getattr(self._settings, item)

    def __repr__(self) -> str:  # pragma: no cover - comportamento trivial
        self._refresh_if_needed()
        return repr(self._settings)

    def model_dump(self, *args: Any, **kwargs: Any) -> Any:
        self._refresh_if_needed()
        return self._settings.model_dump(*args, **kwargs)


# Instancia global das configuracoes com recarga automatica
settings = SettingsManager()
