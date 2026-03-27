import argparse
import asyncio
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
DEFAULT_ANALYSIS = (
    BASE_DIR
    / "microaprendizado_output"
    / "pitch_anything_an_innovative_method_for_presenting_ae0b5975"
    / "analise_livro.md"
)
DEFAULT_OUTPUT_DIR = BASE_DIR / "microaprendizado_output" / "prompt_tests_pitch_stage2"


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
    json_valid: bool = False
    output_path: Optional[Path] = None
    error: Optional[str] = None


@dataclass
class ModelReport:
    name: str
    total_runs: int
    json_valid: int = 0
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


async def _call_model_text(generator, prompt: str) -> str:
    response = await generator.call_model_with_messages(
        [{"role": "user", "content": prompt}],
    )
    return remove_think_tags(str(response))


def _build_stage2_prompt(analysis_text: str) -> str:
    prompt = _load_prompt("2-sessoes.md")
    prompt = _replace_between(prompt, "ANALISE ANTERIOR", "INSTRUCOES DETALHADAS", analysis_text)
    prompt += "\n\nResponda APENAS com JSON valido."
    return prompt


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "modelo"


def _write_trial_output(output_root: Path, model_name: str, run_id: int, content: str) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{_slugify(model_name)}_run_{run_id:02d}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


async def run_trials(analysis_path: Path, runs: int, models: List[str], output_root: Path) -> List[ModelReport]:
    selected = [(name, factory) for name, factory in MODEL_FACTORIES if name in models]
    if not selected:
        raise ValueError("Nenhum modelo selecionado para teste.")

    analysis_text = analysis_path.read_text(encoding="utf-8").strip()
    if not analysis_text:
        raise ValueError(f"Arquivo de analise vazio: {analysis_path}")

    prompt = _build_stage2_prompt(analysis_text)
    reports: List[ModelReport] = []

    for name, factory in selected:
        logger.info("Iniciando testes do Stage 2 para modelo {}", name)
        report = ModelReport(name=name, total_runs=runs)
        generator = factory()
        try:
            for run_id in range(1, runs + 1):
                trial = TrialResult(run_id=run_id)
                try:
                    response = await _call_model_text(generator, prompt)
                    trial.output_path = _write_trial_output(output_root, name, run_id, response)
                    candidate = _extract_json_candidate(response) or response
                    parsed = _safe_json_loads(candidate)
                    if parsed is not None:
                        trial.json_valid = True
                        report.json_valid += 1
                except Exception as exc:
                    trial.error = str(exc)
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

    return reports


def _format_report(reports: List[ModelReport], analysis_path: Path, output_root: Path) -> str:
    lines: List[str] = []
    lines.append("RELATORIO DE TESTE DE PROMPTS - STAGE 2 PITCH")
    lines.append(f"Arquivo de analise: {analysis_path}")
    lines.append(f"Diretorio de saida: {output_root}")
    lines.append("")
    for report in reports:
        lines.append(f"Modelo: {report.name}")
        lines.append(f"Total de execucoes: {report.total_runs}")
        lines.append(f"JSON valido: {report.json_valid}/{report.total_runs}")
        lines.append("Detalhes por execucao:")
        for trial in report.trials:
            output_label = str(trial.output_path) if trial.output_path else "N/A"
            error_label = trial.error or "nenhum"
            lines.append(
                f"- Execucao {trial.run_id}: json={'ok' if trial.json_valid else 'invalido'}, "
                f"saida={output_label}, erro={error_label}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Teste do prompt Stage 2 de microaprendizado para Pitch Anything.")
    parser.add_argument(
        "--analysis",
        default=str(DEFAULT_ANALYSIS),
        help="Caminho do analise_livro.md a ser usado no prompt do Stage 2.",
    )
    parser.add_argument("--runs", type=int, default=1, help="Quantidade de execucoes por modelo.")
    parser.add_argument(
        "--models",
        default=",".join(name for name, _ in MODEL_FACTORIES),
        help="Lista separada por virgula com os modelos a testar.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Diretorio onde as respostas brutas por modelo/execucao serao salvas.",
    )
    parser.add_argument("--output", help="Caminho opcional para salvar o relatorio.")
    args = parser.parse_args()

    analysis_path = Path(args.analysis).resolve()
    if not analysis_path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {analysis_path}")

    models = [item.strip().upper() for item in args.models.split(",") if item.strip()]
    output_root = Path(args.output_dir).resolve()
    reports = await run_trials(analysis_path, args.runs, models, output_root)
    report_text = _format_report(reports, analysis_path, output_root)
    print(report_text)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
