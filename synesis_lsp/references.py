"""
references.py - Find All References para símbolos Synesis

Propósito:
    Implementa textDocument/references para encontrar todas as
    referências a codes e bibrefs no workspace.

LSP Feature:
    textDocument/references → Lista de Location com todas as referências
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lsprotocol.types import Location, Position, Range

logger = logging.getLogger(__name__)


def compute_references(
    cached_result,
    word: str,
    workspace_root: Optional[Path],
    include_declaration: bool = True
) -> Optional[list[Location]]:
    """
    Encontra todas as referências a um símbolo (code ou bibref).

    Args:
        cached_result: CachedCompilation com LinkedProject
        word: Símbolo a procurar (code ou @bibref)
        workspace_root: Raiz do workspace para construir URIs
        include_declaration: Se deve incluir a declaração (definição) do símbolo

    Returns:
        Lista de Location com todas as referências, ou None se não encontrado
    """
    if not cached_result or not word:
        return None

    result = getattr(cached_result, "result", None)
    if not result:
        return None

    lp = getattr(result, "linked_project", None)
    if not lp:
        return None

    # Determinar tipo de símbolo
    if word.startswith("@"):
        # Bibref
        return _find_bibref_references(lp, word[1:], workspace_root, include_declaration)
    else:
        # Code
        return _find_code_references(lp, word, workspace_root, include_declaration)


def _find_code_references(
    lp,
    code: str,
    workspace_root: Optional[Path],
    include_declaration: bool
) -> Optional[list[Location]]:
    """
    Encontra todas as referências a um code.

    Args:
        lp: LinkedProject
        code: Nome do code
        workspace_root: Raiz do workspace
        include_declaration: Incluir definição na ontologia

    Returns:
        Lista de Location ou None
    """
    locations = []

    normalized = _normalize_code(code)

    # 1. Incluir declaração na ontologia (se solicitado)
    if include_declaration:
        ontology_index = getattr(lp, "ontology_index", {}) or {}
        onto_node = ontology_index.get(code) or ontology_index.get(normalized)
        if onto_node:
            onto_location = getattr(onto_node, "location", None)
            if onto_location:
                loc = _convert_to_lsp_location(onto_location, workspace_root)
                if loc:
                    locations.append(loc)

    # 2. Buscar usos nos arquivos .syn
    code_usage = getattr(lp, "code_usage", {}) or {}
    items = code_usage.get(code, code_usage.get(normalized, []))

    for item in items:
        # Localização do item
        item_location = getattr(item, "location", None)
        if item_location:
            loc = _convert_to_lsp_location(item_location, workspace_root)
            if loc:
                locations.append(loc)

    return locations if locations else None


def _find_bibref_references(
    lp,
    bibref: str,
    workspace_root: Optional[Path],
    include_declaration: bool
) -> Optional[list[Location]]:
    """
    Encontra todas as referências a um bibref.

    Args:
        lp: LinkedProject
        bibref: Bibref (sem @)
        workspace_root: Raiz do workspace
        include_declaration: Incluir definição na bibliografia

    Returns:
        Lista de Location ou None
    """
    locations = []

    # Normalizar bibref (remover @ se presente)
    bibref = _normalize_bibref(bibref)

    # 1. Incluir declaração na bibliografia (se solicitado)
    if include_declaration:
        bibliography = getattr(lp, "bibliography", {}) or {}
        bib_entry = bibliography.get(bibref)
        if bib_entry:
            bib_location = getattr(bib_entry, "location", None)
            if bib_location:
                loc = _convert_to_lsp_location(bib_location, workspace_root)
                if loc:
                    locations.append(loc)

    # 2. Buscar usos nos arquivos .syn
    sources = getattr(lp, "sources", {}) or {}

    for source_key, source in sources.items():
        # Verificar SOURCE.bibref
        source_bibref = getattr(source, "bibref", None)
        if source_bibref and _normalize_bibref(source_bibref) == bibref:
            source_location = getattr(source, "location", None)
            if source_location:
                loc = _convert_to_lsp_location(source_location, workspace_root)
                if loc:
                    locations.append(loc)

        # Verificar ITEM.bibref em cada item
        items = getattr(source, "items", []) or []
        for item in items:
            item_bibref = _extract_item_bibref(item)
            if item_bibref and _normalize_bibref(item_bibref) == bibref:
                # Procurar location do campo BIBREF especificamente
                item_location = getattr(item, "location", None)
                if item_location:
                    loc = _convert_to_lsp_location(item_location, workspace_root)
                    if loc:
                        locations.append(loc)

    return locations if locations else None


def _extract_item_bibref(item) -> Optional[str]:
    """Extrai bibref de um item usando múltiplas estratégias."""
    # Estratégia 1: Atributos diretos
    for key in ("bibref", "source_bibref", "bibref_id", "ref"):
        value = getattr(item, key, None)
        if value:
            return str(value)

    # Estratégia 2: extra_fields
    extra_fields = getattr(item, "extra_fields", {}) or {}
    bibref_field = extra_fields.get("BIBREF")
    if bibref_field:
        if isinstance(bibref_field, list) and bibref_field:
            return str(bibref_field[0])
        return str(bibref_field)

    # Estratégia 3: source.bibref
    source = getattr(item, "source", None)
    if source:
        source_bibref = getattr(source, "bibref", None)
        if source_bibref:
            return str(source_bibref)

    return None


def _normalize_bibref(bibref: str) -> str:
    """Normaliza bibref removendo @ prefix."""
    return bibref.lstrip("@").strip().lower()


def _normalize_code(code: str) -> str:
    return " ".join(code.strip().split()).lower()


def _convert_to_lsp_location(
    synesis_location,
    workspace_root: Optional[Path]
) -> Optional[Location]:
    """
    Converte SourceLocation do compilador para Location do LSP.

    Args:
        synesis_location: Location do compilador (1-based)
        workspace_root: Raiz do workspace

    Returns:
        Location do LSP (0-based) ou None
    """
    file_path = getattr(synesis_location, "file", None)
    line = getattr(synesis_location, "line", None)
    column = getattr(synesis_location, "column", None)

    if not file_path or line is None:
        return None

    # Construir URI
    path = Path(file_path)
    if not path.is_absolute():
        if workspace_root:
            path = workspace_root / path
        else:
            # Sem workspace_root, não podemos resolver path relativo
            path = path.resolve()

    uri = path.as_uri()

    # Converter coordenadas 1-based → 0-based
    lsp_line = max(0, line - 1)
    lsp_column = max(0, (column - 1) if column else 0)

    # Criar Range (início e fim na mesma posição)
    position = Position(line=lsp_line, character=lsp_column)
    range_ = Range(start=position, end=position)

    return Location(uri=uri, range=range_)
