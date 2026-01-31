"""
test_semantic_tokens.py - Testes para colorização semântica

Propósito:
    Validar extração de tokens semânticos de arquivos Synesis.
    Testa keywords, bibrefs, campos, valores e encoding delta.
"""

from __future__ import annotations

from synesis_lsp.semantic_tokens import (
    _TK_KEYWORD,
    _TK_VARIABLE,
    _TK_PROPERTY,
    _TK_STRING,
    _TK_ENUM_MEMBER,
    _TK_NAMESPACE,
    _MOD_DECLARATION,
    _extract_tokens_from_source,
    _encode_deltas,
    compute_semantic_tokens,
)


def test_empty_source():
    """Fonte vazio retorna tokens vazios."""
    result = compute_semantic_tokens("", "test.syn")
    assert result.data == []


def test_source_block():
    """SOURCE @bibref ... END SOURCE gera tokens corretos."""
    source = "SOURCE @smith2020\n    codigo: N/A\nEND SOURCE"
    tokens = _extract_tokens_from_source(source)

    # Linha 0: SOURCE (keyword) + @smith2020 (variable)
    kw_tokens = [t for t in tokens if t[3] == _TK_KEYWORD]
    var_tokens = [t for t in tokens if t[3] == _TK_VARIABLE]

    assert len(kw_tokens) >= 2  # SOURCE + END SOURCE
    assert len(var_tokens) >= 1  # @smith2020

    # SOURCE na posição (0, 0)
    assert kw_tokens[0][0] == 0  # line
    assert kw_tokens[0][1] == 0  # col
    assert kw_tokens[0][2] == 6  # len("SOURCE")
    assert kw_tokens[0][4] == _MOD_DECLARATION  # modifier

    # @smith2020 após SOURCE
    assert var_tokens[0][0] == 0  # line
    assert var_tokens[0][2] == len("@smith2020")  # length inclui @


def test_item_block():
    """ITEM @bibref com campos gera tokens corretos."""
    source = "ITEM @entrevista01\n    ordem_1a: proposito\nEND ITEM"
    tokens = _extract_tokens_from_source(source)

    kw_tokens = [t for t in tokens if t[3] == _TK_KEYWORD]
    var_tokens = [t for t in tokens if t[3] == _TK_VARIABLE]
    prop_tokens = [t for t in tokens if t[3] == _TK_PROPERTY]
    enum_tokens = [t for t in tokens if t[3] == _TK_ENUM_MEMBER]

    # ITEM + END ITEM
    assert len(kw_tokens) >= 2

    # @entrevista01
    assert len(var_tokens) >= 1

    # ordem_1a:
    assert len(prop_tokens) >= 1

    # proposito (valor sem aspas -> EnumMember)
    assert len(enum_tokens) >= 1


def test_ontology_block():
    """ONTOLOGY concept ... END ONTOLOGY gera tokens corretos."""
    source = "ONTOLOGY proposito\n    descricao: texto aqui\nEND ONTOLOGY"
    tokens = _extract_tokens_from_source(source)

    kw_tokens = [t for t in tokens if t[3] == _TK_KEYWORD]
    enum_tokens = [t for t in tokens if t[3] == _TK_ENUM_MEMBER]

    # ONTOLOGY + END ONTOLOGY
    assert len(kw_tokens) >= 2

    # "proposito" como concept (EnumMember)
    concept_tokens = [t for t in enum_tokens if t[0] == 0]
    assert len(concept_tokens) >= 1


def test_quoted_value_is_string():
    """Valores entre aspas são classificados como String."""
    source = '    ordem_1a: "texto entre aspas"'
    tokens = _extract_tokens_from_source(source)

    str_tokens = [t for t in tokens if t[3] == _TK_STRING]
    assert len(str_tokens) >= 1


def test_unquoted_value_is_enum():
    """Valores sem aspas são classificados como EnumMember."""
    source = "    ordem_2a: proposito"
    tokens = _extract_tokens_from_source(source)

    enum_tokens = [t for t in tokens if t[3] == _TK_ENUM_MEMBER]
    assert len(enum_tokens) >= 1


def test_project_keywords():
    """PROJECT e INCLUDE são classificados como Namespace."""
    source = "PROJECT gestao_fe\n    TEMPLATE Davi.synt\nEND PROJECT"
    tokens = _extract_tokens_from_source(source)

    ns_tokens = [t for t in tokens if t[3] == _TK_NAMESPACE]
    assert len(ns_tokens) >= 2  # PROJECT + TEMPLATE (ou END PROJECT)


def test_encode_deltas_empty():
    """Lista vazia produz data vazio."""
    assert _encode_deltas([]) == []


def test_encode_deltas_single():
    """Token único produz deltas absolutos."""
    tokens = [(2, 5, 6, _TK_KEYWORD, _MOD_DECLARATION)]
    data = _encode_deltas(tokens)
    assert data == [2, 5, 6, _TK_KEYWORD, _MOD_DECLARATION]


def test_encode_deltas_same_line():
    """Dois tokens na mesma linha: deltaLine=0, deltaCol relativo."""
    tokens = [
        (0, 0, 6, _TK_KEYWORD, _MOD_DECLARATION),   # SOURCE
        (0, 7, 10, _TK_VARIABLE, 0),                  # @smith2020
    ]
    data = _encode_deltas(tokens)
    assert data == [
        0, 0, 6, _TK_KEYWORD, _MOD_DECLARATION,
        0, 7, 10, _TK_VARIABLE, 0,
    ]


def test_encode_deltas_different_lines():
    """Tokens em linhas diferentes: deltaCol é absoluto quando deltaLine > 0."""
    tokens = [
        (0, 0, 6, _TK_KEYWORD, 0),     # linha 0, col 0
        (2, 4, 8, _TK_PROPERTY, 0),     # linha 2, col 4
    ]
    data = _encode_deltas(tokens)
    assert data == [
        0, 0, 6, _TK_KEYWORD, 0,
        2, 4, 8, _TK_PROPERTY, 0,
    ]


def test_full_syn_file():
    """Teste integrado com conteúdo .syn realista."""
    source = """SOURCE @entrevista01
    codigo: N/A
END SOURCE

ITEM @entrevista01
    ordem_1a: "texto citado aqui"
    ordem_2a: proposito
    justificativa_interna: "justificativa longa"
END ITEM
"""
    result = compute_semantic_tokens(source, "test.syn")

    # Deve ter tokens (data não vazio)
    assert len(result.data) > 0
    # Data deve ser múltiplo de 5 (cada token = 5 ints)
    assert len(result.data) % 5 == 0


def test_full_syno_file():
    """Teste integrado com conteúdo .syno realista."""
    source = """ONTOLOGY dons_do_espirito
    descricao: "Capacitacoes concedidas pelo Espirito Santo"
    ordem_3a: acao_do_espirito
END ONTOLOGY
"""
    result = compute_semantic_tokens(source, "test.syno")

    assert len(result.data) > 0
    assert len(result.data) % 5 == 0
