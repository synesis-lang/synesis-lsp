"""
test_explorer_requests.py - Testes para custom requests do Explorer

Propósito:
    Validar get_references, get_codes e get_relations usando mocks
    de CachedCompilation com LinkedProject.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from synesis_lsp.explorer_requests import get_references, get_codes, get_relations


# --- Helpers para criar mocks ---


def _make_source(bibref, fields=None, items=None, location=None):
    """Cria mock de SourceNode."""
    src = MagicMock()
    src.bibref = bibref
    src.fields = fields or {}
    src.items = items or []
    src.location = location
    return src


def _make_location(file="test.syn", line=1, column=1):
    """Cria mock de SourceLocation."""
    loc = MagicMock()
    loc.file = file
    loc.line = line
    loc.column = column
    return loc


def _make_cached(sources=None, code_usage=None, ontology_index=None, all_triples=None):
    """Cria mock de CachedCompilation com LinkedProject."""
    cached = MagicMock()
    lp = MagicMock()
    lp.sources = sources or {}
    lp.code_usage = code_usage or {}
    lp.ontology_index = ontology_index or {}
    lp.all_triples = all_triples or []
    cached.result.linked_project = lp
    return cached


# --- Testes para get_references ---


def test_get_references_success():
    """Retorna lista de SOURCEs com contagem de items."""
    loc1 = _make_location("entrevista01.syn", 1, 1)
    loc2 = _make_location("entrevista02.syn", 1, 1)
    sources = {
        "entrevista01": _make_source(
            "@entrevista01",
            fields={"codigo": "N/A"},
            items=[MagicMock()] * 5,
            location=loc1,
        ),
        "entrevista02": _make_source(
            "@entrevista02",
            fields={"codigo": "BR-02"},
            items=[MagicMock()] * 3,
            location=loc2,
        ),
    }
    cached = _make_cached(sources=sources)

    result = get_references(cached)

    assert result["success"] is True
    assert len(result["references"]) == 2

    ref1 = result["references"][0]
    assert ref1["bibref"] == "@entrevista01"
    assert ref1["itemCount"] == 5
    assert ref1["fields"]["codigo"] == "N/A"
    assert ref1["location"]["file"] == "entrevista01.syn"
    assert ref1["location"]["line"] == 1

    ref2 = result["references"][1]
    assert ref2["bibref"] == "@entrevista02"
    assert ref2["itemCount"] == 3


def test_get_references_empty():
    """Projeto sem sources retorna lista vazia."""
    cached = _make_cached(sources={})

    result = get_references(cached)
    assert result["success"] is True
    assert result["references"] == []


def test_get_references_no_cache():
    """Sem cache retorna success=False."""
    result = get_references(None)
    assert result["success"] is False
    assert "carregado" in result["error"]


def test_get_references_no_linked_project():
    """Cache sem linked_project retorna success=False."""
    cached = MagicMock()
    cached.result.linked_project = None

    result = get_references(cached)
    assert result["success"] is False


# --- Testes para get_codes ---


def test_get_codes_success():
    """Retorna lista de códigos com frequência de uso."""
    code_usage = {
        "proposito": [MagicMock()] * 321,
        "chamado_vocacao": [MagicMock()] * 150,
        "codigo_sem_ontologia": [MagicMock()] * 5,
    }
    ontology_index = {
        "proposito": MagicMock(),
        "chamado_vocacao": MagicMock(),
    }
    cached = _make_cached(code_usage=code_usage, ontology_index=ontology_index)

    result = get_codes(cached)

    assert result["success"] is True
    assert len(result["codes"]) == 3

    codes_by_name = {c["code"]: c for c in result["codes"]}

    assert codes_by_name["proposito"]["usageCount"] == 321
    assert codes_by_name["proposito"]["ontologyDefined"] is True

    assert codes_by_name["chamado_vocacao"]["usageCount"] == 150
    assert codes_by_name["chamado_vocacao"]["ontologyDefined"] is True

    assert codes_by_name["codigo_sem_ontologia"]["usageCount"] == 5
    assert codes_by_name["codigo_sem_ontologia"]["ontologyDefined"] is False


def test_get_codes_empty():
    """Projeto sem codes retorna lista vazia."""
    cached = _make_cached(code_usage={})

    result = get_codes(cached)
    assert result["success"] is True
    assert result["codes"] == []


def test_get_codes_no_cache():
    """Sem cache retorna success=False."""
    result = get_codes(None)
    assert result["success"] is False


# --- Testes para get_relations ---


def test_get_relations_success():
    """Retorna lista de triples."""
    triples = [
        ("proposito", "INFLUENCES", "chamado_vocacao"),
        ("chamado_vocacao", "IS_A", "vocacao"),
        ("trabalho", "RELATES_TO", "adoracao"),
    ]
    cached = _make_cached(all_triples=triples)

    result = get_relations(cached)

    assert result["success"] is True
    assert len(result["relations"]) == 3

    rel0 = result["relations"][0]
    assert rel0["from"] == "proposito"
    assert rel0["relation"] == "INFLUENCES"
    assert rel0["to"] == "chamado_vocacao"

    rel2 = result["relations"][2]
    assert rel2["from"] == "trabalho"
    assert rel2["to"] == "adoracao"


def test_get_relations_empty():
    """Projeto sem triples retorna lista vazia."""
    cached = _make_cached(all_triples=[])

    result = get_relations(cached)
    assert result["success"] is True
    assert result["relations"] == []


def test_get_relations_no_cache():
    """Sem cache retorna success=False."""
    result = get_relations(None)
    assert result["success"] is False


# --- Testes de source sem location ---


def test_get_references_no_location():
    """SOURCE sem location não inclui campo location."""
    sources = {
        "ref1": _make_source("@ref1", location=None),
    }
    cached = _make_cached(sources=sources)

    result = get_references(cached)
    assert result["success"] is True
    assert "location" not in result["references"][0]
