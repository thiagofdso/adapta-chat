import argparse
import asyncio
import hashlib
import json
import os
import re
import requests
import sqlite3
import ssl
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure src is importable when running from repo root.
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generators_v2.adapta.claude_45_sonnet_generator import Claude45SonnetGenerator
from utils.logger import logger
from utils.response_validator import requires_processing_retry
from utils.text_cleaner import remove_think_tags
from utils.session_guard import LogoutGuard

ssl._create_default_https_context = ssl._create_unverified_context
old_request = requests.Session.request


def new_request(self, *args, **kwargs):
    kwargs["verify"] = False
    return old_request(self, *args, **kwargs)


requests.Session.request = new_request


PROMPTS_DIR = BASE_DIR / "microaprendizado"
OUTPUT_ROOT = BASE_DIR / "microaprendizado_output"
DB_PATH = BASE_DIR / "data" / "microaprendizado.db"

STATUS_PENDING = 1
STATUS_RUNNING = 2
STATUS_DONE = 3

RETRY_LIMIT = 4
RETRY_INITIAL_DELAY = 2.0
MIN_MODEL_CALL_DELAY_SECONDS = 60.0
DOC_TEXT_DEFAULT_MAX_CHARS = 60_000


class DoclingSupportUnavailable(RuntimeError):
    """Disparado quando o modo Docling e requisitado mas a dependencia nao esta disponivel."""


@dataclass(frozen=True)
class _DoclingSupport:
    converter: Any
    error_cls: type[BaseException]
    max_chars: int


@dataclass(frozen=True)
class SourceMaterial:
    mode: str
    prompt_block: str
    files: Optional[List[Dict[str, Any]]] = None
    txt_path: Optional[Path] = None


_docling_support_cache: Optional[_DoclingSupport] = None


def _slugify(text: str) -> str:
    if not text:
        return "aula"
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^\w\s-]", "", ascii_text)
    ascii_text = re.sub(r"[\s-]+", "_", ascii_text).strip("_")
    return ascii_text or "aula"


def _hash_path(path: str) -> str:
    return hashlib.md5(path.encode("utf-8")).hexdigest()[:8]


def _build_output_dir(pdf_path: str) -> Path:
    stem = Path(pdf_path).stem
    slug = _slugify(stem)
    return OUTPUT_ROOT / f"{slug}_{_hash_path(os.path.abspath(pdf_path))}"


def _get_docling_support() -> _DoclingSupport:
    global _docling_support_cache
    if _docling_support_cache is not None:
        return _docling_support_cache
    try:
        from utils import docling_converter as docling_module
    except Exception as exc:
        raise DoclingSupportUnavailable(
            "Modo docling requer a dependencia 'docling'. Execute `poetry install` antes de usar --mode docling."
        ) from exc

    converter = getattr(docling_module, "convert_pdf_to_text", None)
    error_cls = getattr(docling_module, "DoclingConversionError", RuntimeError)
    max_chars = getattr(docling_module, "MAX_TEXT_CHARS", DOC_TEXT_DEFAULT_MAX_CHARS)
    if converter is None:
        raise DoclingSupportUnavailable("Modulo utils.docling_converter nao expoe convert_pdf_to_text.")

    _docling_support_cache = _DoclingSupport(converter=converter, error_cls=error_cls, max_chars=max_chars)
    return _docling_support_cache


