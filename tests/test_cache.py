"""
test_cache.py - Testes unitários para WorkspaceCache

Propósito:
    Validar operações de cache: put, get, invalidate, has.
    Testes isolados sem dependência do compilador synesis.
"""

from __future__ import annotations

from pathlib import Path

from synesis_lsp.cache import CachedCompilation, WorkspaceCache


class FakeCompilationResult:
    """Mock simples de CompilationResult para testes."""

    def __init__(self, name: str = "test"):
        self.name = name


def test_put_get():
    """Armazena e recupera resultado do cache."""
    cache = WorkspaceCache()
    result = FakeCompilationResult("projeto1")
    cache.put("/workspace/a", result, Path("/workspace/a"))

    cached = cache.get("/workspace/a")
    assert cached is not None
    assert cached.result.name == "projeto1"
    assert cached.workspace_root == Path("/workspace/a")
    assert cached.timestamp > 0


def test_get_missing():
    """get retorna None para workspace não cacheado."""
    cache = WorkspaceCache()
    assert cache.get("/workspace/inexistente") is None


def test_invalidate():
    """Invalida e verifica que get retorna None."""
    cache = WorkspaceCache()
    cache.put("/workspace/a", FakeCompilationResult(), Path("/workspace/a"))

    cache.invalidate("/workspace/a")
    assert cache.get("/workspace/a") is None


def test_invalidate_missing():
    """Invalidar workspace inexistente não levanta exceção."""
    cache = WorkspaceCache()
    cache.invalidate("/workspace/inexistente")  # Não deve lançar exceção


def test_has():
    """Verifica presença no cache."""
    cache = WorkspaceCache()
    assert cache.has("/workspace/a") is False

    cache.put("/workspace/a", FakeCompilationResult(), Path("/workspace/a"))
    assert cache.has("/workspace/a") is True

    cache.invalidate("/workspace/a")
    assert cache.has("/workspace/a") is False


def test_multiple_workspaces():
    """Cache isolado por workspace."""
    cache = WorkspaceCache()
    cache.put("/ws/a", FakeCompilationResult("a"), Path("/ws/a"))
    cache.put("/ws/b", FakeCompilationResult("b"), Path("/ws/b"))

    assert cache.get("/ws/a").result.name == "a"
    assert cache.get("/ws/b").result.name == "b"

    # Invalidar um não afeta o outro
    cache.invalidate("/ws/a")
    assert cache.get("/ws/a") is None
    assert cache.get("/ws/b").result.name == "b"


def test_put_overwrites():
    """Put sobrescreve resultado anterior para mesmo workspace."""
    cache = WorkspaceCache()
    cache.put("/ws/a", FakeCompilationResult("v1"), Path("/ws/a"))
    cache.put("/ws/a", FakeCompilationResult("v2"), Path("/ws/a"))

    cached = cache.get("/ws/a")
    assert cached.result.name == "v2"


def test_cached_compilation_defaults():
    """CachedCompilation tem defaults sensatos."""
    cached = CachedCompilation(result=FakeCompilationResult())
    assert cached.timestamp > 0
    assert cached.workspace_root == Path(".")
