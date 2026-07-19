"""
test_blocks_lex_fallback.py - Fallback de getBlocks baseado no lexer

`_extract_blocks` degrada em escada: AST -> lexer -> regex. Este arquivo cobre
o degrau do meio, usado quando o documento não compila (estado normal durante
digitação).

Invariante principal: um `SOURCE @x` escrito na PROSA de um bloco de texto livre
é texto, não declaração. O fallback regex reporta esse bloco fantasma; o
baseado no lexer não.
"""

from __future__ import annotations

import pytest

from synesis_lsp.blocks import _blocks_from_lex, _blocks_from_regex


def kinds(blocks):
    return [(b["kind"], b["bibref"]) for b in blocks]


# ------------------------------------------------ ganho sobre o regex

def test_ignora_bloco_fantasma_em_guidelines():
    """
    Prosa dentro de GUIDELINES pode citar `SOURCE @x` como exemplo. O regex
    casa por posição na linha e reporta um bloco que não existe.
    """
    src = (
        "SOURCE @real\n"
        "    GUIDELINES\n"
        "Exemplo de bloco:\n"
        "SOURCE @ficticio\n"
        "    END GUIDELINES\n"
        "END SOURCE\n"
    )
    assert kinds(_blocks_from_lex(src)) == [("SOURCE", "real")]
    # o fallback antigo erra — documenta o motivo da mudança
    assert ("SOURCE", "ficticio") in kinds(_blocks_from_regex(src))


def test_ignora_bloco_fantasma_em_description():
    src = (
        "SOURCE @real\n"
        "    DESCRIPTION\n"
        "Compare com:\n"
        "ITEM @ficticio\n"
        "    END DESCRIPTION\n"
        "END SOURCE\n"
    )
    assert kinds(_blocks_from_lex(src)) == [("SOURCE", "real")]


def test_description_inline_nao_abre_escopo():
    """`DESCRIPTION texto` é campo (sem END): não pode engolir o resto."""
    src = (
        "SOURCE @a\n"
        "    DESCRIPTION resumo curto\n"
        "END SOURCE\n"
        "\n"
        "ITEM @b\n"
        "    code: X\n"
        "END ITEM\n"
    )
    assert kinds(_blocks_from_lex(src)) == [("SOURCE", "a"), ("ITEM", "b")]


# ------------------------------------- paridade com o comportamento atual

@pytest.mark.parametrize(
    "nome,src",
    [
        ("bloco aberto", "SOURCE @a\n    text: x\n\nITEM @b\n    code: C\n"),
        ("indentacao quebrada", "SOURCE @a\n        x: 1\n    y: 2\nEND SOURCE\n"),
        ("unicode bibref", "SOURCE @josé_2024\n    text: a\nEND SOURCE\n"),
        ("multiplos blocos", "SOURCE @a\nEND SOURCE\nITEM @b\nEND ITEM\n"),
    ],
)
def test_paridade_com_regex_nos_casos_normais(nome, src):
    """Onde o regex acerta, o lexer deve produzir o mesmo resultado."""
    assert kinds(_blocks_from_lex(src)) == kinds(_blocks_from_regex(src))


def test_end_source_nao_vira_bloco():
    src = "SOURCE @a\n    text: x\nEND SOURCE\n"
    assert kinds(_blocks_from_lex(src)) == [("SOURCE", "a")]


# ------------------------------------------------------------ robustez

@pytest.mark.parametrize(
    "nome,src",
    [
        ("vazio", ""),
        ("so lixo", "@@@ !!! ###\n"),
        ("dedent inconsistente", "ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n"),
        ("bibref ausente", "SOURCE\nEND SOURCE\n"),
    ],
)
def test_nao_levanta_em_documento_invalido(nome, src):
    resultado = _blocks_from_lex(src)
    assert isinstance(resultado, list)


def test_range_tem_formato_lsp():
    src = "SOURCE @a\n    text: x\nEND SOURCE\n"
    bloco = _blocks_from_lex(src)[0]
    assert set(bloco) == {"kind", "bibref", "range"}
    assert bloco["range"]["start"]["line"] == 0
    assert bloco["range"]["end"]["line"] >= bloco["range"]["start"]["line"]


def test_bibref_normalizado_sem_arroba():
    src = "SOURCE @silva2020\nEND SOURCE\n"
    assert _blocks_from_lex(src)[0]["bibref"] == "silva2020"
