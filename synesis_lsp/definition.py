"""
definition.py - Go-to-definition para @bibref e códigos

Propósito:
    Resolve a definição de um símbolo sob o cursor:
    - @bibref → localização do SourceNode no arquivo .syn
    - código  → localização do OntologyNode no arquivo .syno

Notas de implementação:
    - Depende do workspace_cache (Step 1) para linked_project
    - SourceNode.location.file e OntologyNode.location.file são paths
      relativos; combinados com workspace_root para URI completo
    - Reutiliza _get_word_at_position do hover.py
    - Posições do compilador são 1-based; convertidas para 0-based (LSP)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lsprotocol.types import Location, Position, Range

from synesis_lsp.hover import _get_word_at_position

logger = logging.getLogger(__name__)


def compute_definition(
    source: str, position: Position, cached_result
) -> Optional[Location]:
    """
    Resolve definição: @bibref → SOURCE, código → ONTOLOGY.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor (0-based)
        cached_result: CachedCompilation do workspace_cache

    Returns:
        Location apontando para a definição, ou None
    """
    lines = source.splitlines()
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    word = _get_word_at_position(line, position.character)
    if not word or not cached_result:
        return None

    lp = getattr(cached_result.result, "linked_project", None)
    if not lp:
        return None

    workspace_root = getattr(cached_result, "workspace_root", None)
    if not workspace_root:
        return None

    # @bibref → SourceNode.location
    if word.startswith("@"):
        bibref = word[1:]
        sources = getattr(lp, "sources", {}) or {}
        src = sources.get(bibref)
        if src and hasattr(src, "location"):
            return _location_to_lsp(src.location, workspace_root)

    # código → OntologyNode.location
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    if word in ontology_index:
        onto = ontology_index[word]
        if hasattr(onto, "location"):
            return _location_to_lsp(onto.location, workspace_root)

    return None


def _location_to_lsp(location, workspace_root: Path) -> Optional[Location]:
    """Converte SourceLocation do compilador para LSP Location."""
    file_path = getattr(location, "file", None)
    if not file_path:
        return None

    uri = _to_uri(workspace_root, file_path)
    line = max(0, getattr(location, "line", 1) - 1)  # 1-based → 0-based
    col = max(0, getattr(location, "column", 1) - 1)

    return Location(
        uri=uri,
        range=Range(
            start=Position(line=line, character=col),
            end=Position(line=line, character=col),
        ),
    )


def _to_uri(workspace_root: Path, file_path) -> str:
    """Combina workspace_root com path relativo do nó para URI."""
    full = workspace_root / str(file_path)
    return full.as_uri()
