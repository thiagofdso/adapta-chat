import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import (
    _apply_json_patch,
    _diagnose_patch_failure,
)


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        print(f"[ERRO] Arquivo {path} nao contem JSON valido: {exc}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Aplica um JSON Patch (RFC 6902) em um documento e reporta resultado."
    )
    parser.add_argument("document", type=Path, help="Arquivo JSON base (ex.: indexes/vtsd.json)")
    parser.add_argument("patch", type=Path, help="Arquivo contendo o JSON Patch")
    args = parser.parse_args()

    base_path = args.document
    patch_path = args.patch

    if not base_path.is_file():
        print(f"[ERRO] Arquivo base nao encontrado: {base_path}", file=sys.stderr)
        sys.exit(1)
    if not patch_path.is_file():
        print(f"[ERRO] Arquivo de patch nao encontrado: {patch_path}", file=sys.stderr)
        sys.exit(1)

    document = load_json(base_path)
    patch_data = load_json(patch_path)

    if isinstance(patch_data, dict) and "patch" in patch_data:
        operations = patch_data["patch"]
    else:
        operations = patch_data

    if not isinstance(operations, list):
        print("[ERRO] Patch deve ser uma lista de operacoes ou objeto com campo 'patch'.", file=sys.stderr)
        sys.exit(1)

    try:
        result = _apply_json_patch(document, operations)
    except Exception as exc:
        idx, failing_op, inner_exc = _diagnose_patch_failure(document, operations)
        print(f"[FALHA] Erro ao aplicar JSON Patch: {exc}", file=sys.stderr)
        if failing_op:
            path = failing_op.get("path", "")
            print(f" - Operacao que falhou (indice {idx}): {failing_op}", file=sys.stderr)
            if path:
                if path.startswith("/sections/"):
                    try:
                        section_idx_str = path.split("/")[2]
                        section_idx = int(section_idx_str)
                        sections = document.get("sections") or []
                        if 0 <= section_idx < len(sections):
                            section = sections[section_idx]
                            sec_id = section.get("section_id")
                            sec_title = section.get("title")
                            knowledges = section.get("knowledges") or []
                            print(
                                f"   > Detalhe: section index {section_idx} (section_id={sec_id}, title={sec_title}) possui {len(knowledges)} knowledges.",
                                file=sys.stderr,
                            )
                        else:
                            print(
                                f"   > Detalhe: documento possui apenas {len(sections)} sections; indice {section_idx} invalido.",
                                file=sys.stderr,
                            )
                        if "/knowledges/" in path:
                            parts = path.split("/knowledges/")
                            if len(parts) > 1:
                                kn_idx_part = parts[1].split("/")[0]
                                if kn_idx_part.isdigit():
                                    kn_idx = int(kn_idx_part)
                                    if 0 <= section_idx < len(sections):
                                        knowledges = sections[section_idx].get("knowledges") or []
                                        print(
                                            f"   > knowledges[{kn_idx}] esperado; lista atual possui {len(knowledges)} itens.",
                                            file=sys.stderr,
                                        )
                    except ValueError:
                        pass
        if inner_exc and inner_exc is not exc:
            print(f" - Detalhe: {inner_exc}", file=sys.stderr)
        sys.exit(1)

    print("[SUCESSO] Patch aplicado com sucesso.")
    output_path = Path("patch_result.json")
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(f"Resultado salvo em {output_path.resolve()}")


if __name__ == "__main__":
    main()
