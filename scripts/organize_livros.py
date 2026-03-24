#!/usr/bin/env python3
"""Organiza os PDFs da pasta 'livros', criando subpastas com o mesmo nome."""

from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LIVROS_DIR = BASE_DIR / "livros"


def organize_pdfs(root: Path) -> int:
    """Move cada PDF diretamente contido em root para uma subpasta homônima."""
    if not root.exists() or not root.is_dir():
        print(f"Diretorio nao encontrado: {root}", file=sys.stderr)
        return 1

    moved = 0
    for pdf_path in sorted(root.glob("*.pdf")):
        target_dir = root / pdf_path.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / pdf_path.name

        if target_path.exists():
            print(f"[!] Destino ja existe, pulando: {target_path}")
            continue

        pdf_path.rename(target_path)
        moved += 1
        print(f"[✓] Movido {pdf_path.name} -> {target_dir.relative_to(root)}")

    if moved == 0:
        print("Nenhum PDF para mover na pasta informada.")
    else:
        print(f"Total de PDFs movidos: {moved}")
    return 0


def main() -> int:
    return organize_pdfs(LIVROS_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
