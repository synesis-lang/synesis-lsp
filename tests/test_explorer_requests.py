"""
test_explorer_requests.py - Testes para custom requests do Explorer

Propósito:
    Validar get_references, get_codes e get_relations usando mocks
    de CachedCompilation com LinkedProject.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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


def _make_cached(
    sources=None,
    code_usage=None,
    ontology_index=None,
    all_triples=None,
    template=None,
    workspace_root=None,
):
    """Cria mock de CachedCompilation com LinkedProject."""
    cached = MagicMock()
    lp = MagicMock()
    lp.sources = sources or {}
    lp.code_usage = code_usage or {}
    lp.ontology_index = ontology_index or {}
    lp.all_triples = all_triples or []
    cached.result.linked_project = lp
    cached.result.template = template
    cached.workspace_root = workspace_root or Path("C:/workspace")
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
    chain_type = SimpleNamespace(name="CHAIN")
    chain_spec = SimpleNamespace(type=chain_type, relations=["R"])
    template = SimpleNamespace(field_specs={"ordem_2a": chain_spec})

    item1 = MagicMock()
    item1.location = _make_location("interviews/entrevista01.syn", 10, 5)
    item1.extra_fields = {"ordem_2a": ["proposito", "chamado_vocacao"]}
    item1.codes = ["proposito"]
    item1.chains = []

    item2 = MagicMock()
    item2.location = _make_location("interviews/entrevista02.syn", 7, 3)
    item2.extra_fields = {}
    item2.codes = ["codigo_sem_ontologia"]
    item2.chains = []

    code_usage = {
        "proposito": [item1] * 2,
        "chamado_vocacao": [item1],
        "codigo_sem_ontologia": [item2],
    }
    ontology_index = {
        "proposito": MagicMock(),
        "chamado_vocacao": MagicMock(),
    }
    cached = _make_cached(
        code_usage=code_usage,
        ontology_index=ontology_index,
        template=template,
    )

    result = get_codes(cached)

    assert result["success"] is True
    assert len(result["codes"]) == 3

    codes_by_name = {c["code"]: c for c in result["codes"]}

    assert codes_by_name["proposito"]["usageCount"] == 2
    assert codes_by_name["proposito"]["ontologyDefined"] is True
    assert codes_by_name["proposito"]["occurrences"]
    assert codes_by_name["proposito"]["occurrences"][0]["context"] == "chain"

    assert codes_by_name["chamado_vocacao"]["usageCount"] == 1
    assert codes_by_name["chamado_vocacao"]["ontologyDefined"] is True

    assert codes_by_name["codigo_sem_ontologia"]["usageCount"] == 1
    assert codes_by_name["codigo_sem_ontologia"]["ontologyDefined"] is False
    assert codes_by_name["codigo_sem_ontologia"]["occurrences"]


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


def test_get_codes_exact_positions():
    """Codes occurrences should have exact positions - Task 1.1."""
    code_spec = SimpleNamespace(type=SimpleNamespace(name="CODE"))
    template = SimpleNamespace(field_specs={"theme": code_spec})

    item = MagicMock()
    item.location = _make_location("test.syn", 10, 1)
    item.codes = ["faith"]
    item.chains = []
    item.extra_fields = {"theme": "faith hope love"}

    # Mock field locations (if available)
    item.field_locations = {
        "theme": SimpleNamespace(line=12, column=10)
    }

    code_usage = {"faith": [item], "hope": [item], "love": [item]}
    cached = _make_cached(code_usage=code_usage, template=template)

    result = get_codes(cached)

    # Should find codes
    assert result["success"] is True
    assert len(result["codes"]) == 3

    # Check that faith has field location (when available)
    faith_code = next((c for c in result["codes"] if c["code"] == "faith"), None)
    assert faith_code is not None
    assert len(faith_code["occurrences"]) > 0


def test_get_codes_multiline_field():
    """Handle codes in multiline field values - Task 1.1."""
    code_spec = SimpleNamespace(type=SimpleNamespace(name="CODE"))
    template = SimpleNamespace(field_specs={"notes": code_spec})

    item = MagicMock()
    item.location = _make_location("test.syn", 10, 1)
    item.codes = []
    item.chains = []
    item.extra_fields = {
        "notes": "Line 1 with prayer\nLine 2 with faith\nLine 3"
    }
    item.field_locations = {
        "notes": SimpleNamespace(line=12, column=10)
    }

    code_usage = {
        "prayer": [item],
        "faith": [item]
    }
    cached = _make_cached(code_usage=code_usage, template=template)

    result = get_codes(cached)

    assert result["success"] is True
    # Should find both codes
    codes_dict = {c["code"]: c for c in result["codes"]}
    assert "prayer" in codes_dict
    assert "faith" in codes_dict


def test_get_codes_fallback_to_item_location():
    """Falls back to item location if field location unavailable - Task 1.1."""
    template = SimpleNamespace(field_specs={})

    item = MagicMock()
    item.location = _make_location("test.syn", 10, 1)
    item.codes = ["unknown_field_code"]
    item.chains = []
    item.extra_fields = {}
    # No field_locations available

    code_usage = {"unknown_field_code": [item]}
    cached = _make_cached(code_usage=code_usage, template=template)

    result = get_codes(cached)

    # Should use item location as fallback
    assert result["success"] is True
    assert len(result["codes"]) == 1
    occ = result["codes"][0]["occurrences"][0]
    assert occ["line"] == 10  # Item location
    assert occ["column"] == 1


def test_get_codes_with_chain_location():
    """Extract location from chain when available - Task 1.1."""
    chain_spec = SimpleNamespace(type=SimpleNamespace(name="CHAIN"), relations=["R"])
    template = SimpleNamespace(field_specs={"chain": chain_spec})

    chain_loc = _make_location("test.syn", 15, 5)
    chain = SimpleNamespace(
        from_code="faith",
        relation="causes",
        to_code="healing",
        location=chain_loc
    )

    item = MagicMock()
    item.location = _make_location("test.syn", 10, 1)
    item.codes = []
    item.chains = [chain]
    item.extra_fields = {}

    code_usage = {"faith": [item], "healing": [item]}
    cached = _make_cached(code_usage=code_usage, template=template)

    result = get_codes(cached)

    assert result["success"] is True

    # Check that codes have chain location (not item location)
    faith_code = next((c for c in result["codes"] if c["code"] == "faith"), None)
    assert faith_code is not None
    if len(faith_code["occurrences"]) > 0:
        occ = faith_code["occurrences"][0]
        assert occ["line"] == 15  # Chain location, not item line 10
        assert occ["context"] == "chain"


# --- Testes para get_relations ---


def test_get_relations_success():
    """Retorna lista de triples."""
    triples = [
        ("proposito", "INFLUENCES", "chamado_vocacao"),
        ("chamado_vocacao", "IS_A", "vocacao"),
        ("trabalho", "RELATES_TO", "adoracao"),
    ]
    chain_loc = _make_location("interviews/entrevista01.syn", 12, 7)
    chain = SimpleNamespace(
        from_code="proposito",
        relation="INFLUENCES",
        to_code="chamado_vocacao",
        location=chain_loc,
        type="QUALIFIED",
    )
    item = SimpleNamespace(chains=[chain])
    src = SimpleNamespace(items=[item])
    sources = {"entrevista01": src}
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    assert len(result["relations"]) == 3

    rel0 = result["relations"][0]
    assert rel0["from"] == "proposito"
    assert rel0["relation"] == "INFLUENCES"
    assert rel0["to"] == "chamado_vocacao"
    assert rel0["location"]["file"] == "interviews/entrevista01.syn"
    assert rel0["type"] == "qualified"  # Task 1.2: normalized to lowercase

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


def test_get_relations_qualified_type():
    """Detect qualified type from chain with explicit type - Task 1.2."""
    chain = SimpleNamespace(
        from_code="faith",
        relation="causes",
        to_code="healing",
        type="CAUSATION",  # Explicit type → qualified
        location=_make_location("test.syn", 15, 5)
    )
    item = SimpleNamespace(chains=[chain], location=_make_location("test.syn", 10, 1))
    src = SimpleNamespace(items=[item])
    sources = {"test": src}

    triples = [("faith", "causes", "healing")]
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    rel = result["relations"][0]
    assert rel["type"] == "qualified"
    assert rel["location"]["line"] == 15
    assert rel["location"]["column"] == 5


def test_get_relations_simple_type():
    """Detect simple type from plain triple without explicit type - Task 1.2."""
    # Chain without explicit type → simple
    chain = SimpleNamespace(
        from_code="prayer",
        relation="leads_to",
        to_code="peace",
        location=_make_location("test.syn", 20, 8)
    )
    item = SimpleNamespace(chains=[chain])
    src = SimpleNamespace(items=[item])
    sources = {"test": src}

    triples = [("prayer", "leads_to", "peace")]
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    rel = result["relations"][0]
    assert rel["type"] == "simple"


def test_get_relations_location_from_tuple():
    """Extract location from tuple[3] - Task 1.2."""
    # Chain as tuple with location in 4th element
    chain = (
        "faith",
        "causes",
        "miracles",
        _make_location("test.syn", 25, 12)  # Location in tuple[3]
    )
    item = SimpleNamespace(chains=[chain])
    src = SimpleNamespace(items=[item])
    sources = {"test": src}

    triples = [("faith", "causes", "miracles")]
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    rel = result["relations"][0]
    assert rel["location"]["line"] == 25
    assert rel["location"]["column"] == 12


def test_get_relations_dict_location():
    """Extract location from dict["location"] - Task 1.2."""
    chain = {
        "from": "grace",
        "relation": "enables",
        "to": "salvation",
        "location": _make_location("test.syn", 30, 5)
    }
    item = SimpleNamespace(chains=[chain])
    src = SimpleNamespace(items=[item])
    sources = {"test": src}

    triples = [("grace", "enables", "salvation")]
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    rel = result["relations"][0]
    assert rel["location"]["line"] == 30
    assert rel["location"]["column"] == 5


def test_get_relations_fallback_to_item_location():
    """Fall back to item location if chain has none - Task 1.2."""
    chain = SimpleNamespace(
        from_code="hope",
        relation="inspires",
        to_code="action"
        # No location attribute
    )
    item = SimpleNamespace(
        chains=[chain],
        location=_make_location("test.syn", 35, 1)
    )
    src = SimpleNamespace(items=[item])
    sources = {"test": src}

    triples = [("hope", "inspires", "action")]
    cached = _make_cached(all_triples=triples, sources=sources)

    result = get_relations(cached)

    assert result["success"] is True
    rel = result["relations"][0]
    assert rel["location"]["line"] == 35  # Item location used
    assert rel["location"]["column"] == 1


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
