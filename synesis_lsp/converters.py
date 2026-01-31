"""
converters.py - Conversão entre tipos Synesis e LSP

Propósito:
    Converter objetos do compilador Synesis para tipos do protocolo LSP.
    Garante mapeamento correto de coordenadas (1-based → 0-based).
    Integra error_handler do compilador para mensagens pedagógicas enriquecidas.

Componentes principais:
    - convert_severity: ErrorSeverity → DiagnosticSeverity
    - convert_location: SourceLocation → Range
    - build_diagnostic: ValidationError → Diagnostic
    - enrich_error_message: Exception → mensagem pedagógica enriquecida

Dependências críticas:
    - lsprotocol.types: Tipos do protocolo LSP
    - synesis.ast: Tipos do compilador
    - synesis.error_handler: Formatação pedagógica de erros (opcional)

Exemplo de uso:
    from synesis.ast.results import ValidationResult
    from synesis_lsp.converters import build_diagnostics, enrich_error_message

    diagnostics = build_diagnostics(validation_result)

Notas de implementação:
    - Coordenadas Synesis são 1-based (linha, coluna)
    - Coordenadas LSP são 0-based (line, character)
    - Ranges sempre têm comprimento mínimo de 1
    - error_handler enriquece exceções Lark com contexto e sugestões

Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP
"""

from __future__ import annotations

import logging
from typing import List, Optional

from lsprotocol.types import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

logger = logging.getLogger(__name__)

# Importa do compilador (deve estar instalado)
try:
    from synesis.ast.nodes import SourceLocation
    from synesis.ast.results import ErrorSeverity, ValidationError, ValidationResult
except ImportError as e:
    raise ImportError(
        "Pacote 'synesis' não encontrado. "
        "Instale o compilador primeiro: cd ../Compiler && pip install -e ."
    ) from e

# Importa error_handler (opcional — fallback se não disponível)
try:
    from synesis.error_handler import SynesisErrorHandler, create_pedagogical_error

    _error_handler = SynesisErrorHandler()
    _HAS_ERROR_HANDLER = True
except ImportError:
    _HAS_ERROR_HANDLER = False
    _error_handler = None


def convert_severity(synesis_severity: ErrorSeverity) -> DiagnosticSeverity:
    """
    Mapeia ErrorSeverity do Synesis para DiagnosticSeverity do LSP.

    Mapeamento:
        ERROR   → DiagnosticSeverity.Error (1)
        WARNING → DiagnosticSeverity.Warning (2)
        INFO    → DiagnosticSeverity.Information (3)
    """
    mapping = {
        ErrorSeverity.ERROR: DiagnosticSeverity.Error,
        ErrorSeverity.WARNING: DiagnosticSeverity.Warning,
        ErrorSeverity.INFO: DiagnosticSeverity.Information,
    }
    return mapping.get(synesis_severity, DiagnosticSeverity.Error)


def convert_location(location: SourceLocation, length: int = 1) -> Range:
    """
    Converte SourceLocation (1-based) para Range LSP (0-based).

    Args:
        location: Localização Synesis (line 1-based, column 1-based)
        length: Comprimento do erro em caracteres (padrão: 1)

    Returns:
        Range LSP com Position 0-based

    Notas:
        - Synesis: line=1 significa primeira linha
        - LSP: line=0 significa primeira linha
        - Column em Synesis também é 1-based
    """
    # Converte para 0-based
    start_line = max(0, location.line - 1)
    start_char = max(0, location.column - 1)

    # End position: mesma linha, avança 'length' caracteres
    end_line = start_line
    end_char = start_char + length

    return Range(
        start=Position(line=start_line, character=start_char),
        end=Position(line=end_line, character=end_char),
    )


def build_diagnostic(error: ValidationError) -> Diagnostic:
    """
    Converte um ValidationError do Synesis em Diagnostic do LSP.

    Args:
        error: Erro de validação do compilador

    Returns:
        Diagnostic LSP com mensagem, severidade e range

    Notas:
        - Mensagem vem de error.to_diagnostic() (já pedagógica)
        - Se error tem expected tokens, adiciona sugestões humanizadas
        - Severidade convertida via convert_severity()
        - Range assume comprimento 1 (destaca início do erro)
    """
    message = error.to_diagnostic()

    # Enriquecer mensagem com tokens esperados humanizados
    if _HAS_ERROR_HANDLER and hasattr(error, "expected") and error.expected:
        humanized = _humanize_expected(error.expected)
        if humanized:
            message = f"{message}\n\nEsperado: {humanized}"

    return Diagnostic(
        range=convert_location(error.location, length=1),
        severity=convert_severity(error.severity),
        source="synesis",
        message=message,
    )


