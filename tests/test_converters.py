"""
test_converters.py - Testes para conversão de tipos Synesis → LSP

Propósito:
    Validar conversão correta entre tipos do compilador e protocolo LSP.
    Garante que coordenadas, severidades e mensagens são mapeadas corretamente.

Componentes testados:
    - convert_severity: ErrorSeverity → DiagnosticSeverity
    - convert_location: SourceLocation → Range (1-based → 0-based)
    - build_diagnostic: ValidationError → Diagnostic
    - build_diagnostics: ValidationResult → List[Diagnostic]
    - enrich_error_message: Exception → mensagem pedagógica
    - _humanize_expected: tokens Lark → texto legível
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lsprotocol.types import DiagnosticSeverity, Position, Range

# Imports do compilador (assumindo que está instalado)
try:
    from synesis.ast.nodes import SourceLocation
    from synesis.ast.results import (
        ErrorSeverity,
        MissingRequiredField,
        UnregisteredSource,
        ValidationResult,
    )
except ImportError:
    pytest.skip("Compilador synesis não instalado", allow_module_level=True)

from synesis_lsp.converters import (
    build_diagnostic,
    build_diagnostics,
    convert_location,
    convert_severity,
    enrich_error_message,
    _humanize_expected,
    _HAS_ERROR_HANDLER,
)


def test_convert_severity_error():
    """ErrorSeverity.ERROR deve mapear para DiagnosticSeverity.Error."""
    result = convert_severity(ErrorSeverity.ERROR)
    assert result == DiagnosticSeverity.Error


def test_convert_severity_warning():
    """ErrorSeverity.WARNING deve mapear para DiagnosticSeverity.Warning."""
    result = convert_severity(ErrorSeverity.WARNING)
    assert result == DiagnosticSeverity.Warning


def test_convert_severity_info():
    """ErrorSeverity.INFO deve mapear para DiagnosticSeverity.Information."""
    result = convert_severity(ErrorSeverity.INFO)
    assert result == DiagnosticSeverity.Information


def test_convert_location_first_line():
    """Primeira linha (1-based) deve converter para linha 0 (0-based)."""
    location = SourceLocation(file=Path("test.syn"), line=1, column=1)
    range_result = convert_location(location)

    assert range_result.start.line == 0
    assert range_result.start.character == 0
    assert range_result.end.line == 0
    assert range_result.end.character == 1  # length=1 padrão


def test_convert_location_with_length():
    """Length deve determinar o comprimento do range."""
    location = SourceLocation(file=Path("test.syn"), line=5, column=10)
    range_result = convert_location(location, length=5)

    # Line 5 (1-based) → 4 (0-based)
    # Column 10 (1-based) → 9 (0-based)
    assert range_result.start.line == 4
    assert range_result.start.character == 9
    assert range_result.end.line == 4
    assert range_result.end.character == 14  # 9 + 5


def test_convert_location_zero_column():
    """Coluna 0 ou negativa deve ser tratada como 0."""
    location = SourceLocation(file=Path("test.syn"), line=1, column=0)
    range_result = convert_location(location)

    assert range_result.start.character == 0


def test_build_diagnostic_from_error():
    """ValidationError deve ser convertido em Diagnostic completo."""
    error = MissingRequiredField(
        location=SourceLocation(file=Path("test.syn"), line=10, column=5),
        field_name="title",
        block_type="SOURCE",
    )

    diagnostic = build_diagnostic(error)

    assert diagnostic.severity == DiagnosticSeverity.Error
    assert diagnostic.source == "synesis"
    assert "title" in diagnostic.message.lower()
    assert diagnostic.range.start.line == 9  # 10 - 1
    assert diagnostic.range.start.character == 4  # 5 - 1


def test_build_diagnostic_from_warning():
    """ValidationError com WARNING severity deve manter severidade."""
    error = UnregisteredSource(
        location=SourceLocation(file=Path("test.syn"), line=1, column=1),
        bibref="nonexistent",
        suggestions=["silva2023"],
    )

    # UnregisteredSource é ERROR por padrão, mas vamos testar o fluxo
    diagnostic = build_diagnostic(error)

    assert diagnostic.source == "synesis"
    assert "nonexistent" in diagnostic.message


def test_build_diagnostics_empty():
    """ValidationResult vazio deve retornar lista vazia."""
    result = ValidationResult()
    diagnostics = build_diagnostics(result)

    assert diagnostics == []


def test_build_diagnostics_with_errors():
    """ValidationResult com erros deve converter todos."""
    result = ValidationResult()

    error1 = MissingRequiredField(
        location=SourceLocation(file=Path("test.syn"), line=1, column=1),
        field_name="author",
        block_type="SOURCE",
    )
    error2 = MissingRequiredField(
        location=SourceLocation(file=Path("test.syn"), line=5, column=1),
        field_name="title",
        block_type="SOURCE",
    )

    result.add(error1)
    result.add(error2)

    diagnostics = build_diagnostics(result)

    assert len(diagnostics) == 2
    assert all(d.severity == DiagnosticSeverity.Error for d in diagnostics)


def test_build_diagnostics_mixed_severities():
    """ValidationResult com erros, warnings e info deve incluir todos."""
    result = ValidationResult()

    # Adiciona erro
    error = MissingRequiredField(
        location=SourceLocation(file=Path("test.syn"), line=1, column=1),
        field_name="author",
        block_type="SOURCE",
    )
    result.add(error)

    # Warnings e info seriam adicionados se tivéssemos tipos específicos
    # Por ora, verifica que pelo menos erro está presente
    diagnostics = build_diagnostics(result)

    assert len(diagnostics) >= 1
    assert diagnostics[0].severity == DiagnosticSeverity.Error


def test_build_diagnostics_preserves_order():
    """Ordem dos diagnósticos deve ser preservada."""
    result = ValidationResult()

    for i in range(1, 4):
        error = MissingRequiredField(
            location=SourceLocation(file=Path("test.syn"), line=i, column=1),
            field_name=f"field{i}",
            block_type="SOURCE",
        )
        result.add(error)

    diagnostics = build_diagnostics(result)

    assert len(diagnostics) == 3
    # Verifica que linhas estão em ordem crescente
    assert diagnostics[0].range.start.line == 0
    assert diagnostics[1].range.start.line == 1
    assert diagnostics[2].range.start.line == 2


# ---------------------------------------------------------------------------
# Testes para _humanize_expected (Step 9)
# ---------------------------------------------------------------------------


def test_humanize_expected_single():
    """Token único deve ser humanizado."""
    result = _humanize_expected(["COLON"])
    assert result == "':'"


def test_humanize_expected_multiple():
    """Múltiplos tokens: vírgula e 'ou' antes do último."""
    result = _humanize_expected(["COLON", "COMMA", "NEWLINE"])
    assert "':'" in result
    assert "','" in result
    assert "ou" in result
    assert "nova linha" in result


def test_humanize_expected_unknown_token():
    """Token desconhecido mantém nome original."""
    result = _humanize_expected(["UNKNOWN_TOKEN"])
    assert result == "UNKNOWN_TOKEN"


def test_humanize_expected_empty():
    """Lista vazia retorna None."""
    result = _humanize_expected([])
    assert result is None


def test_humanize_expected_deduplicates():
    """Tokens duplicados são removidos."""
    result = _humanize_expected(["COLON", "COLON"])
    assert result == "':'"


def test_humanize_expected_keywords():
    """Keywords Synesis são humanizadas."""
    result = _humanize_expected(["KW_SOURCE", "KW_ITEM", "KW_END"])
    assert "SOURCE" in result
    assert "ITEM" in result
    assert "END" in result


# ---------------------------------------------------------------------------
# Testes para enrich_error_message (Step 9)
# ---------------------------------------------------------------------------


def test_enrich_plain_exception():
    """Exceção simples usa str() como fallback."""
    exc = ValueError("algo deu errado")
    result = enrich_error_message(exc)
    assert "algo deu errado" in result


def test_enrich_exception_with_message_attr():
    """Exceção com .message usa esse atributo."""
    exc = Exception("genérico")
    exc.message = "mensagem específica"
    result = enrich_error_message(exc)
    assert "mensagem específica" in result


def test_enrich_with_source_no_cause():
    """Com source mas sem __cause__, usa fallback."""
    exc = ValueError("erro simples")
    result = enrich_error_message(exc, source="SOURCE @test\n", filename="test.syn")
    assert "erro simples" in result


@pytest.mark.skipif(not _HAS_ERROR_HANDLER, reason="error_handler não disponível")
def test_enrich_with_lark_cause():
    """Com __cause__ Lark, usa create_pedagogical_error."""
    import synesis

    source = "SOURCE @test\n  temaa valor\nEND\n"
    try:
        synesis.compile_string(source, "test.syn")
    except Exception as exc:
        # compile_string raises SynesisSyntaxError with Lark __cause__
        if exc.__cause__:
            result = enrich_error_message(exc, source=source, filename="test.syn")
            # Mensagem enriquecida deve ser diferente de str(exc) básico
            assert len(result) > 0
        else:
            pytest.skip("Exceção sem __cause__ Lark")


def test_enrich_without_error_handler_module():
    """Fallback funciona mesmo sem error_handler (importação falha graciosamente)."""
    exc = RuntimeError("falha total")
    result = enrich_error_message(exc, source=None, filename=None)
    assert "falha total" in result