def _truncate_text(text: str, max_chars: int = DOC_TEXT_DEFAULT_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    suffix = f"\n\n[Trecho truncado apos {max_chars} caracteres]"
    return text[:max_chars] + suffix


def _ensure_dirs(output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    subdirs = {
        "base": output_dir / "aulas_base",
        "aulas": output_dir / "aulas",
        "roteiros": output_dir / "roteiros",
        "perguntas": output_dir / "perguntas",
        "relatorios": output_dir / "relatorios",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return subdirs


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_db() -> None:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_path TEXT NOT NULL UNIQUE,
            pdf_name TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            status_id INTEGER NOT NULL DEFAULT 1,
            stage1_status INTEGER NOT NULL DEFAULT 1,
            stage2_status INTEGER NOT NULL DEFAULT 1,
            stage3_status INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            microaula_id TEXT NOT NULL,
            titulo TEXT NOT NULL,
            slug TEXT NOT NULL,
            sessao_id TEXT,
            sessao_titulo TEXT,
            ordem_sessao INTEGER,
            ordem_microaula INTEGER,
            microaula_json TEXT NOT NULL,
            step4_status INTEGER NOT NULL DEFAULT 1,
            step5_status INTEGER NOT NULL DEFAULT 1,
            step6_status INTEGER NOT NULL DEFAULT 1,
            step7_status INTEGER NOT NULL DEFAULT 1,
            step8_status INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, microaula_id),
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        """
    )
    conn.commit()
    conn.close()


def get_or_create_job(pdf_path: str, output_dir: Path) -> sqlite3.Row:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE pdf_path = ?", (pdf_path,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row

    pdf_name = Path(pdf_path).name
    cursor.execute(
        """
        INSERT INTO jobs (pdf_path, pdf_name, output_dir, status_id, stage1_status, stage2_status, stage3_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (pdf_path, pdf_name, str(output_dir), STATUS_PENDING, STATUS_PENDING, STATUS_PENDING, STATUS_PENDING),
    )
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE pdf_path = ?", (pdf_path,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_job_stage(job_id: int, stage: int, status: int) -> None:
    column = f"stage{stage}_status"
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE jobs SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, job_id),
    )
    conn.commit()
    conn.close()


