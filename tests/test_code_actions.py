"""
Testes para synesis_lsp/code_actions.py

Cobertura:
- Quick fixes para campos desconhecidos
- Sugestões baseadas em distância de edição
- Inserção de campos obrigatórios
- Extração de nomes de campos de mensagens
- Cálculo de distância de Levenshtein
"""

from types import SimpleNamespace

import pytest
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from synesis_lsp.code_actions import (
    compute_code_actions,
    _extract_field_name_from_message,
    _find_similar_fields,
    _levenshtein_distance,
    _suggest_field_corrections,
)


def _make_cached(template=None):
    """Cria CachedCompilation mock."""
    result = SimpleNamespace(template=template)
    return SimpleNamespace(result=result)


def _make_diagnostic(message: str, line: int, col_start: int, col_end: int) -> Diagnostic:
    """Cria Diagnostic mock."""
    return Diagnostic(
        range=Range(
            start=Position(line=line, character=col_start),
            end=Position(line=line, character=col_end)
        ),
        severity=DiagnosticSeverity.Error,
        message=message,
        source="synesis"
    )


class TestComputeCodeActions:
    """Testa função principal compute_code_actions."""

    def test_no_diagnostics(self):
        """Deve retornar None quando não há diagnósticos."""
        empty_range = Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0)
        )
        result = compute_code_actions("file:///test.syn", empty_range, [], None)
        assert result is None

    def test_unknown_field_diagnostic(self):
        """Deve gerar ações para campo desconhecido."""
        template = SimpleNamespace(
            field_specs={
                "CODE": SimpleNamespace(),
                "NOTE": SimpleNamespace(),
                "CHAIN": SimpleNamespace()
            }
        )
        cached = _make_cached(template)

        diagnostic = _make_diagnostic("Unknown field 'notes'", 5, 0, 5)

        empty_range = Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0)
        )
        result = compute_code_actions(
            "file:///test.syn",
            empty_range,
            [diagnostic],
            cached
        )

        assert result is not None
        assert len(result) > 0
        # Deve sugerir "NOTE" (similar a "notes")
        titles = [action.title for action in result]
        assert any("NOTE" in title for title in titles)

    def test_required_field_diagnostic(self):
        """Deve gerar ação para campo obrigatório faltando."""
        template = SimpleNamespace(field_specs={"CODE": SimpleNamespace()})
        cached = _make_cached(template)

        diagnostic = _make_diagnostic("Required field 'CODE' missing", 5, 0, 0)

        empty_range = Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0)
        )
        result = compute_code_actions(
            "file:///test.syn",
            empty_range,
            [diagnostic],
            cached
        )

        assert result is not None
        assert len(result) > 0
        assert "Add required field 'CODE'" in result[0].title

    def test_no_template(self):
        """Deve retornar None quando não há template."""
        diagnostic = _make_diagnostic("Unknown field 'notes'", 5, 0, 5)

        empty_range = Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0)
        )
        result = compute_code_actions(
            "file:///test.syn",
            empty_range,
            [diagnostic],
            None
        )

        assert result is None

    def test_multiple_diagnostics(self):
        """Deve processar múltiplos diagnósticos."""
        template = SimpleNamespace(
            field_specs={
                "CODE": SimpleNamespace(),
                "NOTE": SimpleNamespace()
            }
        )
        cached = _make_cached(template)

        diagnostics = [
            _make_diagnostic("Unknown field 'notes'", 5, 0, 5),
            _make_diagnostic("Unknown field 'codes'", 6, 0, 5)
        ]

        empty_range = Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0)
        )
        result = compute_code_actions(
            "file:///test.syn",
            empty_range,
            diagnostics,
            cached
        )

        assert result is not None
        assert len(result) >= 2


class TestSuggestFieldCorrections:
    """Testa sugestões de correção de campos."""

    def test_suggest_similar_field(self):
        """Deve sugerir campo similar."""
        template = SimpleNamespace(
            field_specs={
                "CODE": SimpleNamespace(),
                "NOTE": SimpleNamespace()
            }
        )

        diagnostic = _make_diagnostic("Unknown field 'notes'", 5, 0, 5)

        actions = _suggest_field_corrections("file:///test.syn", diagnostic, template)

        assert len(actions) > 0
        assert any("NOTE" in action.title for action in actions)

    def test_multiple_suggestions(self):
        """Deve retornar múltiplas sugestões."""
        template = SimpleNamespace(
            field_specs={
                "CODE": SimpleNamespace(),
                "CODES": SimpleNamespace(),
                "CODEC": SimpleNamespace(),
                "NOTE": SimpleNamespace()
            }
        )

        diagnostic = _make_diagnostic("Unknown field 'coda'", 5, 0, 4)

        actions = _suggest_field_corrections("file:///test.syn", diagnostic, template)

        # Deve sugerir CODE, CODES, CODEC (similar a "coda")
        assert len(actions) > 0
        assert len(actions) <= 3  # Limita a 3 sugestões

    def test_no_similar_fields(self):
        """Deve retornar lista vazia quando não há campos similares."""
        template = SimpleNamespace(
            field_specs={
                "CODE": SimpleNamespace(),
                "NOTE": SimpleNamespace()
            }
        )

        diagnostic = _make_diagnostic("Unknown field 'xyz123'", 5, 0, 6)

        actions = _suggest_field_corrections("file:///test.syn", diagnostic, template)

        assert len(actions) == 0

    def test_no_field_specs(self):
        """Deve lidar com template sem field_specs."""
        template = SimpleNamespace()

        diagnostic = _make_diagnostic("Unknown field 'notes'", 5, 0, 5)

        actions = _suggest_field_corrections("file:///test.syn", diagnostic, template)

        assert len(actions) == 0


