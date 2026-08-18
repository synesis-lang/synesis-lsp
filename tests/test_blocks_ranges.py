"""
test_blocks_ranges.py - Fim real do bloco em getBlocks

Antes, o fim de um bloco era inferido por adjacência: "a linha anterior ao
início do próximo bloco". O `END SOURCE` / `END ITEM` real nunca era consultado,
então todo espaço entre o fim verdadeiro e o próximo bloco — linhas em branco e,
sobretudo, COMENTÁRIOS — era atribuído ao bloco anterior.

Efeitos observados em produção:
  - cursor num comentário que rotula a fonte seguinte resolvia o bibref ANTERIOR
    (abstract do artigo errado);
  - o synesis-coder inseria o ITEM gerado DEPOIS desse comentário, isto é, no
    território visual da próxima fonte.

Comentários são `%ignore` na gramática: não existem no AST nem no lexer. O fim
precisa ser derivado do texto — é o que `_find_block_end` faz.
"""

from __future__ import annotations

import pytest

from synesis_lsp.blocks import (
    _blocks_from_lex,
    _blocks_from_nodes,
    _blocks_from_regex,
    _extract_blocks,
    _find_block_end,
)


def ranges(blocks):
    return [
        (b["kind"], b["bibref"], b["range"]["start"]["line"], b["range"]["end"]["line"])
        for b in blocks
    ]


def covering(blocks, line):
    """Blocos cujo range cobre `line`."""
    return [
        (b["kind"], b["bibref"])
        for b in blocks
        if b["range"]["start"]["line"] <= line <= b["range"]["end"]["line"]
    ]


# --------------------------------------------------------- o defeito original

COMENTARIO_ENTRE_BLOCOS = (
    "SOURCE @a2019\n"          # 0
    "    title: Primeiro\n"    # 1
    "END SOURCE\n"             # 2
    "ITEM @a2019\n"            # 3
    "    quote: um\n"          # 4
    "END ITEM\n"               # 5
    "\n"                       # 6
    "# Estudo de Silva 2020\n" # 7
    "SOURCE @b2020\n"          # 8
    "    title: Segundo\n"     # 9
    "END SOURCE\n"             # 10
)


def test_comentario_nao_pertence_ao_bloco_anterior():
    """O teste que prova a correção do defeito #3."""
    blocos = _extract_blocks(COMENTARIO_ENTRE_BLOCOS, "x.syn")
    assert covering(blocos, 7) == []


def test_item_termina_no_seu_end():
    blocos = _extract_blocks(COMENTARIO_ENTRE_BLOCOS, "x.syn")
    item = next(b for b in blocos if b["kind"] == "ITEM")
    assert item["range"]["end"]["line"] == 5  # 'END ITEM', não a linha 7


def test_comentario_antes_do_primeiro_source_fica_fora():
    """A F3 decide o destino do cursor; aqui basta não pertencer a ninguém."""
    src = (
        "# comentario de cabecalho\n"  # 0
        "# outra linha\n"              # 1
        "SOURCE @a2019\n"              # 2
        "    title: T\n"               # 3
        "END SOURCE\n"                 # 4
    )
    blocos = _extract_blocks(src, "x.syn")
    assert covering(blocos, 0) == []
    assert covering(blocos, 1) == []
    assert covering(blocos, 2) == [("SOURCE", "a2019")]


def test_linhas_em_branco_nao_pertencem_ao_bloco_anterior():
    src = (
        "SOURCE @a\n"      # 0
        "    x: 1\n"       # 1
        "END SOURCE\n"     # 2
        "\n"               # 3
        "\n"               # 4
        "ITEM @a\n"        # 5
        "    code: C\n"    # 6
        "END ITEM\n"       # 7
    )
    blocos = _extract_blocks(src, "x.syn")
    assert covering(blocos, 3) == []
    assert covering(blocos, 4) == []


# ------------------------------------------------- indentação: END em valores

def test_end_item_indentado_em_valor_multilinha_nao_fecha_o_bloco():
    """
    Um valor de campo multilinha PODE conter uma linha `END ITEM` indentada — e
    isso compila. Sem comparar indentação, o bloco seria truncado no meio.
    """
    src = (
        "ITEM @a\n"                  # 0
        "    note: exemplo\n"        # 1
        "        END ITEM\n"         # 2  <- dentro do valor, indentado
        "        continuacao\n"      # 3
        "END ITEM\n"                 # 4  <- o END real
    )
    lines = src.split("\n")
    assert _find_block_end(lines, 0, "ITEM") == 4


