from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from utils.logger import logger

DEFAULT_CACHE_DIR = Path("indexes") / "docling_cache"
MAX_TEXT_CHARS = 60_000

try:
    from docling.document_converter import DocumentConverter
except ImportError:  # pragma: no cover - docling available only in production envs
    DocumentConverter = None  # type: ignore[assignment]


class DoclingConversionError(RuntimeError):
    """Erro ao converter PDF via Docling."""


@dataclass
class DoclingTextResult:
    text: str
    cache_path: Path
    source_path: Path


_converter: Optional["DocumentConverter"] = None


def convert_pdf_to_text(
    pdf_path: Union[str, Path],
    *,
    max_chars: int = MAX_TEXT_CHARS,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> DoclingTextResult:
    """Converte um PDF em texto simples usando Docling e devolve o trecho limitado."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado para conversao: {path}")
    cache_path = _resolve_cache_path(path, cache_dir)
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8")
        logger.debug("Docling cache reutilizado para %s -> %s", path.name, cache_path)
        return DoclingTextResult(text=_trim_text(text, max_chars), cache_path=cache_path, source_path=path)

    converter = _get_converter()
    logger.info("Convertendo %s via Docling...", path.name)
    result = converter.convert(str(path))
    document = getattr(result, "document", None)
    if document is None:
        raise DoclingConversionError(f"Docling nao retornou documento para {path}")
    export_fn = getattr(document, "export_to_text", None) or getattr(document, "export_to_markdown", None)
    if export_fn is None:
        raise DoclingConversionError("API Docling mudou: export_to_text/export_to_markdown ausentes.")
    text = export_fn()
    cache_path.write_text(text, encoding="utf-8")
    return DoclingTextResult(text=_trim_text(text, max_chars), cache_path=cache_path, source_path=path)


def _get_converter() -> "DocumentConverter":
    if DocumentConverter is None:
        raise DoclingConversionError(
            "Dependencia 'docling' nao encontrada. Execute `poetry install` para habilitar a conversao."
        )
    global _converter
    if _converter is None:
        DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _converter = DocumentConverter()
    return _converter


def _resolve_cache_path(source_path: Path, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = source_path.stat()
    cache_key = f"{source_path.resolve()}::{stat.st_mtime_ns}"
    digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
    return cache_dir / f"{source_path.stem}_{digest}.txt"


def _trim_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    suffix = f"\n\n[Trecho truncado apos {max_chars} caracteres]"
    return text[:max_chars] + suffix
