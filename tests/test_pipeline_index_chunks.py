import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pipeline  # noqa: E402


def _setup_indexes_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "INDEXES_PATH", str(tmp_path))
    monkeypatch.setattr(pipeline, "CHAT_LOG_PATH", Path(tmp_path) / "chat.md")
    os.makedirs(pipeline.INDEXES_PATH, exist_ok=True)


def _make_knowledge(index: int) -> dict:
    return {
        "name": f"Conhecimento {index}",
        "description": f"Descricao {index}",
        "files": [f"aula_{index:03d}.txt"],
    }


def test_save_index_data_splits_into_chunks(tmp_path, monkeypatch):
    _setup_indexes_dir(tmp_path, monkeypatch)
    folder = tmp_path / "curso"
    folder.mkdir()

    base_path = pipeline.get_index_file_path(str(folder))
    knowledges = [_make_knowledge(i) for i in range(650)]

    pipeline.save_index_data(base_path, {"knowledges": knowledges})

    part_paths = pipeline.get_index_part_paths(base_path)
    assert len(part_paths) == 3

    lengths = []
    for part_path in part_paths:
        with open(part_path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        lengths.append(len(data.get("knowledges") or []))
        assert len(data.get("knowledges") or []) <= pipeline.MAX_INDEX_CHUNK_SIZE

    assert lengths[0] == pipeline.MAX_INDEX_CHUNK_SIZE
    assert lengths[1] == pipeline.MAX_INDEX_CHUNK_SIZE
    assert lengths[2] == len(knowledges) - 2 * pipeline.MAX_INDEX_CHUNK_SIZE

    with open(base_path, "r", encoding="utf-8") as stream:
        base_data = json.load(stream)
    assert len(base_data.get("knowledges") or []) == len(knowledges)


def test_load_index_data_converts_legacy_file(tmp_path, monkeypatch):
    _setup_indexes_dir(tmp_path, monkeypatch)
    folder = tmp_path / "legacy"
    folder.mkdir()

    base_path = pipeline.get_index_file_path(str(folder))
    base_path_obj = Path(base_path)
    base_path_obj.parent.mkdir(parents=True, exist_ok=True)

    legacy_payload = {"knowledges": [_make_knowledge(i) for i in range(325)]}
    base_path_obj.write_text(json.dumps(legacy_payload, ensure_ascii=False, indent=4), encoding="utf-8")

    loaded = pipeline.load_index_data(base_path)
    assert len(loaded.get("knowledges") or []) == 325

    part_paths = pipeline.get_index_part_paths(base_path)
    assert len(part_paths) == 2

    sizes = []
    for part_path in part_paths:
        with open(part_path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        sizes.append(len(data.get("knowledges") or []))

    assert sizes[0] == pipeline.MAX_INDEX_CHUNK_SIZE
    assert sizes[1] == 25


class _DummyGenerator:
    def __init__(self, name: str):
        self._name = name

    def get_provider_name(self) -> str:
        return self._name


def test_call_with_retries_uses_generator_cycle(monkeypatch, tmp_path):
    dummy_input = tmp_path / "input.txt"
    dummy_input.write_text("conteudo", encoding="utf-8")

    cycle = [
        _DummyGenerator("Claude"),
        _DummyGenerator("GPT"),
        _DummyGenerator("Gemini"),
    ]

    def fake_prepare(file_paths, base_dir, prefix, prefer_original, consolidate):
        dummy = tmp_path / f"{prefix}.txt"
        dummy.write_text("temp", encoding="utf-8")
        return [(dummy, False)]

    call_sequence = []
    attempts = {"count": 0}

    async def fake_call(gen, prompt, uploads, messages=None, tool=None):
        attempts["count"] += 1
        call_sequence.append(gen.get_provider_name())
        if attempts["count"] < 3:
            raise RuntimeError("fail")
        return "ok"

    monkeypatch.setattr(pipeline, "_prepare_upload_specs", fake_prepare)
    monkeypatch.setattr(pipeline, "_call_generator_with_uploads", fake_call)

    result = asyncio.run(
        pipeline._call_with_retries(
            generator=cycle[0],
            prompt="ola",
            source_paths=[str(dummy_input)],
            base_dir=None,
            prefix="cycle-test",
            prefer_original_when_single=True,
            consolidate=False,
            max_retries=3,
            initial_delay=0,
            generator_cycle=cycle,
        )
    )

    assert result == "ok"
    assert call_sequence == ["Claude", "GPT", "Gemini"]


def test_predict_upload_names_stage1(tmp_path):
    folder = tmp_path / "curso"
    folder.mkdir()
    job_file = folder / "aula.txt"
    job_file.write_text("conteudo", encoding="utf-8")

    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()
    index_part = indexes_dir / "vtsd_part_001.json"
    index_part.write_text("{}", encoding="utf-8")

    file_paths = [str(job_file), str(index_part)]
    predicted = pipeline._predict_upload_names(
        file_paths,
        str(folder),
        prefix="stage1",
        prefer_original=True,
        consolidate=False,
    )

    assert predicted[0] == "aula.txt"
    assert predicted[1].startswith("stage1_vtsd_part_001_")
    assert predicted[1].endswith(".txt")


def test_predict_upload_names_stage2(tmp_path):
    folder = tmp_path / "curso"
    folder.mkdir()
    file_a = folder / "parte_a.txt"
    file_a.write_text("conteudo A", encoding="utf-8")
    file_b = folder / "parte_b.txt"
    file_b.write_text("conteudo B", encoding="utf-8")

    file_paths = [str(file_a), str(file_b)]
    predicted = pipeline._predict_upload_names(
        file_paths,
        str(folder),
        prefix="stage2",
        prefer_original=True,
        consolidate=True,
    )

    assert len(predicted) == 1
    assert predicted[0].startswith("stage2_parte_a_parte_b_")
    assert predicted[0].endswith(".txt")
