"""
Opção synesisExplorer.diagnostics.checkCodes.

Desligada (padrão), código sem conceito na ontologia vira um único resumo E090
no .synp; ligada, um E004 por ocorrência. Trocar a opção recompila o projeto
em cache e limpa os arquivos que deixaram de ter diagnóstico.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import synesis_lsp.server as server
from synesis_lsp.cache import WorkspaceCache

TEMPLATE = """\
TEMPLATE t
SOURCE FIELDS
    OPTIONAL note
END SOURCE FIELDS
ITEM FIELDS
    REQUIRED code
END ITEM FIELDS
FIELD note TYPE TEXT SCOPE SOURCE END FIELD
FIELD code TYPE CODE SCOPE ITEM END FIELD
"""

SYN = """\
SOURCE @a
    note: x
END SOURCE

ITEM @a
    code: alfa, beta
END ITEM
"""


class _FakeServer:
    """O mínimo do SynesisLanguageServer que a recompilação usa."""

    def __init__(self):
        self.check_codes = False
        self.workspace_cache = WorkspaceCache()
        self.workspace_documents: dict[str, set[str]] = {}
        self._project_diagnostic_uris: dict[str, set[str]] = {}
        self._context_versions: dict[str, int] = {}
        self._last_focused_uri = None
        self.published: dict[str, list] = {}

    def publish_diagnostics(self, uri, diagnostics):
        self.published[uri] = list(diagnostics)


@pytest.fixture
def projeto(tmp_path):
    (tmp_path / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "t.syn").write_text(SYN, encoding="utf-8")
    (tmp_path / "t.synp").write_text(
        'PROJECT t\n    TEMPLATE "t.synt"\n    INCLUDE ANNOTATIONS "t.syn"\nEND PROJECT\n',
        encoding="utf-8",
    )
    return tmp_path


def _codes(diagnostics) -> list[str]:
    return [getattr(d, "code", None) for d in diagnostics]


def _uri(path: Path) -> str:
    return path.resolve().as_uri()


def test_setting_le_caminho_aninhado():
    settings = {"synesisExplorer": {"diagnostics": {"checkCodes": True}}}
    assert server._setting(settings, "synesisExplorer", "diagnostics", "checkCodes") is True
    assert server._setting({}, "synesisExplorer", "diagnostics", "checkCodes") is None
    assert server._setting({"synesisExplorer": 3}, "synesisExplorer", "diagnostics") is None


def test_trocar_check_codes_recompila_e_limpa_avisos(projeto):
    from synesis.compiler import SynesisCompiler

    ls = _FakeServer()
    synp = projeto / "t.synp"

    # Projeto compilado com checkCodes ligado: E004 no .syn
    ls.check_codes = True
    result = SynesisCompiler(synp, check_codes=True).compile()
    ls.workspace_cache.put("ws", result, projeto, fingerprint="f", check_codes=True, synp_path=synp)
    server._publish_compilation_diagnostics(ls, result.validation_result, projeto)
    assert "SYNESIS_E004" in _codes(ls.published[_uri(projeto / "t.syn")])

    # Desliga: recompila, o .syn fica limpo e o .synp recebe o resumo
    ls.check_codes = False
    asyncio.run(server._recompile_after_check_codes_change(ls))

    assert ls.published[_uri(projeto / "t.syn")] == []
    assert _codes(ls.published[_uri(synp)]) == ["SYNESIS_E090"]
    cached = ls.workspace_cache.get("ws")
    assert cached.check_codes is False and cached.synp_path == synp


def test_publicacao_nao_limpa_documento_aberto(projeto):
    """Documento aberto é republicado por validate_document, não zerado aqui."""
    from synesis.compiler import SynesisCompiler

    ls = _FakeServer()
    synp = projeto / "t.synp"
    syn_uri = _uri(projeto / "t.syn")
    ls.workspace_documents["ws"] = {syn_uri}

    com = SynesisCompiler(synp, check_codes=True).compile()
    server._publish_compilation_diagnostics(ls, com.validation_result, projeto)
    ls.published.clear()

    sem = SynesisCompiler(synp, check_codes=False).compile()
    server._publish_compilation_diagnostics(ls, sem.validation_result, projeto)
    assert syn_uri not in ls.published
