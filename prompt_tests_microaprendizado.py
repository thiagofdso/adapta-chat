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

from generators_v2.adapta import (
    Claude45SonnetGenerator,
    DeepseekV3Generator,
    Gemini3ProPreviewGenerator,
    GPT5Generator,
    GPT51Generator,
    Grok41Generator,
    O3Generator,
    OneProGenerator,
    Qwen3MaxGenerator,
    SonarProGenerator,
)
from utils.logger import logger
from utils.text_cleaner import remove_think_tags


PROMPTS_DIR = BASE_DIR / "microaprendizado"
DEFAULT_PDF = BASE_DIR / "100M_Hooks_Playbook.pdf"
RETRY_LIMIT = 3
RETRY_INITIAL_DELAY = 2.0


MODEL_FACTORIES = [
    ("CLAUDE_4_5_SONNET", Claude45SonnetGenerator),
    ("DEEPSEEK_V3", DeepseekV3Generator),
    ("GEMINI_3_PRO_PREVIEW", Gemini3ProPreviewGenerator),
    ("GPT_5", GPT5Generator),
    ("GPT_5_1", GPT51Generator),
    ("GROK_4_1", Grok41Generator),
    ("O3", O3Generator),
    ("ONE_PRO", OneProGenerator),
    ("QWEN3_MAX", Qwen3MaxGenerator),
    ("SONAR_PRO", SonarProGenerator),
]


@dataclass
class TrialResult:
    run_id: int
    prompt1_valid: bool = False
    prompt2_valid: bool = False
    score: Optional[int] = None
    score_note: Optional[str] = None


@dataclass
class ModelReport:
    name: str
    total_runs: int
    prompt1_valid: int = 0
    prompt2_valid: int = 0
    scores: List[int] = field(default_factory=list)
    trials: List[TrialResult] = field(default_factory=list)


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


def _build_prompt1() -> str:
    prompt = _load_prompt("1-analiselivro.md")
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


async def run_trials(pdf_path: Path, runs: int, models: List[str]) -> List[ModelReport]:
    reports: List[ModelReport] = []
    selected = [(name, factory) for name, factory in MODEL_FACTORIES if name in models]
    if not selected:
        raise ValueError("Nenhum modelo selecionado para teste.")

    scoring_generator = GPT5Generator()
    try:
        scoring_upload = await scoring_generator.client.upload_arquivo(str(pdf_path))
        for name, factory in selected:
            logger.info("Iniciando testes para modelo {}", name)
            report = ModelReport(name=name, total_runs=runs)
            generator = factory()
            try:
                upload_info = await generator.client.upload_arquivo(str(pdf_path))
                for run_id in range(1, runs + 1):
                    trial = TrialResult(run_id=run_id)
                    try:
                        prompt1 = _build_prompt1()
                        response1 = await _call_model_text(generator, prompt1, files=[upload_info])
                        if response1.strip():
                            trial.prompt1_valid = True
                            report.prompt1_valid += 1

                        prompt2 = _build_prompt2(response1)
                        response2 = await _call_model_text(generator, prompt2)
                        candidate2 = _extract_json_candidate(response2) or response2
                        parsed2 = _safe_json_loads(candidate2)
                        if parsed2 is not None:
                            trial.prompt2_valid = True
                            report.prompt2_valid += 1

                            score_prompt = _build_score_prompt(
                                json.dumps(parsed2, ensure_ascii=False, indent=2)
                            )
                            score_response = await _call_model_text(
                                scoring_generator, score_prompt, files=[scoring_upload]
                            )
                            score, note = _parse_score(score_response)
                            trial.score = score
                            trial.score_note = note
                            if score is not None:
                                report.scores.append(score)

                            # Exclui sessoes criadas apos avaliacao (nao persistir).
                            if isinstance(parsed2, dict):
                                curso = parsed2.get("curso")
                                if isinstance(curso, dict) and "sessoes" in curso:
                                    curso.pop("sessoes", None)
                                    if "sessoes" in curso:
                                        raise RuntimeError("Falha ao remover sessoes do JSON.")
                        report.trials.append(trial)
                    except Exception as exc:
                        logger.warning("Falha na execucao {} do modelo {}: {}", run_id, name, exc)
                        report.trials.append(trial)
            finally:
                try:
                    logout = getattr(generator.client, "logout", None)
                    if callable(logout):
                        await logout()
                except Exception as exc:
                    logger.warning("Falha ao efetuar logout do modelo {}: {}", name, exc)
                try:
                    await generator.client.close()
                except Exception:
                    pass
            reports.append(report)
    finally:
        try:
            logout = getattr(scoring_generator.client, "logout", None)
            if callable(logout):
                await logout()
        except Exception as exc:
            logger.warning("Falha ao efetuar logout do modelo GPT: {}", exc)
        try:
            await scoring_generator.client.close()
        except Exception:
            pass
    return reports


def _format_report(reports: List[ModelReport]) -> str:
    lines: List[str] = []
    lines.append("RELATORIO DE TESTE DE PROMPTS")
    lines.append("")
    for report in reports:
        avg_score = None
        if report.scores:
            avg_score = sum(report.scores) / len(report.scores)

        lines.append(f"Modelo: {report.name}")
        lines.append(f"Total de execucoes: {report.total_runs}")
        lines.append(f"Prompt 1 executado (texto): {report.prompt1_valid}/{report.total_runs}")
        lines.append(f"JSON valido (prompt 2): {report.prompt2_valid}/{report.total_runs}")
        if report.scores:
            score_list = ", ".join(str(score) for score in report.scores)
            lines.append(f"Notas (apenas prompt 2 valido): {score_list}")
            lines.append(f"Media de notas: {avg_score:.2f}")
        else:
            lines.append("Notas (apenas prompt 2 valido): nenhuma")
            lines.append("Media de notas: N/A")
        lines.append("Detalhes por execucao:")
        for trial in report.trials:
            score_text = str(trial.score) if trial.score is not None else "N/A"
            lines.append(
                f"- Execucao {trial.run_id}: prompt1={'ok' if trial.prompt1_valid else 'vazio'}, "
                f"prompt2={'ok' if trial.prompt2_valid else 'invalido'}, nota={score_text}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Teste de prompts de microaprendizado.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Caminho do PDF a ser usado nos testes.")
    parser.add_argument("--runs", type=int, default=3, help="Quantidade de execucoes por modelo.")
    parser.add_argument(
        "--models",
        default=",".join(name for name, _ in MODEL_FACTORIES),
        help="Lista separada por virgula com os modelos a testar.",
    )
    parser.add_argument("--output", help="Caminho opcional para salvar o relatorio.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {pdf_path}")

    models = [item.strip().upper() for item in args.models.split(",") if item.strip()]
    reports = await run_trials(pdf_path, args.runs, models)
    report_text = _format_report(reports)
    print(report_text)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
