"""Utilities to validate LLM responses."""

from __future__ import annotations

import unicodedata
from typing import Optional


ERROR_SNIPPET = "nao consigo processar o arquivo"


class ResponseValidationError(RuntimeError):
    """Raised when the model response indicates it could not process the input file."""


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


def requires_processing_retry(response_text: Optional[str]) -> bool:
    """Return True when the model response contains the known failure message."""
    if not response_text:
        return False
    normalized = _normalize(str(response_text))
    return ERROR_SNIPPET in normalized


__all__ = ["ResponseValidationError", "requires_processing_retry"]