def update_job_status(job_id: int, status: int) -> None:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET status_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, job_id),
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def fetch_lessons(job_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM lessons
        WHERE job_id = ?
        ORDER BY COALESCE(ordem_sessao, 0), COALESCE(ordem_microaula, 0)
        """,
        (job_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def upsert_lessons(job_id: int, lessons: List[Dict[str, Any]]) -> None:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lessons WHERE job_id = ?", (job_id,))
    existing_rows = {row["microaula_id"]: row for row in cursor.fetchall()}

    for lesson in lessons:
        microaula_id = lesson["microaula_id"]
        microaula_json = lesson["microaula_json"]
        existing = existing_rows.get(microaula_id)

        if existing:
            reset_steps = microaula_json != existing["microaula_json"]
            cursor.execute(
                """
                UPDATE lessons
                SET titulo = ?,
                    slug = ?,
                    sessao_id = ?,
                    sessao_titulo = ?,
                    ordem_sessao = ?,
                    ordem_microaula = ?,
                    microaula_json = ?,
                    step4_status = ?,
                    step5_status = ?,
                    step6_status = ?,
                    step7_status = ?,
                    step8_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND microaula_id = ?
                """,
                (
                    lesson["titulo"],
                    lesson["slug"],
                    lesson.get("sessao_id"),
                    lesson.get("sessao_titulo"),
                    lesson.get("ordem_sessao"),
                    lesson.get("ordem_microaula"),
                    microaula_json,
                    STATUS_PENDING if reset_steps else existing["step4_status"],
                    STATUS_PENDING if reset_steps else existing["step5_status"],
                    STATUS_PENDING if reset_steps else existing["step6_status"],
                    STATUS_PENDING if reset_steps else existing["step7_status"],
                    STATUS_PENDING if reset_steps else existing["step8_status"],
                    job_id,
                    microaula_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO lessons (
                    job_id,
                    microaula_id,
                    titulo,
                    slug,
                    sessao_id,
                    sessao_titulo,
                    ordem_sessao,
                    ordem_microaula,
                    microaula_json,
                    step4_status,
                    step5_status,
                    step6_status,
                    step7_status,
                    step8_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    microaula_id,
                    lesson["titulo"],
                    lesson["slug"],
                    lesson.get("sessao_id"),
                    lesson.get("sessao_titulo"),
                    lesson.get("ordem_sessao"),
                    lesson.get("ordem_microaula"),
                    microaula_json,
                    STATUS_PENDING,
                    STATUS_PENDING,
                    STATUS_PENDING,
                    STATUS_PENDING,
                    STATUS_PENDING,
                ),
            )

    conn.commit()
    conn.close()


def update_lesson_step(lesson_id: int, step: int, status: int) -> None:
    column = f"step{step}_status"
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE lessons SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, lesson_id),
    )
    conn.commit()
    conn.close()


def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1].strip()


def _safe_json_loads(candidate: str) -> Dict[str, Any]:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
        return json.loads(cleaned)


def _render_questions_markdown(questions: Dict[str, Any]) -> str:
    titulo = questions.get("titulo_microaula") or questions.get("microaula_id") or "Perguntas"
    payload = json.dumps(questions, ensure_ascii=False, indent=2)
    return f"# Perguntas - {titulo}\n\n```json\n{payload}\n```\n"


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _find_marker(prompt: str, marker: str) -> int:
    direct = prompt.find(marker)
    if direct != -1:
        return direct
    prompt_norm = _strip_accents(prompt)
    marker_norm = _strip_accents(marker)
    return prompt_norm.find(marker_norm)


def _find_marker_after(prompt: str, marker: str, start_idx: int) -> int:
    if start_idx < 0:
        return _find_marker(prompt, marker)
    direct = prompt.find(marker, start_idx)
    if direct != -1:
        return direct
    prompt_norm = _strip_accents(prompt)
    marker_norm = _strip_accents(marker)
    return prompt_norm.find(marker_norm, start_idx)


def _replace_between(prompt: str, start_marker: str, end_marker: str, new_block: str) -> str:
    start_idx = _find_marker(prompt, start_marker)
    if start_idx == -1:
        logger.warning("Marcador inicial nao encontrado: {}", start_marker)
        return f"{prompt}\n\n{new_block}\n"
    start_idx += len(start_marker)
    end_idx = _find_marker_after(prompt, end_marker, start_idx)
    if end_idx == -1 or end_idx <= start_idx:
        logger.warning("Marcador final nao encontrado: {}", end_marker)
        return f"{prompt[:start_idx]}\n\n{new_block}\n"
    return f"{prompt[:start_idx]}\n\n{new_block}\n\n{prompt[end_idx:]}"


def _load_prompt(file_name: str) -> str:
    path = PROMPTS_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt nao encontrado: {path}")
    return path.read_text(encoding="utf-8")


def _inject_book_content(prompt: str, content_block: str) -> str:
    return re.sub(
        r"\[INSERIR.*?CONTE[UÚ]DO DO LIVRO AQUI\]",
        content_block,
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _replace_book_source_reference(prompt: str, source_block: str) -> str:
    replacements = (
        "LIVRO EM ANEXO, USE A FERRAMENTA DE LEITURA COMPLETA",
        "LIVRO EM ANEXO (PDF).",
    )
    updated_prompt = prompt
    replaced = False
    for needle in replacements:
        if needle in updated_prompt:
            updated_prompt = updated_prompt.replace(needle, source_block)
            replaced = True
    if replaced:
        return updated_prompt
    return _replace_between(prompt, "CONTEÚDO ORIGINAL DO LIVRO", "PRINCÍPIOS DO MICROAPRENDIZADO", source_block)


async def _call_model_text(
    generator: Claude45SonnetGenerator,
    prompt: str,
    *,
    files: Optional[List[Dict[str, Any]]] = None,
    retries: int = RETRY_LIMIT,
    keep_chat: bool = False,
) -> str:
    delay = RETRY_INITIAL_DELAY
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            response = await generator.call_model_with_messages(
                [{"role": "user", "content": prompt}],
                files=files,
            )
            if not keep_chat:
                try:
                    await _cleanup_chat(generator)
                except Exception:
                    pass
        except Exception as exc:
            last_exc = exc
            logger.warning("Falha ao chamar modelo (tentativa {}): {}", attempt, exc)
            if attempt < retries:
                sleep_time = max(delay, MIN_MODEL_CALL_DELAY_SECONDS)
                await asyncio.sleep(sleep_time)
                delay = max(delay * 2, MIN_MODEL_CALL_DELAY_SECONDS)
            continue

        cleaned = remove_think_tags(str(response))
        if requires_processing_retry(cleaned):
            logger.warning(
                "Resposta do modelo indicou que não foi possível processar o arquivo (tentativa {}/{})",
                attempt,
                retries,
            )
            if attempt < retries:
                sleep_time = max(delay, MIN_MODEL_CALL_DELAY_SECONDS)
                await asyncio.sleep(sleep_time)
                delay = max(delay * 2, MIN_MODEL_CALL_DELAY_SECONDS)
                continue
            raise RuntimeError("Modelo nao conseguiu processar o arquivo.")
        return cleaned
    raise RuntimeError("Falha ao chamar modelo.") from last_exc


async def _call_model_json(
    generator: Claude45SonnetGenerator,
    prompt: str,
    *,
    files: Optional[List[Dict[str, Any]]] = None,
    retries: int = RETRY_LIMIT,
    keep_chat: bool = False,
) -> Tuple[Dict[str, Any], str]:
    augmented_prompt = prompt
    for attempt in range(1, retries + 1):
        response = await _call_model_text(
            generator,
            augmented_prompt,
            files=files,
            retries=1,
            keep_chat=keep_chat,
        )
        candidate = _extract_json_candidate(response) or response
        try:
            parsed = _safe_json_loads(candidate)
            return parsed, candidate
        except Exception as exc:
            logger.warning("JSON invalido na tentativa {}: {}", attempt, exc)
            if attempt >= retries:
                raise
            augmented_prompt = (
                prompt
                + "\n\nResponda APENAS com JSON valido no formato solicitado, sem explicacoes ou markdown."
            )
    raise RuntimeError("Falha ao obter JSON valido do modelo.")


def _build_microaula_filename(microaula_id: str, titulo: str) -> str:
    slug = _slugify(titulo)
    return f"{microaula_id}_{slug}.md"


def _extract_microaulas(curso: Dict[str, Any]) -> List[Dict[str, Any]]:
    curso_data = curso.get("curso") or {}
    sessoes = curso_data.get("sessoes") or []
    lessons: List[Dict[str, Any]] = []
    for sessao in sessoes:
        sessao_id = sessao.get("id")
        sessao_titulo = sessao.get("titulo")
        sessao_ordem = sessao.get("ordem")
        microaulas = sessao.get("microaulas") or []
        for micro in microaulas:
            micro_id = micro.get("id")
            if not micro_id:
                ordem_micro = micro.get("ordem") or (len(lessons) + 1)
                sessao_ordem_fmt = int(sessao_ordem or 0)
                micro_id = f"aula_{sessao_ordem_fmt:02d}_{int(ordem_micro):02d}"
                micro = dict(micro)
                micro["id"] = micro_id
            titulo = micro.get("titulo") or micro_id or "Microaula"
            lessons.append(
                {
                    "microaula_id": micro_id,
                    "titulo": titulo,
                    "slug": _slugify(titulo),
                    "sessao_id": sessao_id,
                    "sessao_titulo": sessao_titulo,
                    "ordem_sessao": sessao_ordem,
                    "ordem_microaula": micro.get("ordem"),
                    "microaula_json": json.dumps(micro, ensure_ascii=False, indent=2),
                    "microaula_obj": micro,
                }
            )
    lessons.sort(key=lambda item: (item.get("ordem_sessao") or 0, item.get("ordem_microaula") or 0))
    return lessons


def _normalize_job_stage(job: Dict[str, Any], stage: int, file_path: Path) -> None:
    column = f"stage{stage}_status"
    current = job.get(column)
    if file_path.exists():
        if current != STATUS_DONE:
            update_job_stage(job["id"], stage, STATUS_DONE)
    else:
        if current == STATUS_DONE:
            update_job_stage(job["id"], stage, STATUS_PENDING)


def _normalize_lesson_steps(lesson: Dict[str, Any], paths: Dict[str, Path]) -> None:
    mapping = {
        4: ("step4_status", paths["base"]),
        5: ("step5_status", paths["aula"]),
        6: ("step6_status", paths["audio"]),
        7: ("step7_status", paths["perguntas"]),
        8: ("step8_status", paths["relatorio"]),
    }
    for step, (column, file_path) in mapping.items():
        current = lesson.get(column)
        if file_path.exists():
            if current != STATUS_DONE:
                update_lesson_step(lesson["id"], step, STATUS_DONE)
        else:
            if current == STATUS_DONE:
                update_lesson_step(lesson["id"], step, STATUS_PENDING)


def _build_paths_for_lesson(output_dirs: Dict[str, Path], microaula_id: str, titulo: str) -> Dict[str, Path]:
    filename = _build_microaula_filename(microaula_id, titulo)
    return {
        "base": output_dirs["base"] / filename,
        "aula": output_dirs["aulas"] / filename,
        "audio": output_dirs["roteiros"] / f"{microaula_id}_audio.md",
        "perguntas": output_dirs["perguntas"] / f"{microaula_id}_perguntas.json",
        "perguntas_md": output_dirs["perguntas"] / f"{microaula_id}_perguntas.md",
        "relatorio": output_dirs["relatorios"] / f"{microaula_id}_perguntas_relatorio.md",
    }


async def _ensure_upload(
    generator: Claude45SonnetGenerator,
    pdf_path: str,
    upload_cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    cached = upload_cache.get(pdf_path)
    if cached:
        return cached
    logger.info("Fazendo upload do PDF: {}", pdf_path)
    upload_info = await generator.client.upload_arquivo(pdf_path)
    upload_cache[pdf_path] = upload_info
    return upload_info


async def _cleanup_chat(generator: Claude45SonnetGenerator) -> None:
    client = getattr(generator, "client", None)
    if client is None:
        return
    chat_id = getattr(client, "last_chat_id", None)
    if not chat_id:
        return
    try:
        await client.excluir_chat(chat_id)
        logger.debug("Chat {} excluido com sucesso.", chat_id)
    except Exception as exc:
        logger.warning("Falha ao excluir chat {}: {}", chat_id, exc)


async def _build_source_material(
    generator: Claude45SonnetGenerator,
    pdf_path: str,
    mode: str,
    output_dir: Path,
    upload_cache: Dict[str, Dict[str, Any]],
) -> SourceMaterial:
    normalized_mode = mode.lower()
    if normalized_mode == "upload":
        upload_info = await _ensure_upload(generator, pdf_path, upload_cache)
        return SourceMaterial(
            mode=normalized_mode,
            prompt_block="LIVRO EM ANEXO (PDF).",
            files=[upload_info],
        )

    if normalized_mode != "docling":
        raise ValueError(f"Modo invalido: {mode}")

    support = _get_docling_support()
    result = support.converter(pdf_path, max_chars=support.max_chars)
    text = _truncate_text(getattr(result, "text", ""), max_chars=support.max_chars)
    if not text.strip():
        raise support.error_cls("Docling nao retornou texto utilizavel para o microaprendizado.")

    txt_path = output_dir / f"{Path(pdf_path).stem}.txt"
    txt_path.write_text(text, encoding="utf-8")
    logger.info("Arquivo convertido para TXT em {}", txt_path)
    prompt_block = (
        f"LIVRO CONVERTIDO PARA TXT ({txt_path.name}). USE EXCLUSIVAMENTE O CONTEUDO ABAIXO.\n\n"
        f"```text\n{text}\n```"
    )
    return SourceMaterial(
        mode=normalized_mode,
        prompt_block=prompt_block,
        files=None,
        txt_path=txt_path,
    )


async def process_job(pdf_path: str, mode: str, keep_chat: bool = False) -> None:
    output_dir = _build_output_dir(pdf_path)
    output_dirs = _ensure_dirs(output_dir)

    job = get_or_create_job(pdf_path, output_dir)
    job_dict = _row_to_dict(job)

    update_job_status(job_dict["id"], STATUS_RUNNING)
    logger.info("Iniciando pipeline de microaprendizado para {}. Saida em {}", pdf_path, output_dir)

    analysis_path = output_dir / "analise_livro.md"
    sessions_path = output_dir / "sessoes.json"
    review_path = output_dir / "revisao_sessoes.md"
    final_json_path = output_dir / "curso.json"

    _normalize_job_stage(job_dict, 1, analysis_path)
    _normalize_job_stage(job_dict, 2, sessions_path)
    _normalize_job_stage(job_dict, 3, review_path)

    generator = Claude45SonnetGenerator()
    guard = LogoutGuard(generator.client, label="microaprendizado")
    guard.register()
    upload_cache: Dict[str, Dict[str, Any]] = {}

    try:
        source_material = await _build_source_material(generator, pdf_path, mode, output_dir, upload_cache)
        # Stage 1: Book analysis
        job = get_or_create_job(pdf_path, output_dir)
        if job["stage1_status"] != STATUS_DONE or not analysis_path.exists():
            logger.info("Stage 1 - Gerando analise do livro para {}", pdf_path)
            update_job_stage(job["id"], 1, STATUS_RUNNING)
            prompt = _load_prompt("1-analiselivro.md")
            prompt = _inject_book_content(prompt, source_material.prompt_block)
            analysis_text = await _call_model_text(
                generator,
                prompt,
                files=source_material.files,
                keep_chat=keep_chat,
            )
            analysis_path.write_text(analysis_text, encoding="utf-8")
            update_job_stage(job["id"], 1, STATUS_DONE)

        # Stage 2: Sessions JSON
        job = get_or_create_job(pdf_path, output_dir)
        if job["stage2_status"] != STATUS_DONE or not sessions_path.exists():
            logger.info("Stage 2 - Construindo JSON de sessoes para {}", pdf_path)
            update_job_stage(job["id"], 2, STATUS_RUNNING)
            analysis_text = analysis_path.read_text(encoding="utf-8").strip()
            if not analysis_text:
                raise RuntimeError("Analise do livro vazia. Prompt 1 deve gerar texto, nao JSON.")
            prompt = _load_prompt("2-sessoes.md")
            prompt = _replace_between(prompt, "ANÁLISE ANTERIOR", "INSTRUÇÕES DETALHADAS", analysis_text)
            prompt += "\n\nResponda APENAS com JSON valido."
            sessions_json, _ = await _call_model_json(generator, prompt, keep_chat=keep_chat)
            sessions_path.write_text(
                json.dumps(sessions_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            update_job_stage(job["id"], 2, STATUS_DONE)

        # Stage 3: Review sessions
        job = get_or_create_job(pdf_path, output_dir)
        if job["stage3_status"] != STATUS_DONE or not review_path.exists() or not final_json_path.exists():
            logger.info("Stage 3 - Revisando sessoes e consolidando JSON final para {}", pdf_path)
            update_job_stage(job["id"], 3, STATUS_RUNNING)
            sessions_json = json.loads(sessions_path.read_text(encoding="utf-8"))
            sessions_payload = json.dumps(sessions_json, ensure_ascii=False, indent=2)
            prompt = _load_prompt("3-revisaosessoes.md")
            prompt = _replace_between(
                prompt,
                "JSON EM ANEXO",
                "INSTRUÇÕES DETALHADAS",
                f"```json\n{sessions_payload}\n```",
            )
            review_text = await _call_model_text(generator, prompt, keep_chat=keep_chat)
            review_path.write_text(review_text, encoding="utf-8")

            corrected_candidate = _extract_json_candidate(review_text)
            if corrected_candidate:
                try:
                    corrected_json = _safe_json_loads(corrected_candidate)
                    final_json_path.write_text(
                        json.dumps(corrected_json, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    logger.warning("JSON corrigido invalido na revisao: {}", exc)
                    final_json_path.write_text(sessions_payload, encoding="utf-8")
            else:
                final_json_path.write_text(sessions_payload, encoding="utf-8")
            update_job_stage(job["id"], 3, STATUS_DONE)

        # Stage 4-8: Microaulas
        curso_json = json.loads(final_json_path.read_text(encoding="utf-8"))
        lessons = _extract_microaulas(curso_json)
        upsert_lessons(job_dict["id"], lessons)
        stored_lessons = fetch_lessons(job_dict["id"])

        # Map for next microaula
        lesson_objects = {lesson["microaula_id"]: lesson for lesson in lessons}
        ordered_ids = [lesson["microaula_id"] for lesson in lessons]

        for lesson in stored_lessons:
            microaula_id = lesson["microaula_id"]
            microaula_obj = lesson_objects.get(microaula_id)
            if not microaula_obj:
                logger.warning("Microaula {} nao encontrada no JSON atual. Ignorando.", microaula_id)
                continue

            next_micro = None
            if microaula_id in ordered_ids:
                pos = ordered_ids.index(microaula_id)
                if pos + 1 < len(ordered_ids):
                    next_id = ordered_ids[pos + 1]
                    next_micro = lesson_objects.get(next_id)

            paths = _build_paths_for_lesson(output_dirs, microaula_id, lesson["titulo"])
            _normalize_lesson_steps(lesson, paths)

            # Step 4: generate base lesson
            lesson = _row_to_dict(get_lesson_by_id(lesson["id"]))
            if lesson["step4_status"] != STATUS_DONE or not paths["base"].exists():
                logger.info("Step 4 - Gerando markdown base da microaula {}", microaula_id)
                update_lesson_step(lesson["id"], 4, STATUS_RUNNING)
                prompt = _load_prompt("4-geracao-aula.md")
                microaula_payload = microaula_obj["microaula_obj"]
                prompt = _replace_between(
                    prompt,
                    "INFORMAÇÕES DA MICROAULA",
                    "CONTEÚDO ORIGINAL DO LIVRO",
                    f"```json\n{json.dumps(microaula_payload, ensure_ascii=False, indent=2)}\n```",
                )
                if next_micro:
                    next_block = f"```json\n{json.dumps(next_micro['microaula_obj'], ensure_ascii=False, indent=2)}\n```"
                else:
                    next_block = "Nenhuma. Esta e a ultima microaula da trilha."
                prompt = _replace_between(
                    prompt,
                    "Próxima Microaula",
                    "INSTRUÇÕES DETALHADAS POR SEÇÃO",
                    next_block,
                )
                prompt = _replace_book_source_reference(prompt, source_material.prompt_block)
                base_markdown = await _call_model_text(
                    generator,
                    prompt,
                    files=source_material.files,
                    keep_chat=keep_chat,
                )
                paths["base"].write_text(base_markdown, encoding="utf-8")
                update_lesson_step(lesson["id"], 4, STATUS_DONE)

            # Step 5: enrich lesson
            lesson = _row_to_dict(get_lesson_by_id(lesson["id"]))
            if lesson["step5_status"] != STATUS_DONE or not paths["aula"].exists():
                logger.info("Step 5 - Enriquecendo microaula {}", microaula_id)
                update_lesson_step(lesson["id"], 5, STATUS_RUNNING)
                base_markdown = paths["base"].read_text(encoding="utf-8")
                prompt = _load_prompt("5-enriquecimento-aula.md")
                prompt = _replace_between(
                    prompt,
                    "MARKDOWN ORIGINAL",
                    "INSTRUÇÕES DETALHADAS",
                    base_markdown,
                )
                enriched_markdown = await _call_model_text(generator, prompt, keep_chat=keep_chat)
                paths["aula"].write_text(enriched_markdown, encoding="utf-8")
                update_lesson_step(lesson["id"], 5, STATUS_DONE)

            # Step 6: audio script
            lesson = _row_to_dict(get_lesson_by_id(lesson["id"]))
            if lesson["step6_status"] != STATUS_DONE or not paths["audio"].exists():
                logger.info("Step 6 - Criando roteiro de audio para {}", microaula_id)
                update_lesson_step(lesson["id"], 6, STATUS_RUNNING)
                enriched_markdown = paths["aula"].read_text(encoding="utf-8")
                prompt = _load_prompt("6-criacao-roteiro.md")
                prompt = _replace_between(
                    prompt,
                    "CONTEÚDO DA MICROAULA",
                    "OBJETIVO",
                    enriched_markdown,
                )
                audio_script = await _call_model_text(generator, prompt, keep_chat=keep_chat)
                paths["audio"].write_text(audio_script, encoding="utf-8")
                update_lesson_step(lesson["id"], 6, STATUS_DONE)

            # Step 7: questions JSON
            lesson = _row_to_dict(get_lesson_by_id(lesson["id"]))
            if paths["perguntas"].exists() and not paths["perguntas_md"].exists():
                try:
                    cached_questions = json.loads(paths["perguntas"].read_text(encoding="utf-8"))
                    paths["perguntas_md"].write_text(
                        _render_questions_markdown(cached_questions),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    logger.warning("Falha ao gerar markdown de perguntas: {}", exc)
            if lesson["step7_status"] != STATUS_DONE or not paths["perguntas"].exists():
                logger.info("Step 7 - Gerando perguntas para {}", microaula_id)
                update_lesson_step(lesson["id"], 7, STATUS_RUNNING)
                enriched_markdown = paths["aula"].read_text(encoding="utf-8")
                prompt = _load_prompt("7-criacao-perguntas.md")
                prompt = _replace_between(
                    prompt,
                    "INFORMAÇÕES DA MICROAULA",
                    "CONTEÚDO COMPLETO",
                    f"```json\n{json.dumps(microaula_obj['microaula_obj'], ensure_ascii=False, indent=2)}\n```",
                )
                prompt = _replace_between(
                    prompt,
                    "CONTEÚDO COMPLETO",
                    "INSTRUÇÕES DETALHADAS",
                    enriched_markdown,
                )
                prompt += "\n\nResponda APENAS com JSON valido."
                questions_json, _ = await _call_model_json(generator, prompt, keep_chat=keep_chat)
                paths["perguntas"].write_text(
                    json.dumps(questions_json, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                paths["perguntas_md"].write_text(
                    _render_questions_markdown(questions_json),
                    encoding="utf-8",
                )
                update_lesson_step(lesson["id"], 7, STATUS_DONE)

            # Step 8: questions review
            lesson = _row_to_dict(get_lesson_by_id(lesson["id"]))
            if lesson["step8_status"] != STATUS_DONE or not paths["relatorio"].exists():
                logger.info("Step 8 - Revisando perguntas e gerando relatorio para {}", microaula_id)
                update_lesson_step(lesson["id"], 8, STATUS_RUNNING)
                questions_payload = paths["perguntas"].read_text(encoding="utf-8")
                prompt = _load_prompt("8-revisao-perguntas")
                prompt = _replace_between(
                    prompt,
                    "PERGUNTAS PARA VALIDAÇÃO",
                    "INSTRUÇÕES DETALHADAS",
                    f"```json\n{questions_payload}\n```",
                )
                report_text = await _call_model_text(generator, prompt, keep_chat=keep_chat)
                paths["relatorio"].write_text(report_text, encoding="utf-8")

                corrected_candidate = _extract_json_candidate(report_text)
                if corrected_candidate:
                    try:
                        corrected_json = _safe_json_loads(corrected_candidate)
                        paths["perguntas"].write_text(
                            json.dumps(corrected_json, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        paths["perguntas_md"].write_text(
                            _render_questions_markdown(corrected_json),
                            encoding="utf-8",
                        )
                    except Exception as exc:
                        logger.warning("JSON corrigido invalido no relatorio: {}", exc)
                update_lesson_step(lesson["id"], 8, STATUS_DONE)

        update_job_status(job_dict["id"], STATUS_DONE)
        logger.info("Processamento concluido. Saida em: {}", output_dir)
    except Exception as exc:
        logger.error("Falha no processamento: {}", exc)
        update_job_status(job_dict["id"], STATUS_PENDING)
        raise
    finally:
        await guard.close_now()


def get_lesson_by_id(lesson_id: int) -> sqlite3.Row:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def _validate_pdf_path(pdf_path: str) -> str:
    resolved = str(Path(pdf_path).resolve())
    if not resolved.lower().endswith(".pdf"):
        raise ValueError("O arquivo informado precisa ser um PDF.")
    if not Path(resolved).exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {resolved}")
    return resolved


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de microaprendizado a partir de PDF.")
    parser.add_argument("--pdf", required=True, help="Caminho do arquivo PDF para processar.")
    parser.add_argument(
        "--mode",
        choices=("upload", "docling"),
        default="upload",
        help="`upload` envia o PDF para a IA; `docling` converte o PDF para TXT e injeta o conteudo no prompt.",
    )
    parser.add_argument(
        "--keep-chat",
        action="store_true",
        help="Mantem o chat criado durante as chamadas ao modelo.",
    )
    args = parser.parse_args()

    pdf_path = _validate_pdf_path(args.pdf)
    initialize_db()
    await process_job(pdf_path, args.mode, keep_chat=bool(args.keep_chat))


if __name__ == "__main__":
    asyncio.run(main())
