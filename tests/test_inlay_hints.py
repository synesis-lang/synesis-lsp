"""
Testes para synesis_lsp/inlay_hints.py

Cobertura:
- Hint com bibref válido
- Sem bibliography (cached_result None, bib None, bib vazia)
- Bibref desconhecido não gera hint
- Múltiplos bibrefs na mesma linha
- Múltiplos bibrefs em linhas diferentes
- Range filtering
- Autor com vírgula (sobrenome apenas)
- Autor ausente / ano ausente
- Bibref em contexto SOURCE (não deve gerar hint para keyword)
"""

from types import SimpleNamespace

import pytest
from lsprotocol.types import InlayHintKind, Position, Range

from synesis_lsp.inlay_hints import compute_inlay_hints


def _make_cached(bibliography):
    """Cria um cached_result mock com bibliography."""
    result = SimpleNamespace(bibliography=bibliography)
    return SimpleNamespace(result=result)


BIB = {
    "entrevista01": {
        "author": "Silva, João and Santos, Maria",
        "year": "2023",
        "title": "Entrevista sobre educação",
        "ENTRYTYPE": "misc",
        "ID": "entrevista01",
    },
    "entrevista02": {
        "author": "Oliveira, Ana",
        "year": "2024",
        "title": "Segunda entrevista",
        "ENTRYTYPE": "misc",
        "ID": "entrevista02",
    },
}


class TestBibrefHint:
    """Testa geração de hints para @bibref."""

    def test_single_bibref(self):
        source = "SOURCE @entrevista01\n  tema: educação\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert len(hints) == 1
        assert hints[0].label == " (Silva, 2023)"
        assert hints[0].kind == InlayHintKind.Type
        assert hints[0].position.line == 0
        # character deve apontar para o fim do match @entrevista01
        assert hints[0].position.character == len("SOURCE @entrevista01")

    def test_multiple_bibrefs_same_line(self):
        source = "refs: @entrevista01 e @entrevista02\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert len(hints) == 2
        assert hints[0].label == " (Silva, 2023)"
        assert hints[1].label == " (Oliveira, 2024)"

    def test_multiple_bibrefs_different_lines(self):
        source = "SOURCE @entrevista01\n  tema: x\nSOURCE @entrevista02\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert len(hints) == 2
        assert hints[0].position.line == 0
        assert hints[1].position.line == 2

    def test_padding_left(self):
        source = "SOURCE @entrevista01\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].padding_left is True


class TestNoBibliography:
    """Testa cenários sem bibliography disponível."""

    def test_cached_result_none(self):
        source = "SOURCE @entrevista01\n"
        hints = compute_inlay_hints(source, None)
        assert hints == []

    def test_bibliography_none(self):
        source = "SOURCE @entrevista01\n"
        cached = _make_cached(None)
        hints = compute_inlay_hints(source, cached)
        assert hints == []

    def test_bibliography_empty(self):
        source = "SOURCE @entrevista01\n"
        cached = _make_cached({})
        hints = compute_inlay_hints(source, cached)
        assert hints == []

    def test_no_bibliography_attr(self):
        """cached_result.result sem atributo bibliography."""
        result = SimpleNamespace()
        cached = SimpleNamespace(result=result)
        hints = compute_inlay_hints("SOURCE @entrevista01\n", cached)
        assert hints == []


class TestUnknownBibref:
    """Testa bibrefs não encontrados na bibliography."""

    def test_unknown_bibref_no_hint(self):
        source = "SOURCE @inexistente\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert hints == []

    def test_mix_known_unknown(self):
        source = "SOURCE @entrevista01\nSOURCE @desconhecido\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached)
        assert len(hints) == 1
        assert hints[0].label == " (Silva, 2023)"


class TestRangeFiltering:
    """Testa filtragem por range."""

    def test_range_includes_line(self):
        source = "SOURCE @entrevista01\nSOURCE @entrevista02\n"
        cached = _make_cached(BIB)
        r = Range(start=Position(line=0, character=0), end=Position(line=0, character=50))
        hints = compute_inlay_hints(source, cached, range_=r)
        assert len(hints) == 1
        assert hints[0].label == " (Silva, 2023)"

    def test_range_excludes_line(self):
        source = "SOURCE @entrevista01\nSOURCE @entrevista02\n"
        cached = _make_cached(BIB)
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=50))
        hints = compute_inlay_hints(source, cached, range_=r)
        assert len(hints) == 1
        assert hints[0].label == " (Oliveira, 2024)"

    def test_range_none_returns_all(self):
        source = "SOURCE @entrevista01\nSOURCE @entrevista02\n"
        cached = _make_cached(BIB)
        hints = compute_inlay_hints(source, cached, range_=None)
        assert len(hints) == 2


class TestAuthorFormatting:
    """Testa formatação do autor."""

    def test_author_with_comma_uses_surname(self):
        bib = {"ref1": {"author": "Souza, Carlos and Pereira, Ana", "year": "2020"}}
        source = "SOURCE @ref1\n"
        cached = _make_cached(bib)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].label == " (Souza, 2020)"

    def test_author_without_comma(self):
        bib = {"ref1": {"author": "Carlos Souza", "year": "2020"}}
        source = "SOURCE @ref1\n"
        cached = _make_cached(bib)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].label == " (Carlos Souza, 2020)"

    def test_author_missing(self):
        bib = {"ref1": {"year": "2020"}}
        source = "SOURCE @ref1\n"
        cached = _make_cached(bib)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].label == " (?, 2020)"

    def test_year_missing(self):
        bib = {"ref1": {"author": "Silva, João"}}
        source = "SOURCE @ref1\n"
        cached = _make_cached(bib)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].label == " (Silva, ?)"

    def test_both_missing(self):
        bib = {"ref1": {"title": "Algo"}}
        source = "SOURCE @ref1\n"
        cached = _make_cached(bib)
        hints = compute_inlay_hints(source, cached)
        assert hints[0].label == " (?, ?)"
