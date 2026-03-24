"""Pipeline simplificado para destilar livros em 7 dimensões usando Claude 4.5 (Adapta)."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List

from generators_v2.adapta.claude_45_sonnet_generator import Claude45SonnetGenerator
from utils.response_validator import requires_processing_retry
from utils.session_guard import LogoutGuard
from utils.text_cleaner import remove_think_tags
from utils.logger import logger

# Pastas fixas conforme solicitado
SOURCE_DIR = Path("livros")
OUTPUT_DIR = Path("docs_livros")
NUM_ITERACOES = 2  # quantas vezes cada dimensão será gerada; fica com a resposta mais longa
DIMENSION_RETRY_LIMIT = 3
DIMENSION_RETRY_DELAY_SECONDS = 60.0
UPLOAD_DELAY_SECONDS = 10.0  # delay padrão após upload

PROMPTS_DIR = Path("src/prompts/livro")

def load_dimension_prompt(dimension: int) -> str:
    prompt_path = PROMPTS_DIR / f"dimensao{dimension}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt da dimensão {dimension} não encontrado em {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")

async def upload_pdf(
    generator: Claude45SonnetGenerator,
    pdf_path: Path,
    delay: float = UPLOAD_DELAY_SECONDS,
) -> tuple[Dict, Path]:
    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"livro_upload_{uuid.uuid4().hex}{pdf_path.suffix.lower()}"
    shutil.copy2(pdf_path, temp_path)
    upload_info = await generator.client.upload_arquivo(str(temp_path))
    if delay and delay > 0:
        await asyncio.sleep(delay)
    if not upload_info:
        raise RuntimeError(f"Falha ao fazer upload de {pdf_path}")
    return upload_info, temp_path


async def run_dimension(
    generator: Claude45SonnetGenerator,
    prompt: str,
    upload_info: Dict,
) -> str:
    response = await generator.call_model_with_messages(
        [{"role": "user", "content": prompt}],
        files=[upload_info],
    )
    return remove_think_tags(response)


async def process_book(
    pdf_path: Path,
    generator: Claude45SonnetGenerator,
    *,
    auto: bool = False,
    upload_delay: float = UPLOAD_DELAY_SECONDS,
) -> None:
    logger.info("Processando livro: {}", pdf_path.name)
    working_dir = OUTPUT_DIR / pdf_path.stem
    working_dir.mkdir(parents=True, exist_ok=True)

    upload_info: Dict | None = None
    temp_upload_path: Path | None = None
    dim_paths: List[Path] = []
    success = False
    user_declined = False
    interrupted = False

    try:
        upload_info, temp_upload_path = await upload_pdf(generator, pdf_path, delay=upload_delay)

        for dimension in range(1, 8):
            prompt = load_dimension_prompt(dimension)
            logger.info("Disparando {} iterações em paralelo para dimensão {} ({})", NUM_ITERACOES, dimension, pdf_path.name)

            dim_file = working_dir / f"dimensao{dimension}.txt"
            if dim_file.exists():
                logger.info("Dimensão {} já existe, pulando geração para {}", dimension, pdf_path.name)
                dim_paths.append(dim_file)
                continue

            dimension_completed = False
            for attempt in range(1, DIMENSION_RETRY_LIMIT + 1):
                tasks = [
                    asyncio.create_task(run_dimension(generator, prompt, upload_info))
                    for _ in range(NUM_ITERACOES)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                best_content = ""
                for idx, res in enumerate(results, start=1):
                    if isinstance(res, Exception):
                        logger.warning("Iteração {} da dimensão {} falhou: {}", idx, dimension, res)
                        continue
                    if requires_processing_retry(res):
                        logger.warning(
                            "Dimensão {} tentativa {}.{} retornou aviso de que o arquivo não pôde ser processado. Repetindo.",
                            dimension,
                            attempt,
                            idx,
                        )
                        continue
                    logger.info("Dimensão {} tentativa {}/{} concluída para {}", dimension, idx, NUM_ITERACOES, pdf_path.name)
                    if len(res) > len(best_content):
                        best_content = res

                if best_content:
                    if dimension <= 6 and not best_content.endswith("\n"):
                        best_content += "\n"
                    dim_file.write_text(best_content, encoding="utf-8")
                    logger.info("Dimensão {} finalizada (maior resposta selecionada) para {}", dimension, pdf_path.name)
                    dim_paths.append(dim_file)
                    dimension_completed = True
                    break

                if attempt < DIMENSION_RETRY_LIMIT:
                    logger.warning(
                        "Nenhuma resposta válida obtida na dimensão {} (tentativa {}/{}). Repetindo processamento.",
                        dimension,
                        attempt,
                        DIMENSION_RETRY_LIMIT,
                    )
                    await asyncio.sleep(DIMENSION_RETRY_DELAY_SECONDS)

            if not dimension_completed:
                logger.error("Nenhuma resposta válida obtida na dimensão {} para {}", dimension, pdf_path.name)
                raise RuntimeError(f"Dimensão {dimension} sem respostas válidas")

        if upload_info:
            remote_path = (
                upload_info.get("path")
                or upload_info.get("filePathOnStorage")
                or upload_info.get("filename")
            )
            if remote_path:
                try:
                    await generator.client.excluir_arquivo(remote_path)
                except Exception as exc:  # pragma: no cover - limpeza best-effort
                    logger.warning("Falha ao excluir arquivo remoto {}: {}", remote_path, exc)
            upload_info = None

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
        if upload_info:
            remote_path = (
                upload_info.get("path")
                or upload_info.get("filePathOnStorage")
                or upload_info.get("filename")
            )
            if remote_path:
                try:
                    await generator.client.excluir_arquivo(remote_path)
                except Exception as exc:  # pragma: no cover - limpeza best-effort
                    logger.warning("Falha ao excluir arquivo remoto {}: {}", remote_path, exc)

        if temp_upload_path and temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception as exc:
                logger.warning("Falha ao remover upload temporário {}: {}", temp_upload_path, exc)

        # Limpeza condicional dos parciais
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


async def main(auto: bool = False, upload_delay: float = UPLOAD_DELAY_SECONDS) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generator = Claude45SonnetGenerator()
    guard = LogoutGuard(generator.client, label="destilador")
    guard.register()

    try:
        logger.info("Destilador iniciado com auto={} e upload_delay={}s", auto, upload_delay)
        pdfs = sorted(p for p in SOURCE_DIR.glob("*.pdf") if p.is_file())
        if not pdfs:
            logger.info("Nenhum PDF encontrado em {}", SOURCE_DIR)
            return

        for idx, pdf in enumerate(pdfs, start=1):
            logger.info("Iniciando processamento {}/{}: {}", idx, len(pdfs), pdf.name)
            await process_book(pdf, generator, auto=auto, upload_delay=upload_delay)
        logger.info("Destilador finalizado. Livros processados: {}", len(pdfs))
    finally:
        await guard.close_now()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Destilador v2 (Claude 4.5) - processa PDFs em 7 dimensões.")
    parser.add_argument("--auto", action="store_true", help="Gera consolidado automaticamente sem pedir confirmação.")
    parser.add_argument("--upload-delay", type=float, default=UPLOAD_DELAY_SECONDS, help="Delay (s) após cada upload antes de chamar o modelo.")
    args = parser.parse_args()

    asyncio.run(main(auto=args.auto, upload_delay=args.upload_delay))
