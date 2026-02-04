"""
inlay_hints.py - Inlay hints para bibrefs (Autor, Ano)

Propósito:
    Exibe informação inline (Autor, Ano) após cada @bibref no editor,
    usando dados da bibliography do CompilationResult em cache.

Notas de implementação:
    - Usa regex para encontrar @bibref no texto-fonte
    - Busca na bibliography do cached_result
    - Retorna InlayHint com label "(Autor, Ano)" após cada referência
    - Suporta range_ para limitar hints à área visível
"""

from __future__ import annotations

import re
from typing import Optional

from lsprotocol.types import InlayHint, InlayHintKind, Position

BIBREF_PATTERN = re.compile(r"@([\w._-]+)")


def compute_inlay_hints(
    source: str, cached_result, range_=None
) -> list[InlayHint]:
    """
    Computa inlay hints para @bibrefs no texto-fonte.

    Args:
        source: Texto-fonte do documento
        cached_result: CachedCompilation do workspace_cache (pode ser None)
        range_: Range LSP opcional para limitar hints à área visível

    Returns:
        Lista de InlayHint com "(Autor, Ano)" após cada @bibref encontrado
    """
    if not cached_result:
        return []

    bib = getattr(cached_result.result, "bibliography", None)
    if not bib:
        return []

    hints = []
    for line_num, line in enumerate(source.splitlines()):
        if range_ and (line_num < range_.start.line or line_num > range_.end.line):
            continue

        for match in BIBREF_PATTERN.finditer(line):
            bibref = match.group(1)
            entry = bib.get(bibref) or bib.get(bibref.lower())
            if entry:
                author = entry.get("author", "?")
                year = entry.get("year", "?")
                short = author.split(",")[0].strip() if author else "?"
                hints.append(
                    InlayHint(
                        position=Position(line=line_num, character=match.end()),
                        label=f" ({short}, {year})",
                        kind=InlayHintKind.Type,
                        padding_left=True,
                    )
                )

    return hints
