"""
test_semantic_tokens_golden.py - Characterization test (Feathers)

Compara a saida de compute_semantic_tokens() contra snapshots commitados,
capturados com o motor de tokenizacao anterior.

Proposito: detectar regressoes NAO PREVISTAS ao trocar o motor. A suite em
test_semantic_tokens.py fixa o comportamento desejado; este arquivo protege
tudo aquilo que ninguem pensou em testar.

Quando este teste falhar apos uma mudanca intencional:
    1. Rodar `python tests/capture_golden.py`
    2. Inspecionar `git diff tests/fixtures/golden/*.golden`
    3. Confirmar que CADA diferenca e esperada antes de commitar
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis_lsp.semantic_tokens import compute_semantic_tokens

from .capture_golden import decode_tokens

FIXTURES = Path(__file__).parent / "fixtures" / "golden"

FONTES = sorted(
    p for p in FIXTURES.iterdir() if p.suffix in {".syn", ".synt", ".syno", ".synp"}
) if FIXTURES.is_dir() else []


@pytest.mark.parametrize("src_path", FONTES, ids=lambda p: p.name)
def test_tokens_batem_com_golden(src_path: Path):
    golden_path = src_path.with_suffix(src_path.suffix + ".golden")
    assert golden_path.is_file(), (
        f"Golden ausente para {src_path.name}. "
        "Rode: python tests/capture_golden.py"
    )

    source = src_path.read_text(encoding="utf-8")
    result = compute_semantic_tokens(source, f"file:///{src_path.name}", None)
    atual = decode_tokens(result.data, source)
    esperado = golden_path.read_text(encoding="utf-8").splitlines()

    if atual == esperado:
        return

    # Diff legivel: mostrar as primeiras divergencias com contexto
    import difflib

    diff = list(
        difflib.unified_diff(
            esperado, atual, fromfile="golden", tofile="atual", lineterm="", n=2
        )
    )
    amostra = "\n".join(diff[:60])
    pytest.fail(
        f"{src_path.name}: saida divergiu do golden "
        f"({len(esperado)} -> {len(atual)} tokens).\n"
        f"Se a mudanca for intencional, rode `python tests/capture_golden.py` "
        f"e revise o diff.\n\n{amostra}"
    )