def test_end_de_outro_tipo_nao_fecha_o_bloco():
    src = (
        "SOURCE @a\n"                # 0
        "    description: um\n"      # 1
        "        END ITEM\n"         # 2  <- tipo diferente
        "END SOURCE\n"               # 3
    )
    lines = src.split("\n")
    assert _find_block_end(lines, 0, "SOURCE") == 3


# ------------------------------------------------------ documento em edição

def test_bloco_sem_end_termina_antes_do_proximo():
    src = (
        "ITEM @a\n"        # 0
        "    code: X\n"    # 1
        "\n"               # 2
        "ITEM @b\n"        # 3
        "END ITEM\n"       # 4
    )
    lines = src.split("\n")
    assert _find_block_end(lines, 0, "ITEM") == 2


def test_end_de_tipo_trocado_nao_levanta():
    """`ITEM ... END SOURCE` é inválido, mas getBlocks não pode explodir."""
    src = "ITEM @a\n    code: X\nEND SOURCE\n"
    assert isinstance(_extract_blocks(src, "x.syn"), list)


@pytest.mark.parametrize(
    "nome,src",
    [
        ("vazio", ""),
        ("so comentarios", "# a\n# b\n"),
        ("end orfao", "END ITEM\nEND SOURCE\n"),
        ("bloco aberto no fim", "SOURCE @a\n    x: 1\n"),
        ("so lixo", "@@@ ### !!!\n"),
    ],
)
def test_nao_levanta_em_documento_degenerado(nome, src):
    assert isinstance(_extract_blocks(src, "x.syn"), list)


def test_find_block_end_com_start_fora_do_range():
    assert _find_block_end(["SOURCE @a"], 99, "SOURCE") == 0


# ------------------------------------- paridade entre os 3 caminhos da escada

DOC_VALIDO = (
    "SOURCE @a\n"
    "    description: um\n"
    "END SOURCE\n"
    "\n"
    "# comentario\n"
    "ITEM @a\n"
    "    code: C\n"
    "END ITEM\n"
)


def test_paridade_lex_e_regex():
    """
    A escada AST -> lexer -> regex não pode mudar os ranges: qual degrau roda
    depende do documento compilar, não da intenção do usuário.
    """
    assert ranges(_blocks_from_lex(DOC_VALIDO)) == ranges(_blocks_from_regex(DOC_VALIDO))


def test_paridade_ast_e_lex():
    import synesis

    nodes = synesis.compile_string(DOC_VALIDO, "x.syn")
    assert ranges(_blocks_from_nodes(nodes, DOC_VALIDO)) == ranges(
        _blocks_from_lex(DOC_VALIDO)
    )


def test_comentario_fora_do_range_nos_tres_caminhos():
    import synesis

    nodes = synesis.compile_string(COMENTARIO_ENTRE_BLOCOS, "x.syn")
    for blocos in (
        _blocks_from_nodes(nodes, COMENTARIO_ENTRE_BLOCOS),
        _blocks_from_lex(COMENTARIO_ENTRE_BLOCOS),
        _blocks_from_regex(COMENTARIO_ENTRE_BLOCOS),
    ):
        assert covering(blocos, 7) == []


# ---------------------------------------------------------- não-regressão

def test_documento_comum_sem_comentarios():
    src = (
        "SOURCE @a\n"      # 0
        "    x: 1\n"       # 1
        "END SOURCE\n"     # 2
        "ITEM @a\n"        # 3
        "    code: C\n"    # 4
        "END ITEM\n"       # 5
    )
    assert ranges(_extract_blocks(src, "x.syn")) == [
        ("SOURCE", "a", 0, 2),
        ("ITEM", "a", 3, 5),
    ]


def test_range_mantem_formato_lsp():
    bloco = _extract_blocks("SOURCE @a\n    x: 1\nEND SOURCE\n", "x.syn")[0]
    assert set(bloco) == {"kind", "bibref", "range"}
    assert set(bloco["range"]) == {"start", "end"}
    assert set(bloco["range"]["start"]) == {"line", "character"}
    assert bloco["range"]["end"]["line"] >= bloco["range"]["start"]["line"]


def test_bibref_continua_sem_arroba():
    blocos = _extract_blocks("SOURCE @silva2020\nEND SOURCE\n", "x.syn")
    assert blocos[0]["bibref"] == "silva2020"
