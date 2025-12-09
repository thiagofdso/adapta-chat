"""Versão do destilador usando generators v1 (GPTGenerator)."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from generators.adapta.gpt_generator import GPTGenerator
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator

from utils.logger import logger

SOURCE_DIR = Path("livros")
OUTPUT_DIR = Path("docs_livros")
NUM_ITERACOES = 1
PROMPTS_DIR = Path("src/prompts/livro")


def load_dimension_prompt(dimension: int) -> str:
    prompt_path = PROMPTS_DIR / f"dimensao{dimension}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt da dimensão {dimension} não encontrado em {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _extract_file_id(upload_info: Dict[str, any]) -> Optional[str]:
    if not upload_info:
        return None
    return (
        upload_info.get("id")
        or upload_info.get("fileId")
        or upload_info.get("file_id")
        or upload_info.get("fileKey")
        or upload_info.get("path")
        or upload_info.get("filePathOnStorage")
    )


async def upload_pdf(generator: ClaudeOpusGenerator, source_path: Path) -> tuple[Dict, Path]:
    temp_dir = Path(tempfile.gettempdir())
    ext = source_path.suffix.lower()
    temp_path = temp_dir / f"livro_upload_{uuid.uuid4().hex}{ext}"
    shutil.copy2(source_path, temp_path)
    upload_info = await generator.client.upload_arquivo(str(temp_path))
    if not upload_info:
        raise RuntimeError(f"Falha ao fazer upload de {source_path}")
    return upload_info, temp_path


async def run_dimension(
    generator: ClaudeOpusGenerator,
    prompt: str,
    file_id: str,
    chat_id: Optional[str] = None,
) -> str:
    messages = [{"role": "user", "content": prompt}]
    return await generator.call_model_with_messages(
        messages,
        chat_id=chat_id,
        file_ids=[file_id] if file_id else None,
    )


async def process_book(pdf_path: Path, generator: ClaudeOpusGenerator, *, auto: bool = False) -> None:
    logger.info("Processando livro: {}", pdf_path.name)
    working_dir = OUTPUT_DIR / pdf_path.stem
    working_dir.mkdir(parents=True, exist_ok=True)

    upload_info: Dict | None = None
    temp_upload_path: Path | None = None
    file_id: Optional[str] = None
    dim_paths: List[Path] = []
    success = False
    user_declined = False
    interrupted = False

    try:
        upload_info, temp_upload_path = await upload_pdf(generator, pdf_path)
        file_id = _extract_file_id(upload_info) or ""

        for dimension in range(1, 8):
            prompt = load_dimension_prompt(dimension)
            logger.info("Executando {} iterações sequenciais para dimensão {} ({})", NUM_ITERACOES, dimension, pdf_path.name)

            dim_file = working_dir / f"dimensao{dimension}.txt"
            if dim_file.exists():
                logger.info("Dimensão {} já existe, pulando geração para {}", dimension, pdf_path.name)
                dim_paths.append(dim_file)
                continue

            results = []
            for attempt in range(1, NUM_ITERACOES + 1):
                try:
                    res = await run_dimension(generator, prompt, file_id)
                    results.append(res)
                    logger.info("Dimensão {} tentativa {}/{} concluída para {}", dimension, attempt, NUM_ITERACOES, pdf_path.name)
                except Exception as res_exc:
                    results.append(res_exc)
                    logger.warning("Iteração {} da dimensão {} falhou: {}", attempt, dimension, res_exc)

            best_content = ""
            for res in results:
                if isinstance(res, Exception):
                    continue
                if len(res) > len(best_content):
                    best_content = res

            if best_content:
                # para dimensões 1 a 6, adiciona quebra de linha extra no fim
                if dimension <= 6 and not best_content.endswith("\n"):
                    best_content = best_content + "\n"
                dim_file.write_text(best_content, encoding="utf-8")
                logger.info("Dimensão {} finalizada (maior resposta selecionada) para {}", dimension, pdf_path.name)
                dim_paths.append(dim_file)
            else:
                logger.error("Nenhuma resposta válida obtida na dimensão {} para {}", dimension, pdf_path.name)
                raise RuntimeError(f"Dimensão {dimension} sem respostas válidas")

        # Remove upload remoto antes da confirmação
        if file_id:
            try:
                await generator.client.excluir_arquivo(file_id)
            except Exception as exc:  # pragma: no cover
                logger.warning("Falha ao excluir arquivo remoto {}: {}", file_id, exc)
            file_id = None

        confirm = "y" if auto else input(
            f"As 7 dimensões de '{pdf_path.name}' estão geradas/atuais. "
            "Gerar o .md final e limpar os parciais? [s/N]: "
        ).strip().lower()
        if confirm in ("s", "y", "sim", "yes"):
            final_md = OUTPUT_DIR / f"{pdf_path.stem}.md"
            combined = "\n\n".join(path.read_text(encoding="utf-8") for path in dim_paths if path.exists())
            final_md.write_text(combined, encoding="utf-8")
            logger.info("Arquivo final salvo em {}", final_md)
            success = True
        else:
            user_declined = True
            logger.info("Usuário optou por revisar antes de consolidar. Parciais mantidos em {}", working_dir)
    except KeyboardInterrupt:
        interrupted = True
        logger.warning("Processamento interrompido manualmente para {}. Mantendo parciais para revisão.", pdf_path.name)
    except Exception as exc:
        logger.error("Erro ao processar {}: {}", pdf_path.name, exc)
    finally:
        if file_id:
            try:
                await generator.client.excluir_arquivo(file_id)
            except Exception as exc:
                logger.warning("Falha ao excluir arquivo remoto {}: {}", file_id, exc)

        if temp_upload_path and temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception as exc:
                logger.warning("Falha ao remover upload temporário {}: {}", temp_upload_path, exc)

        if success:
            for dim_file in dim_paths:
                try:
                    dim_file.unlink()
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    logger.warning("Falha ao remover {}: {}", dim_file, exc)
            try:
                working_dir.rmdir()
            except OSError:
                pass
            else:
                logger.info("Livro {} concluído e parciais removidos.", pdf_path.name)
        else:
            if user_declined:
                logger.info("Parciais preservados para revisão manual em {}", working_dir)
            elif interrupted:
                logger.info("Parciais preservados após interrupção em {}", working_dir)
            else:
                logger.info("Parciais preservados para análise de erro em {}", working_dir)


async def main(auto: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generator = ClaudeOpusGenerator()

    inputs = sorted(
        p for p in SOURCE_DIR.glob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".txt"}
    )
    if not inputs:
        logger.info("Nenhum PDF ou TXT encontrado em {}", SOURCE_DIR)
        return

    for path in inputs:
        await process_book(path, generator, auto=auto)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Destilador v1 (GPT) - processa PDFs/TXTs em 7 dimensões.")
    parser.add_argument("--auto", action="store_true", help="Gera consolidado automaticamente sem pedir confirmação.")
    args = parser.parse_args()

    asyncio.run(main(auto=args.auto))
