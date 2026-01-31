"""
test_server_commands.py - Testes para custom requests do servidor LSP

Propósito:
    Validar handlers de comandos customizados (synesis/loadProject,
    synesis/getProjectStats) usando mocks do compilador.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synesis_lsp.cache import WorkspaceCache


# --- Mocks ---

class FakeStats:
    """Mock de CompilationStats."""

    def __init__(self, sources=10, items=100, ontologies=5, codes=20, chains=3, triples=0):
        self.source_count = sources
        self.item_count = items
        self.ontology_count = ontologies
        self.code_count = codes
        self.chain_count = chains
        self.triple_count = triples


class FakeCompilationResult:
    """Mock de CompilationResult."""

    def __init__(self, stats=None, errors=False, warnings=False):
        self.stats = stats or FakeStats()
        self._has_errors = errors
        self._has_warnings = warnings

    def has_errors(self):
        return self._has_errors

    def has_warnings(self):
        return self._has_warnings


class FakeServer:
    """Mock mínimo de SynesisLanguageServer para testes unitários."""

    def __init__(self):
        self.workspace_cache = WorkspaceCache()
        self.workspace_documents: dict[str, set[str]] = {}
        self.workspace = None


# --- Testes para synesis/getProjectStats ---

def test_get_stats_without_cache():
    """Retorna success=False quando cache está vazio."""
    from synesis_lsp.server import get_project_stats

    ls = FakeServer()
    result = get_project_stats(ls, {"workspaceRoot": "/ws/test"})

    assert result["success"] is False
    assert "não carregado" in result["error"] or "carregado" in result["error"]


def test_get_stats_with_cache():
    """Retorna stats corretos quando cache tem resultado."""
    from synesis_lsp.server import get_project_stats

    ls = FakeServer()
    stats = FakeStats(sources=61, items=10063, ontologies=291, codes=281, chains=5, triples=12)
    fake_result = FakeCompilationResult(stats=stats)
    ls.workspace_cache.put("/ws/test", fake_result, Path("/ws/test"))

    result = get_project_stats(ls, {"workspaceRoot": "/ws/test"})

    assert result["success"] is True
    assert result["stats"]["source_count"] == 61
    assert result["stats"]["item_count"] == 10063
    assert result["stats"]["ontology_count"] == 291
    assert result["stats"]["code_count"] == 281
    assert result["stats"]["chain_count"] == 5
    assert result["stats"]["triple_count"] == 12


def test_get_stats_no_workspace():
    """Retorna success=False quando workspace não pode ser resolvido."""
    from synesis_lsp.server import get_project_stats

    ls = FakeServer()
    result = get_project_stats(ls, {})

    assert result["success"] is False
    assert "Workspace" in result["error"]


# --- Testes para _resolve_workspace_root ---

def test_resolve_from_params_dict():
    """Resolve workspace root a partir de dict com workspaceRoot."""
    from synesis_lsp.server import _resolve_workspace_root

    ls = FakeServer()
    result = _resolve_workspace_root(ls, {"workspaceRoot": "/ws/from_params"})
    assert result == "/ws/from_params"


def test_resolve_from_params_list():
    """Resolve workspace root a partir de lista com dict."""
    from synesis_lsp.server import _resolve_workspace_root

    ls = FakeServer()
    result = _resolve_workspace_root(ls, [{"workspaceRoot": "/ws/from_list"}])
    assert result == "/ws/from_list"


def test_resolve_from_open_documents():
    """Resolve workspace root a partir de documentos abertos."""
    from synesis_lsp.server import _resolve_workspace_root

    ls = FakeServer()
    ls.workspace_documents = {"/ws/open": {"file:///ws/open/test.syn"}}
    result = _resolve_workspace_root(ls, {})
    assert result == "/ws/open"


def test_resolve_returns_none():
    """Retorna None quando nenhuma estratégia funciona."""
    from synesis_lsp.server import _resolve_workspace_root

    ls = FakeServer()
    result = _resolve_workspace_root(ls, {})
    assert result is None
