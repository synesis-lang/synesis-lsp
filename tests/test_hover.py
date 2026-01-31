"""
test_hover.py - Testes para textDocument/hover

Propósito:
    Validar hover contextual para @bibref, campos e códigos.
    Usa mocks de CompilationResult, bibliography, template e linked_project.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lsprotocol.types import Position

from synesis_lsp.hover import (
    compute_hover,
    _get_word_at_position,
    _is_field_name,
)


# --- Helpers para criar mocks ---


def _make_cached_result(bibliography=None, template=None, linked_project=None):
    """Cria mock de CachedCompilation com result."""
    cached = MagicMock()
    cached.result.bibliography = bibliography
    cached.result.template = template
    cached.result.linked_project = linked_project
    return cached


def _make_field_spec(name, type_name="TEXT", scope_name="ITEM", description=None):
    """Cria mock de FieldSpec."""
    spec = MagicMock()
    spec.name = name
    spec.type.name = type_name
    spec.scope.name = scope_name
    spec.description = description
    return spec


def _make_ontology(concept, description="", fields=None):
    """Cria mock de OntologyNode."""
    onto = MagicMock()
    onto.concept = concept
    onto.description = description
    onto.fields = fields or {}
    return onto


# --- Testes para _get_word_at_position ---


def test_get_word_simple():
    """Extrai palavra simples."""
    word = _get_word_at_position("ordem_1a: valor", 0)
    assert word == "ordem_1a"


def test_get_word_bibref():
    """Extrai @bibref incluindo @."""
    word = _get_word_at_position("SOURCE @entrevista01", 7)
    assert word == "@entrevista01"


def test_get_word_middle():
    """Extrai palavra com cursor no meio."""
    word = _get_word_at_position("ordem_1a: proposito", 12)
    assert word == "proposito"


def test_get_word_end_of_line():
    """Cursor além do fim da linha retorna None."""
    word = _get_word_at_position("abc", 10)
    assert word is None


def test_get_word_on_space():
    """Cursor em espaço retorna None."""
    word = _get_word_at_position("abc def", 3)
    assert word is None


def test_get_word_on_colon():
    """Cursor em ':' retorna None."""
    word = _get_word_at_position("campo: valor", 5)
    assert word is None


# --- Testes para _is_field_name ---


def test_is_field_name_true():
    """Palavra seguida de ':' é nome de campo."""
    assert _is_field_name("    ordem_1a: valor", 4, "ordem_1a") is True


def test_is_field_name_false():
    """Palavra NÃO seguida de ':' não é nome de campo."""
    assert _is_field_name("    proposito", 4, "proposito") is False


def test_is_field_name_with_spaces():
    """Palavra com espaços antes de ':' é nome de campo."""
    assert _is_field_name("    campo  : valor", 4, "campo") is True


# --- Testes para hover @bibref ---


def test_hover_bibref():
    """Hover em @bibref mostra título, autor e ano."""
    source = "SOURCE @entrevista01\n    codigo: N/A\nEND SOURCE"
    bib = {
        "entrevista01": {
            "title": "Entrevista sobre empreendedorismo",
            "author": "Silva, J.",
            "year": "2023",
            "ENTRYTYPE": "misc",
        }
    }
    cached = _make_cached_result(bibliography=bib)

    result = compute_hover(source, Position(line=0, character=8), cached)

    assert result is not None
    md = result.contents.value
    assert "Entrevista sobre empreendedorismo" in md
    assert "Silva, J." in md
    assert "2023" in md
    assert "misc" in md


def test_hover_bibref_not_found():
    """Hover em @bibref não encontrado retorna None."""
    source = "SOURCE @desconhecido\n    codigo: N/A\nEND SOURCE"
    bib = {"entrevista01": {"title": "Outro"}}
    cached = _make_cached_result(bibliography=bib)

    result = compute_hover(source, Position(line=0, character=8), cached)
    assert result is None


def test_hover_bibref_no_cache():
    """Hover em @bibref sem cache retorna None."""
    source = "SOURCE @entrevista01\n    codigo: N/A\nEND SOURCE"

    result = compute_hover(source, Position(line=0, character=8), None)
    assert result is None


# --- Testes para hover em campo ---


def test_hover_field():
    """Hover em campo mostra tipo e escopo do template."""
    source = "    ordem_1a: \"texto citado\""
    spec = _make_field_spec("ordem_1a", "QUOTATION", "ITEM", "Campo de citação principal")
    template = MagicMock()
    template.field_specs = {"ordem_1a": spec}
    cached = _make_cached_result(template=template)

    result = compute_hover(source, Position(line=0, character=5), cached)

    assert result is not None
    md = result.contents.value
    assert "ordem_1a" in md
    assert "QUOTATION" in md
    assert "ITEM" in md
    assert "citação principal" in md


def test_hover_field_not_in_template():
    """Hover em campo não definido no template retorna None."""
    source = "    campo_inexistente: valor"
    template = MagicMock()
    template.field_specs = {}
    cached = _make_cached_result(template=template)

    result = compute_hover(source, Position(line=0, character=5), cached)
    assert result is None


def test_hover_field_no_template():
    """Hover em campo sem template no cache retorna None."""
    source = "    ordem_1a: valor"
    cached = _make_cached_result(template=None)

    result = compute_hover(source, Position(line=0, character=5), cached)
    assert result is None


# --- Testes para hover em código ---


def test_hover_code():
    """Hover em código mostra ontologia e contagem de uso."""
    source = "    ordem_2a: proposito"
    onto = _make_ontology(
        "proposito",
        description="Sentido de missão definido pela vontade de Deus",
        fields={"ordem_3a": "categoria_superior"},
    )
    lp = MagicMock()
    lp.ontology_index = {"proposito": onto}
    lp.code_usage = {"proposito": [MagicMock()] * 321}
    cached = _make_cached_result(linked_project=lp)

    result = compute_hover(source, Position(line=0, character=14), cached)

    assert result is not None
    md = result.contents.value
    assert "proposito" in md
    assert "Sentido de missão" in md
    assert "321" in md
    assert "ordem_3a" in md


def test_hover_code_not_found():
    """Hover em código não encontrado na ontologia retorna None."""
    source = "    ordem_2a: codigo_inexistente"
    lp = MagicMock()
    lp.ontology_index = {}
    cached = _make_cached_result(linked_project=lp)

    result = compute_hover(source, Position(line=0, character=14), cached)
    assert result is None


def test_hover_code_no_linked_project():
    """Hover em código sem linked_project retorna None."""
    source = "    ordem_2a: proposito"
    cached = _make_cached_result(linked_project=None)

    result = compute_hover(source, Position(line=0, character=14), cached)
    assert result is None


# --- Testes gerais ---


def test_hover_empty_source():
    """Hover em fonte vazio retorna None."""
    result = compute_hover("", Position(line=0, character=0), None)
    assert result is None


def test_hover_line_out_of_range():
    """Hover em linha fora do range retorna None."""
    result = compute_hover("abc", Position(line=5, character=0), None)
    assert result is None


def test_hover_on_keyword():
    """Hover em keyword (SOURCE) sem cache retorna None."""
    source = "SOURCE @entrevista01"
    result = compute_hover(source, Position(line=0, character=2), None)
    assert result is None


def test_hover_priority_bibref_over_code():
    """@bibref tem prioridade sobre código."""
    source = "ITEM @entrevista01"
    bib = {
        "entrevista01": {
            "title": "Entrevista",
            "author": "A.",
            "year": "2024",
            "ENTRYTYPE": "misc",
        }
    }
    onto = _make_ontology("entrevista01")
    lp = MagicMock()
    lp.ontology_index = {"entrevista01": onto}
    lp.code_usage = {}
    cached = _make_cached_result(bibliography=bib, linked_project=lp)

    # Cursor em @entrevista01 — deve retornar bibref, não ontologia
    result = compute_hover(source, Position(line=0, character=6), cached)

    assert result is not None
    md = result.contents.value
    assert "Entrevista" in md  # Título da bibliografia
    assert "Ontologia" not in md
