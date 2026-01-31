"""
Testes para synesis_lsp/definition.py

Cobertura:
- Go-to @bibref → SourceNode.location
- Go-to código → OntologyNode.location
- Palavra desconhecida → None
- Sem cache / sem linked_project → None
- Conversão 1-based → 0-based
- URI construído com workspace_root
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from lsprotocol.types import Position

from synesis_lsp.definition import compute_definition, _to_uri, _location_to_lsp


def _make_location(file, line=1, column=1):
    return SimpleNamespace(file=Path(file), line=line, column=column)


def _make_cached(sources=None, ontology_index=None, workspace_root=None):
    lp = SimpleNamespace(
        sources=sources or {},
        ontology_index=ontology_index or {},
    )
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(
        result=result,
        workspace_root=workspace_root or Path("d:/projeto"),
    )


class TestGotoBibref:
    """Testa go-to-definition para @bibref."""

    def test_goto_bibref(self):
        src_node = SimpleNamespace(
            location=_make_location("interviews/entrevista01.syn", line=1, column=1),
        )
        cached = _make_cached(sources={"entrevista01": src_node})
        source = "SOURCE @entrevista01\n  tema: educação\n"
        pos = Position(line=0, character=8)  # sobre "entrevista01"

        loc = compute_definition(source, pos, cached)
        assert loc is not None
        assert "entrevista01.syn" in loc.uri
        assert loc.range.start.line == 0  # 1-based → 0-based
        assert loc.range.start.character == 0

    def test_goto_bibref_at_symbol(self):
        """Cursor sobre o @."""
        src_node = SimpleNamespace(
            location=_make_location("entrevista01.syn"),
        )
        cached = _make_cached(sources={"entrevista01": src_node})
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=7)  # sobre "@"

        loc = compute_definition(source, pos, cached)
        assert loc is not None

    def test_goto_bibref_line5(self):
        """Bibref com location em linha diferente."""
        src_node = SimpleNamespace(
            location=_make_location("data/e02.syn", line=5, column=3),
        )
        cached = _make_cached(sources={"e02": src_node})
        source = "algum texto\nSOURCE @e02\n"
        pos = Position(line=1, character=9)

        loc = compute_definition(source, pos, cached)
        assert loc is not None
        assert loc.range.start.line == 4  # 5 → 4 (0-based)
        assert loc.range.start.character == 2  # 3 → 2


class TestGotoCode:
    """Testa go-to-definition para código de ontologia."""

    def test_goto_code(self):
        onto_node = SimpleNamespace(
            location=_make_location("Davi.syno", line=10, column=1),
        )
        cached = _make_cached(ontology_index={"proposito": onto_node})
        source = "  proposito\n"
        pos = Position(line=0, character=3)

        loc = compute_definition(source, pos, cached)
        assert loc is not None
        assert "Davi.syno" in loc.uri
        assert loc.range.start.line == 9  # 10 → 9

    def test_code_not_in_ontology(self):
        cached = _make_cached(ontology_index={})
        source = "  desconhecido\n"
        pos = Position(line=0, character=3)

        loc = compute_definition(source, pos, cached)
        assert loc is None


class TestEdgeCases:
    """Testa casos especiais."""

    def test_no_cache(self):
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=8)
        loc = compute_definition(source, pos, None)
        assert loc is None

    def test_no_linked_project(self):
        result = SimpleNamespace(linked_project=None)
        cached = SimpleNamespace(result=result, workspace_root=Path("d:/proj"))
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=8)
        loc = compute_definition(source, pos, cached)
        assert loc is None

    def test_no_workspace_root(self):
        lp = SimpleNamespace(sources={}, ontology_index={})
        result = SimpleNamespace(linked_project=lp)
        cached = SimpleNamespace(result=result, workspace_root=None)
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=8)
        loc = compute_definition(source, pos, cached)
        assert loc is None

    def test_cursor_on_space(self):
        cached = _make_cached(sources={"e01": SimpleNamespace(location=_make_location("e01.syn"))})
        source = "SOURCE @e01\n"
        pos = Position(line=0, character=6)  # espaço entre SOURCE e @
        loc = compute_definition(source, pos, cached)
        assert loc is None

    def test_line_out_of_range(self):
        cached = _make_cached()
        source = "SOURCE @e01\n"
        pos = Position(line=5, character=0)
        loc = compute_definition(source, pos, cached)
        assert loc is None

    def test_unknown_word(self):
        cached = _make_cached(
            sources={"e01": SimpleNamespace(location=_make_location("e01.syn"))},
        )
        source = "SOURCE @e01\n  tema: educação\n"
        pos = Position(line=1, character=8)  # "educação" - não é bibref nem código
        loc = compute_definition(source, pos, cached)
        assert loc is None


class TestToUri:
    """Testa construção de URI."""

    def test_to_uri_combines_paths(self):
        uri = _to_uri(Path("d:/projeto"), Path("interviews/e01.syn"))
        assert "interviews" in uri
        assert "e01.syn" in uri

    def test_location_to_lsp_converts_1based(self):
        location = _make_location("test.syn", line=3, column=5)
        loc = _location_to_lsp(location, Path("d:/proj"))
        assert loc is not None
        assert loc.range.start.line == 2  # 3 → 2
        assert loc.range.start.character == 4  # 5 → 4
