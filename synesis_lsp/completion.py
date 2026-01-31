"""
completion.py - Autocomplete para bibrefs, códigos e campos

Propósito:
    Fornece sugestões de completamento contextual:
    - Após @: bibrefs da bibliography
    - Códigos da ontologia (ontology_index)
    - Campos do template (field_specs)

Notas de implementação:
    - Depende do workspace_cache para dados do projeto compilado
    - trigger_char="@" ativa sugestões de bibrefs
    - Sem cache, retorna lista vazia
    - CompletionItemKind: Reference (bibrefs), EnumMember (códigos), Property (campos)
"""

from __future__ import annotations

import logging
from typing import Optional

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    Position,
)

logger = logging.getLogger(__name__)


def compute_completions(
    source: str,
    position: Position,
    cached_result,
    trigger_char: Optional[str] = None,
) -> CompletionList:
    """
    Computa lista de completamento.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor (0-based)
        cached_result: CachedCompilation do workspace_cache
        trigger_char: Caractere que disparou o completion (ex: "@")

    Returns:
        CompletionList com sugestões contextuais
    """
    if not cached_result:
        return CompletionList(is_incomplete=False, items=[])

    result = cached_result.result
    items: list[CompletionItem] = []

    lines = source.splitlines()
    line = lines[position.line] if position.line < len(lines) else ""

    # Após @: sugerir bibrefs
    if trigger_char == "@" or _is_after_at(line, position.character):
        bib = getattr(result, "bibliography", None) or {}
        for bibref, entry in bib.items():
            author = entry.get("author", "?")
            year = entry.get("year", "?")
            items.append(
                CompletionItem(
                    label=f"@{bibref}",
                    kind=CompletionItemKind.Reference,
                    detail=f"{author} ({year})",
                    insert_text=bibref,
                )
            )

    # Sugerir códigos da ontologia
    lp = getattr(result, "linked_project", None)
    if lp:
        ontology_index = getattr(lp, "ontology_index", {}) or {}
        code_usage = getattr(lp, "code_usage", {}) or {}
        for concept in ontology_index:
            usage_count = len(code_usage.get(concept, []))
            items.append(
                CompletionItem(
                    label=concept,
                    kind=CompletionItemKind.EnumMember,
                    detail=f"Ontologia ({usage_count} usos)",
                )
            )

    # Sugerir campos do template
    template = getattr(result, "template", None)
    if template:
        field_specs = getattr(template, "field_specs", {}) or {}
        for name, spec in field_specs.items():
            type_name = getattr(spec.type, "name", str(spec.type))
            scope_name = getattr(spec.scope, "name", str(spec.scope))
            description = getattr(spec, "description", "") or ""
            items.append(
                CompletionItem(
                    label=f"{name}:",
                    kind=CompletionItemKind.Property,
                    detail=f"{type_name} ({scope_name})",
                    documentation=description,
                )
            )

    return CompletionList(is_incomplete=False, items=items)


def _is_after_at(line: str, character: int) -> bool:
    """Verifica se o cursor está logo após um '@'."""
    if character <= 0:
        return False
    # Busca o @ mais próximo à esquerda do cursor
    prefix = line[:character]
    # Verifica se o último caractere não-alfanumérico antes do cursor é @
    for i in range(len(prefix) - 1, -1, -1):
        ch = prefix[i]
        if ch == "@":
            return True
        if not ch.isalnum() and ch != "_":
            return False
    return False
