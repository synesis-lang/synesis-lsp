"""
inlay_hints.py - Inlay hints para bibrefs, campos ORDERED e ENUMERATED

Propósito:
    Exibe informação inline após elementos cujo significado permanece oculto
    no arquivo de anotação:

    @bibref       → "· Trecho do título" (tooltip com título completo)
    campo ORDERED → "← Label" com tooltip "Label — description" (o valor é
                    um índice numérico; o label revela seu significado modal)
    campo ENUMERATED → "← description" truncada (o valor já é o label, então
                       a description acrescenta o significado)

Notas de implementação:
    - Usa regex para detectar padrão "campo: valor" por linha
    - Busca field_specs no template via cached_result.result.template
    - Suporta range_ para limitar hints à área visível
"""

from __future__ import annotations

import re
from typing import Optional

from lsprotocol.types import (
    InlayHint,
    InlayHintKind,
    MarkupContent,
    MarkupKind,
    Position,
)

BIBREF_PATTERN = re.compile(r"@([\w._-]+)")
_FIELD_LINE = re.compile(r"^(\s*)(\w+)\s*:\s*(.+?)\s*$")

# Comprimento máximo da description no label de hints ENUMERATED
_MAX_DESC_LEN = 55


def compute_inlay_hints(
    source: str, cached_result, range_=None
) -> list[InlayHint]:
    """
    Computa inlay hints para @bibrefs e campos ORDERED/ENUMERATED.

    Args:
        source: Texto-fonte do documento
        cached_result: CachedCompilation do workspace_cache (pode ser None)
        range_: Range LSP opcional para limitar hints à área visível

    Returns:
        Lista de InlayHint posicionados após o valor em cada linha relevante.
        @bibrefs sem título na bibliography não geram hint.
    """
    if not cached_result:
        return []

    result = cached_result.result
    bib = getattr(result, "bibliography", None)
    template = getattr(result, "template", None)
    field_specs = getattr(template, "field_specs", None) if template else None

    hints = []
    for line_num, line in enumerate(source.splitlines()):
        if range_ and (line_num < range_.start.line or line_num > range_.end.line):
            continue

        # 1. @bibref → trecho do título
        if bib:
            for match in BIBREF_PATTERN.finditer(line):
                bibref = match.group(1)
                entry = bib.get(bibref) or bib.get(bibref.lower())
                if entry:
                    title = entry.get("title", "")
                    if title:
                        hints.append(
                            InlayHint(
                                position=Position(line=line_num, character=match.end()),
                                label=f" · {_truncate_title(title)}",
                                kind=InlayHintKind.Type,
                                tooltip=MarkupContent(kind=MarkupKind.Markdown, value=title),
                                padding_left=True,
                            )
                        )

        # 2. Campos ORDERED / ENUMERATED
        if field_specs:
            hint = _hint_for_value_field(line, line_num, field_specs)
            if hint:
                hints.append(hint)

    return hints


_MAX_TITLE_LEN = 50


def _truncate_title(title: str) -> str:
    """Trunca título em _MAX_TITLE_LEN chars, cortando na palavra mais próxima."""
    if len(title) <= _MAX_TITLE_LEN:
        return title
    return title[:_MAX_TITLE_LEN].rsplit(" ", 1)[0] + "…"


def _hint_for_value_field(
    line: str, line_num: int, field_specs
) -> Optional[InlayHint]:
    """
    Retorna InlayHint para campos ORDERED ou ENUMERATED se o valor tiver
    uma entrada correspondente no template VALUES, ou None caso contrário.
    """
    m = _FIELD_LINE.match(line)
    if not m:
        return None

    field_name = m.group(2)
    raw_value = m.group(3).strip()

    # Ignora linhas de bloco (SOURCE, ITEM, END...) e comentários
    if not raw_value or raw_value.startswith("#"):
        return None

    spec = field_specs.get(field_name) or _find_case_insensitive(field_specs, field_name)
    if not spec:
        return None

    field_type = getattr(getattr(spec, "type", None), "name", None)
    values = getattr(spec, "values", None)
    if not values or field_type not in ("ORDERED", "ENUMERATED"):
        return None

    # Posição após o final do valor na linha
    value_end = line.rindex(raw_value) + len(raw_value)

    if field_type == "ORDERED":
        return _hint_ordered(line_num, value_end, raw_value, values)
    else:
        return _hint_enumerated(line_num, value_end, raw_value, values)


def _hint_ordered(
    line_num: int, value_end: int, raw_value: str, values
) -> Optional[InlayHint]:
    """
    ORDERED: valor é índice numérico. Hint mostra o label.
    Tooltip mostra "Label — description".
    """
    try:
        index = int(raw_value)
    except ValueError:
        return None

    entry = next((v for v in values if v.index == index), None)
    if not entry:
        return None

    tooltip = MarkupContent(
        kind=MarkupKind.Markdown,
        value=f"**{entry.label}** — {entry.description}",
    )
    return InlayHint(
        position=Position(line=line_num, character=value_end),
        label=f" ← {entry.label}",
        kind=InlayHintKind.Parameter,
        tooltip=tooltip,
        padding_left=True,
    )


def _hint_enumerated(
    line_num: int, value_end: int, raw_value: str, values
) -> Optional[InlayHint]:
    """
    ENUMERATED: valor já é o label. Hint mostra a description (truncada).
    Tooltip mostra a description completa.
    """
    entry = next(
        (v for v in values if v.label.upper() == raw_value.upper()), None
    )
    if not entry:
        return None

    desc = entry.description
    short = desc if len(desc) <= _MAX_DESC_LEN else desc[:_MAX_DESC_LEN].rsplit(" ", 1)[0] + "…"

    tooltip = MarkupContent(kind=MarkupKind.Markdown, value=desc)
    return InlayHint(
        position=Position(line=line_num, character=value_end),
        label=f" ← {short}",
        kind=InlayHintKind.Parameter,
        tooltip=tooltip,
        padding_left=True,
    )


def _find_case_insensitive(field_specs, name: str):
    """Busca field_spec ignorando case — fallback para templates com nomes em maiúsculas."""
    name_lower = name.lower()
    for key, spec in field_specs.items():
        if key.lower() == name_lower:
            return spec
    return None
