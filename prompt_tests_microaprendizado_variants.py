import argparse
import asyncio
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure src is importable when running from repo root.
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generators_v2.adapta import Claude45SonnetGenerator, GPT5Generator
from utils.logger import logger
from utils.text_cleaner import remove_think_tags


PROMPTS_DIR = BASE_DIR / "microaprendizado"
DEFAULT_PDF = BASE_DIR / "100M_Hooks_Playbook.pdf"
PROMPT1_VARIANTS = [
    "1-analiselivro.md",
    "1-1-analiselivro.md",
    "1-2-analiselivro.md",
    "1-3-analiselivro.md",
]

RETRY_LIMIT = 3
RETRY_INITIAL_DELAY = 2.0


@dataclass
class PromptReport:
    prompt_name: str
    total_runs: int
    json_valid: int = 0
    scores: List[int] = field(default_factory=list)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _find_marker(prompt: str, marker: str) -> int:
    direct = prompt.find(marker)
    if direct != -1:
        return direct
    return _strip_accents(prompt).find(_strip_accents(marker))


def _find_marker_after(prompt: str, marker: str, start_idx: int) -> int:
    if start_idx < 0:
        return _find_marker(prompt, marker)
    direct = prompt.find(marker, start_idx)
    if direct != -1:
        return direct
    return _strip_accents(prompt).find(_strip_accents(marker), start_idx)


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


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt nao encontrado: {path}")
    return path.read_text(encoding="utf-8")


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


def _safe_json_loads(candidate: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


async def _call_model_text(generator, prompt: str, *, files: Optional[List[Dict[str, Any]]] = None) -> str:
    delay = RETRY_INITIAL_DELAY
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            response = await generator.call_model_with_messages(
                [{"role": "user", "content": prompt}],
                files=files,
            )
            cleaned = remove_think_tags(str(response))
            return cleaned
        except Exception as exc:
            last_exc = exc
            logger.warning("Falha ao chamar modelo (tentativa {}): {}", attempt, exc)
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(delay)
                delay *= 2
    raise RuntimeError("Falha ao chamar modelo.") from last_exc


def _build_prompt1(prompt_name: str) -> str:
    prompt = _load_prompt(prompt_name)
    prompt = re.sub(
        r"\[INSERIR.*?LIVRO AQUI\]",
        "LIVRO EM ANEXO (PDF).",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return prompt


def _build_prompt2(analysis_text: str) -> str:
    prompt = _load_prompt("2-sessoes.md")
    prompt = _replace_between(prompt, "ANALISE ANTERIOR", "INSTRUCOES DETALHADAS", analysis_text)
    prompt += "\n\nResponda APENAS com JSON valido."
    return prompt


def _build_score_prompt(json_text: str) -> str:
    return (
        "Voce recebera um JSON de microaprendizado e o PDF do livro em anexo. "
        "Avalie a qualidade, coerencia e aderencia ao livro. Dê uma nota de 0 a 100. "
        "Responda APENAS com JSON valido no formato: "
        '{"nota": 0, "justificativa": "texto breve"}.\n\n'
        f"JSON DO CURSO:\n```json\n{json_text}\n```"
    )


def _parse_score(text: str) -> Tuple[Optional[int], Optional[str]]:
    candidate = _extract_json_candidate(text) or text
    parsed = _safe_json_loads(candidate)
    if isinstance(parsed, dict) and "nota" in parsed:
        try:
            nota = int(round(float(parsed["nota"])))
        except (TypeError, ValueError):
            nota = None
        justificativa = parsed.get("justificativa")
        if nota is not None:
            return max(0, min(100, nota)), str(justificativa) if justificativa else None

    match = re.search(r"\b([0-9]{1,3})\b", text)
    if match:
        nota = int(match.group(1))
        return max(0, min(100, nota)), None
    return None, None


async def run_trials(pdf_path: Path, runs: int) -> List[PromptReport]:
    reports: List[PromptReport] = []
    claude = Claude45SonnetGenerator()
    gpt = GPT5Generator()
    try:
        claude_upload = await claude.client.upload_arquivo(str(pdf_path))
        gpt_upload = await gpt.client.upload_arquivo(str(pdf_path))

        for prompt_name in PROMPT1_VARIANTS:
            report = PromptReport(prompt_name=prompt_name, total_runs=runs)
            logger.info("Testando prompt {} com Claude 4.5", prompt_name)
            for _ in range(runs):
                try:
                    prompt1 = _build_prompt1(prompt_name)
                    analysis = await _call_model_text(claude, prompt1, files=[claude_upload])
                    if not analysis.strip():
                        continue
                    prompt2 = _build_prompt2(analysis)
                    response2 = await _call_model_text(claude, prompt2)
                    candidate2 = _extract_json_candidate(response2) or response2
                    parsed2 = _safe_json_loads(candidate2)
                    if parsed2 is None:
                        continue
                    report.json_valid += 1

                    score_prompt = _build_score_prompt(
                        json.dumps(parsed2, ensure_ascii=False, indent=2)
                    )
                    score_response = await _call_model_text(gpt, score_prompt, files=[gpt_upload])
                    score, _ = _parse_score(score_response)
                    if score is not None:
                        report.scores.append(score)
                except Exception as exc:
                    logger.warning("Falha ao testar prompt {}: {}", prompt_name, exc)
            reports.append(report)
    finally:
        try:
            logout = getattr(claude.client, "logout", None)
            if callable(logout):
                await logout()
        except Exception as exc:
            logger.warning("Falha ao efetuar logout do Claude: {}", exc)
        try:
            await claude.client.close()
        except Exception:
            pass

        try:
            logout = getattr(gpt.client, "logout", None)
            if callable(logout):
                await logout()
        except Exception as exc:
            logger.warning("Falha ao efetuar logout do GPT: {}", exc)
        try:
            await gpt.client.close()
        except Exception:
            pass

    return reports


def _format_report(reports: List[PromptReport]) -> str:
    lines: List[str] = []
    lines.append("RELATORIO DE VARIACAO DE PROMPT 1 (CLAUDE 4.5 + GPT AVALIADOR)")
    lines.append("")
    for report in reports:
        avg_score = None
        if report.scores:
            avg_score = sum(report.scores) / len(report.scores)
        lines.append(f"Prompt: {report.prompt_name}")
        lines.append(f"Execucoes: {report.total_runs}")
        lines.append(f"JSON valido (prompt 2): {report.json_valid}/{report.total_runs}")
        if report.scores:
            score_list = ", ".join(str(score) for score in report.scores)
            lines.append(f"Notas: {score_list}")
            lines.append(f"Media: {avg_score:.2f}")
        else:
            lines.append("Notas: nenhuma")
            lines.append("Media: N/A")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Teste de variacoes do prompt 1.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Caminho do PDF a ser usado nos testes.")
    parser.add_argument("--runs", type=int, default=3, help="Execucoes por prompt.")
    parser.add_argument("--output", help="Caminho opcional para salvar o relatorio.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {pdf_path}")

    reports = await run_trials(pdf_path, args.runs)
    report_text = _format_report(reports)
    print(report_text)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