class TestExtractFieldNameFromMessage:
    """Testa extração de nome de campo."""

    def test_single_quotes(self):
        """Deve extrair campo entre aspas simples."""
        assert _extract_field_name_from_message("Unknown field 'notes'") == "notes"

    def test_double_quotes(self):
        """Deve extrair campo entre aspas duplas."""
        assert _extract_field_name_from_message('Unknown field "notes"') == "notes"

    def test_required_field(self):
        """Deve extrair campo de mensagem de campo obrigatório."""
        assert _extract_field_name_from_message("Required field 'CODE' missing") == "CODE"

    def test_portuguese_message(self):
        """Deve extrair campo de mensagem em português."""
        assert _extract_field_name_from_message("Campo desconhecido 'notas'") == "notas"

    def test_no_quotes(self):
        """Deve retornar None quando não há aspas."""
        assert _extract_field_name_from_message("Unknown field without quotes") is None

    def test_empty_message(self):
        """Deve retornar None para mensagem vazia."""
        assert _extract_field_name_from_message("") is None


class TestFindSimilarFields:
    """Testa busca de campos similares."""

    def test_exact_match(self):
        """Deve encontrar match exato."""
        similar = _find_similar_fields("CODE", ["CODE", "NOTE", "CHAIN"])
        assert similar[0] == "CODE"

    def test_one_char_difference(self):
        """Deve encontrar campos com 1 caractere diferente."""
        similar = _find_similar_fields("CODA", ["CODE", "NOTE", "CHAIN"])
        assert "CODE" in similar

    def test_case_insensitive(self):
        """Deve ser case insensitive."""
        similar = _find_similar_fields("code", ["CODE", "NOTE"])
        assert "CODE" in similar

    def test_multiple_similar(self):
        """Deve encontrar múltiplos campos similares."""
        similar = _find_similar_fields("cod", ["CODE", "CODES", "CODEC"])
        assert len(similar) == 3

    def test_no_similar(self):
        """Deve retornar lista vazia quando não há similares."""
        similar = _find_similar_fields("xyz123", ["CODE", "NOTE"], max_distance=2)
        assert len(similar) == 0

    def test_max_distance_limit(self):
        """Deve respeitar max_distance."""
        # "notes" vs "NOTE" = 1 diferença, vs "CODE" = 3 diferenças
        similar = _find_similar_fields("notes", ["CODE", "NOTE", "ABCD"], max_distance=2)
        assert "NOTE" in similar  # 1 diferença
        # CODE tem 3 diferenças, está no limite
        # ABCD tem 4 diferenças, não deve estar
        assert "ABCD" not in similar


class TestLevenshteinDistance:
    """Testa cálculo de distância de edição."""

    def test_identical_strings(self):
        """Distância entre strings idênticas deve ser 0."""
        assert _levenshtein_distance("CODE", "CODE") == 0

    def test_one_substitution(self):
        """Distância de 1 substituição."""
        assert _levenshtein_distance("CODE", "CODA") == 1

    def test_one_insertion(self):
        """Distância de 1 inserção."""
        assert _levenshtein_distance("COD", "CODE") == 1

    def test_one_deletion(self):
        """Distância de 1 deleção."""
        assert _levenshtein_distance("CODE", "COD") == 1

    def test_multiple_operations(self):
        """Distância com múltiplas operações."""
        assert _levenshtein_distance("kitten", "sitting") == 3

    def test_empty_string(self):
        """Distância com string vazia."""
        assert _levenshtein_distance("", "CODE") == 4
        assert _levenshtein_distance("CODE", "") == 4

    def test_case_sensitive(self):
        """Deve ser case sensitive."""
        # Normalmente usamos lowercase na comparação, mas a função em si é case sensitive
        assert _levenshtein_distance("code", "CODE") > 0

    def test_symmetric(self):
        """Distância deve ser simétrica."""
        d1 = _levenshtein_distance("abc", "xyz")
        d2 = _levenshtein_distance("xyz", "abc")
        assert d1 == d2
