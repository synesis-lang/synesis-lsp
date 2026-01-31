"""
Testes para synesis_lsp/rename.py

Cobertura:
- prepareRename: bibref, código, desconhecido, sem cache
- compute_rename bibref: WorkspaceEdit com TextEdits
- compute_rename código: WorkspaceEdit com TextEdits
- Leitura de arquivos e geração de edits
- Sem cache / sem linked_project → None
- _word_range
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lsprotocol.types import Position

from synesis_lsp.rename import (
    prepare_rename,
    compute_rename,
    _find_and_replace_in_file,
    _word_range,
)


def _make_location(file, line=1, column=1):
    return SimpleNamespace(file=Path(file), line=line, column=column)


def _make_cached(sources=None, ontology_index=None, code_usage=None, workspace_root=None):
    lp = SimpleNamespace(
        sources=sources or {},
        ontology_index=ontology_index or {},
        code_usage=code_usage or {},
    )
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(
        result=result,
        workspace_root=workspace_root or Path(tempfile.gettempdir()),
    )


class TestPrepareRename:
    """Testa prepareRename."""

    def test_prepare_bibref(self):
        src = SimpleNamespace(location=_make_location("e01.syn"))
        cached = _make_cached(sources={"entrevista01": src})
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=9)

        result = prepare_rename(source, pos, cached)
        assert result is not None
        assert result.start.character == 7  # início de @entrevista01
        assert result.end.character == 20  # fim de @entrevista01

    def test_prepare_code(self):
        onto = SimpleNamespace(location=_make_location("onto.syno"))
        cached = _make_cached(ontology_index={"proposito": onto})
        source = "  proposito\n"
        pos = Position(line=0, character=4)

        result = prepare_rename(source, pos, cached)
        assert result is not None
        assert result.start.character == 2
        assert result.end.character == 11

    def test_prepare_unknown_word(self):
        cached = _make_cached()
        source = "  desconhecido\n"
        pos = Position(line=0, character=4)

        result = prepare_rename(source, pos, cached)
        assert result is None

    def test_prepare_no_cache(self):
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = prepare_rename(source, pos, None)
        assert result is None

    def test_prepare_no_linked_project(self):
        result_ns = SimpleNamespace(linked_project=None)
        cached = SimpleNamespace(result=result_ns)
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = prepare_rename(source, pos, cached)
        assert result is None

    def test_prepare_bibref_not_in_sources(self):
        cached = _make_cached(sources={})
        source = "SOURCE @desconhecido\n"
        pos = Position(line=0, character=10)
        result = prepare_rename(source, pos, cached)
        assert result is None


class TestComputeRenameBibref:
    """Testa rename de bibref com arquivos temporários."""

    def test_rename_bibref(self, tmp_path):
        # Criar arquivo .syn temporário
        syn_file = tmp_path / "interviews" / "e01.syn"
        syn_file.parent.mkdir(parents=True)
        syn_file.write_text(
            "SOURCE @entrevista01\n  tema: educação\nEND\n", encoding="utf-8"
        )

        src_loc = _make_location("interviews/e01.syn", line=1, column=1)
        item_loc = _make_location("interviews/e01.syn", line=2, column=1)
        item = SimpleNamespace(location=item_loc)
        src = SimpleNamespace(location=src_loc, items=[item])

        cached = _make_cached(
            sources={"entrevista01": src},
            workspace_root=tmp_path,
        )

        source = "SOURCE @entrevista01\n  tema: educação\nEND\n"
        pos = Position(line=0, character=9)

        result = compute_rename(source, pos, "entrevista01_novo", cached)
        assert result is not None
        assert result.changes is not None
        assert len(result.changes) == 1

        uri = syn_file.as_uri()
        edits = result.changes[uri]
        assert len(edits) == 1
        assert edits[0].new_text == "@entrevista01_novo"

    def test_rename_bibref_multiple_occurrences(self, tmp_path):
        syn_file = tmp_path / "e01.syn"
        syn_file.write_text(
            "SOURCE @e01\n  ref: @e01\nEND\n", encoding="utf-8"
        )

        src_loc = _make_location("e01.syn")
        src = SimpleNamespace(location=src_loc, items=[])

        cached = _make_cached(
            sources={"e01": src},
            workspace_root=tmp_path,
        )

        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)

        result = compute_rename(source, pos, "e01_novo", cached)
        assert result is not None
        uri = syn_file.as_uri()
        edits = result.changes[uri]
        assert len(edits) == 2

    def test_rename_bibref_no_match(self, tmp_path):
        syn_file = tmp_path / "e01.syn"
        syn_file.write_text("SOURCE @outro\nEND\n", encoding="utf-8")

        src_loc = _make_location("e01.syn")
        src = SimpleNamespace(location=src_loc, items=[])

        cached = _make_cached(
            sources={"entrevista01": src},
            workspace_root=tmp_path,
        )

        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=9)

        result = compute_rename(source, pos, "novo", cached)
        # Arquivo não contém @entrevista01
        assert result is None


class TestComputeRenameCode:
    """Testa rename de código com arquivos temporários."""

    def test_rename_code(self, tmp_path):
        # Criar arquivo .syno
        syno_file = tmp_path / "onto.syno"
        syno_file.write_text(
            "ONTOLOGY proposito\n  descricao: propósito de vida\nEND\n",
            encoding="utf-8",
        )

        # Criar arquivo .syn que usa o código
        syn_file = tmp_path / "e01.syn"
        syn_file.write_text(
            "SOURCE @e01\n  ordem_2a: proposito\nEND\n",
            encoding="utf-8",
        )

        onto_loc = _make_location("onto.syno", line=1, column=1)
        onto = SimpleNamespace(location=onto_loc)

        item_loc = _make_location("e01.syn", line=2, column=1)
        item = SimpleNamespace(location=item_loc)

        cached = _make_cached(
            ontology_index={"proposito": onto},
            code_usage={"proposito": [item]},
            workspace_root=tmp_path,
        )

        source = "  proposito\n"
        pos = Position(line=0, character=4)

        result = compute_rename(source, pos, "objetivo", cached)
        assert result is not None
        assert len(result.changes) == 2

        # Verificar edits no .syno
        syno_uri = syno_file.as_uri()
        assert syno_uri in result.changes
        syno_edits = result.changes[syno_uri]
        assert any(e.new_text == "objetivo" for e in syno_edits)

        # Verificar edits no .syn
        syn_uri = syn_file.as_uri()
        assert syn_uri in result.changes

    def test_rename_code_not_in_ontology(self):
        cached = _make_cached(ontology_index={})
        source = "  desconhecido\n"
        pos = Position(line=0, character=4)
        result = compute_rename(source, pos, "novo", cached)
        assert result is None


class TestComputeRenameEdgeCases:
    """Testa casos especiais de rename."""

    def test_no_cache(self):
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = compute_rename(source, pos, "novo", None)
        assert result is None

    def test_no_linked_project(self):
        result_ns = SimpleNamespace(linked_project=None)
        cached = SimpleNamespace(result=result_ns, workspace_root=Path("."))
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = compute_rename(source, pos, "novo", cached)
        assert result is None

    def test_no_workspace_root(self):
        lp = SimpleNamespace(sources={}, ontology_index={}, code_usage={})
        result_ns = SimpleNamespace(linked_project=lp)
        cached = SimpleNamespace(result=result_ns, workspace_root=None)
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = compute_rename(source, pos, "novo", cached)
        assert result is None

    def test_line_out_of_range(self):
        cached = _make_cached()
        source = "SOURCE @e01\n"
        pos = Position(line=5, character=0)
        result = compute_rename(source, pos, "novo", cached)
        assert result is None

    def test_new_name_strips_at(self, tmp_path):
        """Se usuário digita @novo_nome, o @ é removido."""
        syn_file = tmp_path / "e01.syn"
        syn_file.write_text("SOURCE @e01\nEND\n", encoding="utf-8")

        src = SimpleNamespace(
            location=_make_location("e01.syn"),
            items=[],
        )
        cached = _make_cached(
            sources={"e01": src},
            workspace_root=tmp_path,
        )

        source = "SOURCE @e01\n"
        pos = Position(line=0, character=8)
        result = compute_rename(source, pos, "@novo", cached)

        assert result is not None
        uri = syn_file.as_uri()
        assert result.changes[uri][0].new_text == "@novo"


class TestFindAndReplace:
    """Testa busca e substituição em arquivo."""

    def test_find_occurrences(self, tmp_path):
        import re

        f = tmp_path / "test.syn"
        f.write_text("abc proposito xyz\nproposito\n  proposito outro\n", encoding="utf-8")

        pattern = re.compile(r"(?<!\w)proposito(?!\w)")
        edits = _find_and_replace_in_file(f, pattern, "objetivo")

        assert len(edits) == 3
        assert edits[0].range.start.line == 0
        assert edits[1].range.start.line == 1
        assert edits[2].range.start.line == 2

    def test_file_not_found(self, tmp_path):
        import re

        f = tmp_path / "inexistente.syn"
        pattern = re.compile(r"test")
        edits = _find_and_replace_in_file(f, pattern, "novo")
        assert edits == []


class TestWordRange:
    """Testa _word_range."""

    def test_simple_word(self):
        start, end = _word_range("  proposito", 4)
        assert start == 2
        assert end == 11

    def test_at_bibref(self):
        start, end = _word_range("SOURCE @entrevista01", 9)
        assert start == 7
        assert end == 20

    def test_at_start(self):
        start, end = _word_range("abc", 0)
        assert start == 0
        assert end == 3
