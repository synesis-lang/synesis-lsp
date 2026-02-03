"""
Testes para synesis_lsp/references.py

Cobertura:
- Find All References para codes
- Find All References para bibrefs
- Inclusão/exclusão de declarações
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from synesis_lsp.references import (
    compute_references,
    _find_code_references,
    _find_bibref_references,
    _normalize_bibref,
)


def _make_cached(ontology_index=None, code_usage=None, bibliography=None, sources=None):
    """Cria CachedCompilation mock."""
    lp = SimpleNamespace(
        ontology_index=ontology_index or {},
        code_usage=code_usage or {},
        bibliography=bibliography or {},
        sources=sources or {}
    )
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(result=result)


class TestComputeReferences:
    """Testa função principal compute_references."""

    def test_no_cache(self):
        """Deve retornar None quando não há cache."""
        result = compute_references(None, "smoking", None)
        assert result is None

    def test_no_word(self):
        """Deve retornar None quando palavra não fornecida."""
        cached = _make_cached()
        result = compute_references(cached, "", None)
        assert result is None


class TestFindCodeReferences:
    """Testa busca de referências a codes."""

    def test_without_declaration(self):
        """Deve excluir declaração quando include_declaration=False."""
        onto_node = SimpleNamespace(
            location=SimpleNamespace(file="test.syno", line=5, column=1)
        )

        lp = SimpleNamespace(
            ontology_index={"smoking": onto_node},
            code_usage={}
        )

        result = _find_code_references(lp, "smoking", None, include_declaration=False)
        assert result is None  # Apenas declaração, sem usos

    def test_code_not_found(self):
        """Deve retornar None quando code não encontrado."""
        lp = SimpleNamespace(ontology_index={}, code_usage={})
        result = _find_code_references(lp, "nonexistent", None, include_declaration=True)
        assert result is None


class TestFindBibrefReferences:
    """Testa busca de referências a bibrefs."""

    def test_without_declaration(self):
        """Deve excluir declaração quando include_declaration=False."""
        bib_entry = SimpleNamespace(
            location=SimpleNamespace(file="refs.bib", line=5, column=1)
        )

        lp = SimpleNamespace(
            bibliography={"smith2020": bib_entry},
            sources={}
        )

        result = _find_bibref_references(lp, "smith2020", None, include_declaration=False)
        assert result is None  # Apenas declaração, sem usos

    def test_bibref_not_found(self):
        """Deve retornar None quando bibref não encontrado."""
        lp = SimpleNamespace(bibliography={}, sources={})
        result = _find_bibref_references(lp, "nonexistent", None, include_declaration=True)
        assert result is None


class TestNormalizeBibref:
    """Testa normalização de bibref."""

    def test_with_at(self):
        """Deve remover @ prefix."""
        assert _normalize_bibref("@smith2020") == "smith2020"

    def test_without_at(self):
        """Deve manter como está."""
        assert _normalize_bibref("smith2020") == "smith2020"

    def test_multiple_at(self):
        """Deve remover todos os @ iniciais."""
        assert _normalize_bibref("@@smith") == "smith"
