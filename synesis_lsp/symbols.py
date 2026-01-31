"""
symbols.py - Document symbols (outline view) para arquivos Synesis

Propósito:
    Usa compile_string() (~3ms para fragmentos, ~69ms para arquivos grandes) para
    produzir DocumentSymbol[] que o editor exibirá como outline/breadcrumb.

Mapeamento de nodes Synesis → LSP SymbolKind:
    SourceNode   → Class (com children ITEM → Method)
    ItemNode     → Method (standalone se não associado a SOURCE)
    OntologyNode → Struct
    ProjectNode  → Namespace

Notas de implementação:
    - compile_string() retorna nodes de nível superior
    - ItemNodes são retornados separados dos SourceNodes (linking não ocorre)
    - Agrupamos ItemNodes por bibref para criar hierarquia SOURCE > ITEM
    - location é 1-based; convertemos para 0-based no Range/Position LSP
    - Em caso de erro de parse, retorna lista vazia (sem crash)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import List, Optional

from lsprotocol.types import DocumentSymbol, Position, Range, SymbolKind

logger = logging.getLogger(__name__)


def compute_document_symbols(source: str, uri: str) -> List[DocumentSymbol]:
    """
    Computa document symbols para um arquivo Synesis.

    Usa compile_string para obter AST nodes, depois agrupa ItemNodes
    como children de seus SourceNodes correspondentes (por bibref).
    """
    try:
        import synesis

        nodes = synesis.compile_string(source, uri)
    except Exception:
        # Fallback: tenta extrair symbols via regex
        return _extract_symbols_regex(source)

    return _build_symbols_from_nodes(nodes, source)


def _build_symbols_from_nodes(nodes: list, source: str) -> List[DocumentSymbol]:
    """Constrói DocumentSymbol[] a partir dos AST nodes do compilador."""
    from synesis.ast.nodes import SourceNode, ItemNode, OntologyNode

    # Tenta importar ProjectNode (pode não existir em todas as versões)
    try:
        from synesis.ast.nodes import ProjectNode
    except ImportError:
        ProjectNode = None

    symbols: List[DocumentSymbol] = []
    lines = source.splitlines()

    # Separar nodes por tipo
    source_nodes: list = []
    item_nodes: list = []
    ontology_nodes: list = []
    project_nodes: list = []

    for node in nodes:
        if isinstance(node, SourceNode):
            source_nodes.append(node)
        elif isinstance(node, ItemNode):
            item_nodes.append(node)
        elif isinstance(node, OntologyNode):
            ontology_nodes.append(node)
        elif ProjectNode and isinstance(node, ProjectNode):
            project_nodes.append(node)

    # Agrupar items por bibref para associar a sources
    items_by_bibref: dict[str, list] = defaultdict(list)
    for item in item_nodes:
        items_by_bibref[item.bibref].append(item)

    matched_bibrefs: set = set()

    # SOURCE nodes com children ITEM
    for snode in source_nodes:
        children: List[DocumentSymbol] = []
        bibref = snode.bibref

        # Items que referenciam este source
        matching_items = items_by_bibref.get(bibref, [])
        if matching_items:
            matched_bibrefs.add(bibref)

        for i, item in enumerate(matching_items):
            item_range = _make_range(item.location, lines)
            # Exibe o quote truncado ou um índice
            item_detail = ""
            if hasattr(item, "quote") and item.quote:
                item_detail = item.quote[:60]
            children.append(
                DocumentSymbol(
                    name=f"ITEM #{i + 1}",
                    kind=SymbolKind.Method,
                    range=item_range,
                    selection_range=item_range,
                    detail=item_detail if item_detail else None,
                )
            )

        source_range = _make_range(snode.location, lines)
        # bibref já inclui @ quando vem do compilador
        display_bibref = bibref if bibref.startswith("@") else f"@{bibref}"
        symbols.append(
            DocumentSymbol(
                name=f"SOURCE {display_bibref}",
                kind=SymbolKind.Class,
                range=source_range,
                selection_range=source_range,
                children=children if children else None,
            )
        )

    # Items órfãos (sem SOURCE correspondente)
    for bibref, items in items_by_bibref.items():
        if bibref in matched_bibrefs:
            continue
        display_ref = bibref if bibref.startswith("@") else f"@{bibref}"
        for i, item in enumerate(items):
            item_range = _make_range(item.location, lines)
            symbols.append(
                DocumentSymbol(
                    name=f"ITEM {display_ref} #{i + 1}",
                    kind=SymbolKind.Method,
                    range=item_range,
                    selection_range=item_range,
                )
            )

    # ONTOLOGY nodes
    for onode in ontology_nodes:
        onto_range = _make_range(onode.location, lines)
        symbols.append(
            DocumentSymbol(
                name=f"ONTOLOGY {onode.concept}",
                kind=SymbolKind.Struct,
                range=onto_range,
                selection_range=onto_range,
            )
        )

    # PROJECT nodes
    for pnode in project_nodes:
        proj_range = _make_range(pnode.location, lines)
        symbols.append(
            DocumentSymbol(
                name=f"PROJECT {pnode.name}",
                kind=SymbolKind.Namespace,
                range=proj_range,
                selection_range=proj_range,
            )
        )

    return symbols


def _make_range(location, lines: List[str]) -> Range:
    """
    Cria Range LSP a partir de SourceLocation (1-based → 0-based).

    Como location só indica o início do bloco, a range cobre
    apenas a linha de declaração (usado para selection_range/navegação).
    """
    if location is None:
        return Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0),
        )

    line_0 = max(0, location.line - 1)  # 1-based → 0-based
    col_0 = max(0, location.column - 1)

    # Comprimento da linha para o end
    end_char = 0
    if line_0 < len(lines):
        end_char = len(lines[line_0])

    return Range(
        start=Position(line=line_0, character=col_0),
        end=Position(line=line_0, character=end_char),
    )


# --- Fallback regex para quando compile_string falha ---

_RE_SOURCE = re.compile(r"^\s*(SOURCE)\s+@(\w+)", re.MULTILINE)
_RE_ITEM = re.compile(r"^\s*(ITEM)\s+@(\w+)", re.MULTILINE)
_RE_ONTOLOGY = re.compile(r"^\s*(ONTOLOGY)\s+(\w+)", re.MULTILINE)
_RE_PROJECT = re.compile(r"^\s*(PROJECT)\s+(\w+)", re.MULTILINE)


def _extract_symbols_regex(source: str) -> List[DocumentSymbol]:
    """Extrai symbols usando regex puro (fallback para erros de parse)."""
    symbols: List[DocumentSymbol] = []
    lines = source.splitlines()

    for m in _RE_SOURCE.finditer(source):
        line_idx = source[:m.start()].count("\n")
        col = m.start(1) - source.rfind("\n", 0, m.start(1)) - 1
        end_char = len(lines[line_idx]) if line_idx < len(lines) else 0
        r = Range(
            start=Position(line=line_idx, character=col),
            end=Position(line=line_idx, character=end_char),
        )
        symbols.append(
            DocumentSymbol(
                name=f"SOURCE @{m.group(2)}",
                kind=SymbolKind.Class,
                range=r,
                selection_range=r,
            )
        )

    for m in _RE_ONTOLOGY.finditer(source):
        line_idx = source[:m.start()].count("\n")
        col = m.start(1) - source.rfind("\n", 0, m.start(1)) - 1
        end_char = len(lines[line_idx]) if line_idx < len(lines) else 0
        r = Range(
            start=Position(line=line_idx, character=col),
            end=Position(line=line_idx, character=end_char),
        )
        symbols.append(
            DocumentSymbol(
                name=f"ONTOLOGY {m.group(2)}",
                kind=SymbolKind.Struct,
                range=r,
                selection_range=r,
            )
        )

    for m in _RE_PROJECT.finditer(source):
        line_idx = source[:m.start()].count("\n")
        col = m.start(1) - source.rfind("\n", 0, m.start(1)) - 1
        end_char = len(lines[line_idx]) if line_idx < len(lines) else 0
        r = Range(
            start=Position(line=line_idx, character=col),
            end=Position(line=line_idx, character=end_char),
        )
        symbols.append(
            DocumentSymbol(
                name=f"PROJECT {m.group(2)}",
                kind=SymbolKind.Namespace,
                range=r,
                selection_range=r,
            )
        )

    return symbols
