"""
Testes para synesis_lsp/graph.py

Cobertura:
- Grafo com triples
- Grafo vazio (sem relações)
- Sem cache / sem linked_project
- Filtragem por bibref
- Sanitização de IDs
- Deduplicação de triples
"""

from types import SimpleNamespace

import pytest

from synesis_lsp.graph import get_relation_graph, _sanitize_id


def _make_cached(triples=None, sources=None, code_usage=None):
    lp = SimpleNamespace(
        all_triples=triples,
        sources=sources or {},
        code_usage=code_usage or {},
    )
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(result=result)


class TestGetRelationGraph:
    """Testa geração de grafo Mermaid.js."""

    def test_basic_graph(self):
        triples = [
            ("proposito", "CAUSA", "chamado"),
            ("chamado", "LEVA_A", "missao"),
        ]
        cached = _make_cached(triples=triples)
        result = get_relation_graph(cached)

        assert result["success"] is True
        mermaid = result["mermaidCode"]
        assert "graph LR" in mermaid
        assert "proposito" in mermaid
        assert "CAUSA" in mermaid
        assert "chamado" in mermaid
        assert "missao" in mermaid

    def test_empty_triples(self):
        cached = _make_cached(triples=[])
        result = get_relation_graph(cached)

        assert result["success"] is True
        assert "Sem relações" in result["mermaidCode"]

    def test_none_triples(self):
        cached = _make_cached(triples=None)
        result = get_relation_graph(cached)

        assert result["success"] is True
        assert "Sem relações" in result["mermaidCode"]

    def test_no_cache(self):
        result = get_relation_graph(None)
        assert result["success"] is False
        assert "error" in result

    def test_no_linked_project(self):
        cached = SimpleNamespace(result=SimpleNamespace(linked_project=None))
        result = get_relation_graph(cached)
        assert result["success"] is False

    def test_deduplication(self):
        triples = [
            ("a", "REL", "b"),
            ("a", "REL", "b"),
            ("a", "REL", "b"),
        ]
        cached = _make_cached(triples=triples)
        result = get_relation_graph(cached)

        mermaid = result["mermaidCode"]
        lines = mermaid.strip().split("\n")
        # 1 header + 1 edge (deduplicada)
        assert len(lines) == 2

    def test_single_triple(self):
        triples = [("X", "causes", "Y")]
        cached = _make_cached(triples=triples)
        result = get_relation_graph(cached)

        assert result["success"] is True
        assert "causes" in result["mermaidCode"]


class TestFilterByBibref:
    """Testa filtragem por bibref."""

    def test_filter_by_bibref(self):
        item1 = SimpleNamespace(extra_fields={"ordem_2a": ["proposito", "chamado"]})
        src = SimpleNamespace(items=[item1])
        sources = {"entrevista01": src}

        triples = [
            ("proposito", "CAUSA", "chamado"),
            ("dons", "LEVA_A", "milagres"),
        ]

        cached = _make_cached(triples=triples, sources=sources)
        result = get_relation_graph(cached, bibref="@entrevista01")

        assert result["success"] is True
        mermaid = result["mermaidCode"]
        assert "proposito" in mermaid
        assert "chamado" in mermaid
        # "dons" e "milagres" não são usados por entrevista01
        assert "milagres" not in mermaid

    def test_filter_bibref_no_items(self):
        src = SimpleNamespace(items=[])
        sources = {"e01": src}
        triples = [("a", "R", "b")]
        cached = _make_cached(triples=triples, sources=sources)

        result = get_relation_graph(cached, bibref="e01")
        assert result["success"] is True
        assert "Sem relações" in result["mermaidCode"]

    def test_filter_bibref_unknown(self):
        triples = [("a", "R", "b")]
        cached = _make_cached(triples=triples, sources={})

        result = get_relation_graph(cached, bibref="inexistente")
        assert result["success"] is True
        assert "Sem relações" in result["mermaidCode"]


class TestSanitizeId:
    """Testa sanitização de IDs Mermaid."""

    def test_simple_name(self):
        assert _sanitize_id("proposito") == "proposito"

    def test_with_spaces(self):
        assert _sanitize_id("meu conceito") == "meu_conceito"

    def test_with_special_chars(self):
        assert _sanitize_id("ação-do-espírito") == "a__o_do_esp_rito"

    def test_with_underscores(self):
        assert _sanitize_id("chamado_vocacao") == "chamado_vocacao"