def build_diagnostics(result: ValidationResult) -> List[Diagnostic]:
    """
    Converte todos os erros/warnings/info de um ValidationResult.

    Args:
        result: Resultado agregado da validação

    Returns:
        Lista de Diagnostic LSP (erros + warnings + info)

    Nota:
        - Ordem: erros primeiro, depois warnings, depois info
        - Cada tipo mantém sua severidade original
    """
    diagnostics: List[Diagnostic] = []

    # Processa todos os tipos de diagnósticos
    all_errors = result.errors + result.warnings + result.info

    for error in all_errors:
        try:
            diagnostic = build_diagnostic(error)
            diagnostics.append(diagnostic)
        except Exception as e:
            # Fallback: cria diagnostic genérico se conversão falhar
            # Evita que um erro mal-formado derrube o LSP
            fallback = Diagnostic(
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=0, character=1),
                ),
                severity=DiagnosticSeverity.Error,
                source="synesis-lsp",
                message=f"Erro ao processar diagnóstico: {str(e)}",
            )
            diagnostics.append(fallback)

    return diagnostics


# ---------------------------------------------------------------------------
# Integração com error_handler (Step 9)
# ---------------------------------------------------------------------------

# Mapeamento de nomes de tokens Lark para nomes legíveis
_TOKEN_NAMES = {
    "COLON": "':'",
    "COMMA": "','",
    "NEWLINE": "nova linha",
    "KW_SOURCE": "SOURCE",
    "KW_ITEM": "ITEM",
    "KW_END": "END",
    "KW_ONTOLOGY": "ONTOLOGY",
    "KW_PROJECT": "PROJECT",
    "KW_TEMPLATE": "TEMPLATE",
    "KW_INCLUDE": "INCLUDE",
    "KW_REQUIRED": "REQUIRED",
    "KW_OPTIONAL": "OPTIONAL",
    "KW_FORBIDDEN": "FORBIDDEN",
    "IDENTIFIER": "identificador",
    "BIBREF": "@referência",
    "ARROW": "'->'",
    "QUOTED_STRING": "texto entre aspas",
}


def _humanize_expected(expected: list) -> Optional[str]:
    """
    Converte lista de tokens esperados em texto legível.

    Args:
        expected: Lista de nomes de tokens Lark (ex: ['COLON', 'COMMA'])

    Returns:
        String humanizada ou None se lista vazia
    """
    if not expected:
        return None

    humanized = []
    seen = set()
    for token in expected:
        name = _TOKEN_NAMES.get(token, token)
        if name not in seen:
            humanized.append(name)
            seen.add(name)

    if not humanized:
        return None

    if len(humanized) == 1:
        return humanized[0]
    return ", ".join(humanized[:-1]) + f" ou {humanized[-1]}"


def enrich_error_message(
    exc: Exception,
    source: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Enriquece mensagem de exceção usando error_handler do compilador.

    Tenta usar create_pedagogical_error do compilador para produzir
    mensagens com contexto e sugestões. Faz fallback para str(exc).

    Args:
        exc: Exceção capturada
        source: Texto-fonte do documento (necessário para enriquecimento)
        filename: Nome do arquivo (para contexto na mensagem)

    Returns:
        Mensagem de erro enriquecida (string)
    """
    # Tenta enriquecer via __cause__ (exceção Lark encapsulada)
    if _HAS_ERROR_HANDLER and source:
        cause = getattr(exc, "__cause__", None)
        if cause:
            try:
                enriched = create_pedagogical_error(
                    cause, source, filename or "<desconhecido>"
                )
                if enriched:
                    return enriched
            except Exception:
                logger.debug("error_handler falhou ao enriquecer __cause__", exc_info=True)

        # Tenta enriquecer a exceção diretamente
        try:
            enriched = create_pedagogical_error(
                exc, source, filename or "<desconhecido>"
            )
            if enriched:
                return enriched
        except Exception:
            logger.debug("error_handler falhou ao enriquecer exceção", exc_info=True)

    # Fallback: usa .message se disponível, senão str()
    return str(getattr(exc, "message", str(exc)))
