"""
code_actions.py - Code Actions (Quick Fixes) para Synesis

Propósito:
    Implementa textDocument/codeAction para fornecer quick fixes
    para erros comuns (ex: campos desconhecidos, typos).

LSP Feature:
    textDocument/codeAction → Lista de CodeAction com sugestões de correção
"""

from __future__ import annotations

import logging
from typing import Optional

from lsprotocol.types import (
    CodeAction,
    CodeActionKind,
    Diagnostic,
    Range,
    TextEdit,
    WorkspaceEdit,
)

logger = logging.getLogger(__name__)


def compute_code_actions(
    uri: str,
    range_: Range,
    diagnostics: list[Diagnostic],
    cached_result
) -> Optional[list[CodeAction]]:
    """
    Gera code actions (quick fixes) para diagnósticos.

    Args:
        uri: URI do documento
        range_: Range selecionado ou posição do cursor
        diagnostics: Lista de diagnósticos no range
        cached_result: CachedCompilation com template

    Returns:
        Lista de CodeAction ou None
    """
    if not diagnostics:
        return None

    actions = []

    # Extrair template do cache
    template = None
    if cached_result:
        result = getattr(cached_result, "result", None)
        if result:
            template = getattr(result, "template", None)

    # Processar cada diagnóstico
    for diagnostic in diagnostics:
        # Quick fix para campo desconhecido
        if "unknown field" in diagnostic.message.lower() or "campo desconhecido" in diagnostic.message.lower():
            field_actions = _suggest_field_corrections(uri, diagnostic, template)
            if field_actions:
                actions.extend(field_actions)

        # Quick fix para campo obrigatório faltando
        elif "required field" in diagnostic.message.lower() or "campo obrigatório" in diagnostic.message.lower():
            required_actions = _suggest_required_field(uri, diagnostic, template)
            if required_actions:
                actions.extend(required_actions)

        # Quick fix para valor inválido
        elif "invalid value" in diagnostic.message.lower() or "valor inválido" in diagnostic.message.lower():
            value_actions = _suggest_value_corrections(uri, diagnostic, template)
            if value_actions:
                actions.extend(value_actions)

    return actions if actions else None


def _suggest_field_corrections(
    uri: str,
    diagnostic: Diagnostic,
    template
) -> list[CodeAction]:
    """
    Sugere correções para campos desconhecidos.

    Args:
        uri: URI do documento
        diagnostic: Diagnóstico de campo desconhecido
        template: Template para extrair campos válidos

    Returns:
        Lista de CodeAction com sugestões
    """
    actions = []

    # Extrair nome do campo desconhecido da mensagem
    unknown_field = _extract_field_name_from_message(diagnostic.message)
    if not unknown_field:
        return actions

    # Obter campos válidos do template
    if not template:
        return actions

    field_specs = getattr(template, "field_specs", {}) or {}
    valid_fields = list(field_specs.keys())

    if not valid_fields:
        return actions

    # Encontrar campos similares usando distância de edição
    suggestions = _find_similar_fields(unknown_field, valid_fields)

    # Criar CodeAction para cada sugestão
    for suggestion in suggestions[:3]:  # Limitar a 3 sugestões
        edit = TextEdit(
            range=diagnostic.range,
            new_text=suggestion
        )

        workspace_edit = WorkspaceEdit(changes={uri: [edit]})

        action = CodeAction(
            title=f"Change to '{suggestion}'",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=workspace_edit
        )

        actions.append(action)

    return actions


def _suggest_required_field(
    uri: str,
    diagnostic: Diagnostic,
    template
) -> list[CodeAction]:
    """
    Sugere inserção de campo obrigatório faltando.

    Args:
        uri: URI do documento
        diagnostic: Diagnóstico de campo obrigatório faltando
        template: Template para extrair informações do campo

    Returns:
        Lista de CodeAction com sugestão de inserção
    """
    actions = []

    # Extrair nome do campo obrigatório
    field_name = _extract_field_name_from_message(diagnostic.message)
    if not field_name:
        return actions

    # Criar texto de inserção
    insert_text = f"{field_name}: \n"

    # Range de inserção: logo após a posição do diagnóstico
    insert_range = Range(
        start=diagnostic.range.end,
        end=diagnostic.range.end
    )

    edit = TextEdit(range=insert_range, new_text=insert_text)
    workspace_edit = WorkspaceEdit(changes={uri: [edit]})

    action = CodeAction(
        title=f"Add required field '{field_name}'",
        kind=CodeActionKind.QuickFix,
        diagnostics=[diagnostic],
        edit=workspace_edit
    )

    actions.append(action)

    return actions


def _suggest_value_corrections(
    uri: str,
    diagnostic: Diagnostic,
    template
) -> list[CodeAction]:
    """
    Sugere correções para valores inválidos.

    Args:
        uri: URI do documento
        diagnostic: Diagnóstico de valor inválido
        template: Template para extrair valores válidos

    Returns:
        Lista de CodeAction com sugestões
    """
    # TODO: Implementar sugestões de valores válidos baseado em constraints do template
    return []


def _extract_field_name_from_message(message: str) -> Optional[str]:
    """
    Extrai nome do campo de mensagem de diagnóstico.

    Exemplos:
        "Unknown field 'notes'" → "notes"
        "Campo desconhecido 'notes'" → "notes"
        "Required field 'CODE' missing" → "CODE"
    """
    import re

    # Padrão: palavra entre aspas simples ou duplas
    patterns = [
        r"'([^']+)'",  # Aspas simples
        r'"([^"]+)"',  # Aspas duplas
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)

    return None


def _find_similar_fields(target: str, candidates: list[str], max_distance: int = 3) -> list[str]:
    """
    Encontra campos similares usando distância de Levenshtein.

    Args:
        target: Campo alvo (com typo)
        candidates: Lista de campos válidos
        max_distance: Distância máxima de edição

    Returns:
        Lista de campos similares, ordenados por similaridade
    """
    similar = []

    for candidate in candidates:
        distance = _levenshtein_distance(target.lower(), candidate.lower())
        if distance <= max_distance:
            similar.append((candidate, distance))

    # Ordenar por distância (menor primeiro)
    similar.sort(key=lambda x: x[1])

    return [field for field, _ in similar]


def _levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calcula distância de Levenshtein entre duas strings.

    Args:
        s1: Primeira string
        s2: Segunda string

    Returns:
        Distância de edição (número de operações)
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Custo de inserção, deleção, substituição
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
