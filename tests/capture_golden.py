"""
capture_golden.py - Captura snapshot de tokens semanticos (characterization test)

Uso:
    python tests/capture_golden.py

Proposito:
    Serializa a saida de compute_semantic_tokens() para fixtures reais, de forma
    legivel (uma linha por token, com o texto que o token cobre). Serve para
    detectar regressoes NAO PREVISTAS ao trocar o motor de tokenizacao.

    Diferenca em relacao a suite normal: a suite testa o comportamento DESEJADO;
    o golden detecta mudancas que ninguem pensou em testar.

Fluxo:
    1. Rodar com o motor ANTIGO -> commitar os .golden gerados
    2. Trocar o motor
    3. Rodar test_semantic_tokens_golden.py -> revisar CADA diferenca:
       - esperada (DESCRIPTION corrigido, IDENTIFIES colorido) => atualizar golden
       - inesperada => regressao
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synesis_lsp.semantic_tokens import (  # noqa: E402
    TOKEN_TYPES,
    compute_semantic_tokens,
)

FIXTURES = Path(__file__).parent / "fixtures" / "golden"


def decode_tokens(data: list[int], source: str) -> list[str]:
    """Converte o encoding delta do LSP em linhas legiveis e diffaveis."""
    lines = source.splitlines()
    out: list[str] = []
    line = col = 0
    i = 0
    while i < len(data):
        d_line, d_col, length, ttype, tmod = data[i : i + 5]
        line += d_line
        col = d_col if d_line else col + d_col
        texto = lines[line][col : col + length] if line < len(lines) else ""
        out.append(
            f"{line + 1:5d}:{col + 1:<4d} {TOKEN_TYPES[ttype]:<12} mod={tmod} {texto!r}"
        )
        i += 5
    return out


def main() -> int:
    if not FIXTURES.is_dir():
        print(f"ERRO: {FIXTURES} nao existe", file=sys.stderr)
        return 1

    fontes = sorted(
        p for p in FIXTURES.iterdir() if p.suffix in {".syn", ".synt", ".syno", ".synp"}
    )
    if not fontes:
        print(f"ERRO: nenhuma fixture em {FIXTURES}", file=sys.stderr)
        return 1

    for src_path in fontes:
        source = src_path.read_text(encoding="utf-8")
        # relation_names=None => usa _DEFAULT_RELATIONS (mesmo caminho do LSP
        # antes de loadProject terminar). Deterministico entre execucoes.
        result = compute_semantic_tokens(source, f"file:///{src_path.name}", None)
        linhas = decode_tokens(result.data, source)

        golden = src_path.with_suffix(src_path.suffix + ".golden")
        golden.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"{src_path.name}: {len(linhas)} tokens -> {golden.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
