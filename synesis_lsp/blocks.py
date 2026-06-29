"""
blocks.py - Retorna blocos SOURCE/ITEM com bibref e range estruturados

Propósito:
    Custom request synesis/getBlocks — substitui synesisParser.js na extensão.
    Fornece (kind, bibref, range) por bloco, sem string-parsing de labels no cliente.

Custom Request:
    synesis/getBlocks → lista de blocos SOURCE e ITEM com range LSP e bibref resolvido

Notas de implementação:
    - Reutiliza compile_string() (mesmo caminho de symbols.py)
    - Fallback regex para texto inválido (cursor em documento sendo editado)
    - bibref normalizado sem '@' (como coderService espera)
    - range em coordenadas 0-based (padrão LSP)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback regex — use `regex` module (suporta \p{L}) se disponível, senão \w
try:
    import regex as _re_module
    _RE_SOURCE = _re_module.compile(r"^\s*SOURCE\s+@([\p{L}\p{N}._-]+)", _re_module.MULTILINE)
    _RE_ITEM = _re_module.compile(r"^\s*ITEM\s+@([\p{L}\p{N}._-]+)", _re_module.MULTILINE)
except ImportError:
    _RE_SOURCE = re.compile(r"^\s*SOURCE\s+@([\w._-]+)", re.MULTILINE)
    _RE_ITEM = re.compile(r"^\s*ITEM\s+@([\w._-]+)", re.MULTILINE)


def get_blocks(file_path: str, workspace_root: Optional[Path] = None) -> dict:
    """
    Retorna blocos SOURCE e ITEM de um arquivo .syn com bibref e range.

    Args:
        file_path: Caminho para arquivo .syn
        workspace_root: Raiz do workspace para resolver paths relativos

    Returns:
        {
            "success": bool,
            "blocks": [
                {
                    "kind": "SOURCE" | "ITEM",
                    "bibref": str,           # sem '@'
                    "range": {
                        "start": {"line": int, "character": int},
                        "end":   {"line": int, "character": int}
                    }
                }
            ]
        }
    """
    if not file_path:
        return {"success": False, "error": "Parâmetro 'file' não fornecido"}

    path = Path(file_path)
    if not path.is_absolute() and workspace_root:
        path = workspace_root / path

    if not path.exists():
        return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}

    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"success": False, "error": f"Erro ao ler arquivo: {exc}"}

    blocks = _extract_blocks(source, str(path))
    return {"success": True, "blocks": blocks}


def _extract_blocks(source: str, uri: str) -> list[dict]:
    """Extrai blocos via compile_string; fallback regex se parse falhar."""
    try:
        import synesis
        nodes = synesis.compile_string(source, uri)
        return _blocks_from_nodes(nodes, source)
    except Exception:
        return _blocks_from_regex(source)


def _blocks_from_nodes(nodes: list, source: str) -> list[dict]:
    """Constrói lista de blocos a partir dos AST nodes do compilador."""
    from synesis.ast.nodes import ItemNode, SourceNode

    lines = source.splitlines()

    # Linha de início de todos os nodes top-level (para calcular fim de cada bloco)
    all_start_lines: list[int] = sorted(
        node.location.line
        for node in nodes
        if getattr(node, "location", None) is not None
    )

    def _block_end(start_line_1based: int) -> tuple[int, int]:
        """Retorna (line_0based, character) do fim do bloco."""
        if start_line_1based in all_start_lines:
            idx = all_start_lines.index(start_line_1based)
            if idx + 1 < len(all_start_lines):
                end_line_0 = all_start_lines[idx + 1] - 2
            else:
                end_line_0 = max(0, len(lines) - 1)
        else:
            end_line_0 = max(0, len(lines) - 1)
        end_char = len(lines[end_line_0]) if end_line_0 < len(lines) else 0
        return end_line_0, end_char

    # Agrupar items por bibref para herdar bibref do SOURCE pai quando necessário
    source_nodes = [n for n in nodes if isinstance(n, SourceNode)]
    item_nodes = [n for n in nodes if isinstance(n, ItemNode)]

    blocks: list[dict] = []

    for snode in source_nodes:
        loc = snode.location
        if loc is None:
            continue
        start_0 = max(0, loc.line - 1)
        start_col = max(0, loc.column - 1)
        end_0, end_char = _block_end(loc.line)
        bibref = _normalize_bibref(snode.bibref)
        blocks.append({
            "kind": "SOURCE",
            "bibref": bibref,
            "range": {
                "start": {"line": start_0, "character": start_col},
                "end":   {"line": end_0,   "character": end_char},
            },
        })

    for item in item_nodes:
        loc = item.location
        if loc is None:
            continue
        start_0 = max(0, loc.line - 1)
        start_col = max(0, loc.column - 1)
        end_0, end_char = _block_end(loc.line)
        bibref = _normalize_bibref(item.bibref)
        blocks.append({
            "kind": "ITEM",
            "bibref": bibref,
            "range": {
                "start": {"line": start_0, "character": start_col},
                "end":   {"line": end_0,   "character": end_char},
            },
        })

    # Ordenar por linha de início
    blocks.sort(key=lambda b: b["range"]["start"]["line"])
    return blocks


def _blocks_from_regex(source: str) -> list[dict]:
    """Fallback: extrai blocos via regex quando compile_string falha (doc inválido)."""
    lines = source.splitlines()
    blocks: list[dict] = []

    all_matches: list[tuple[int, str, str]] = []  # (line_idx, kind, bibref)
    for m in _RE_SOURCE.finditer(source):
        line_idx = source[: m.start()].count("\n")
        all_matches.append((line_idx, "SOURCE", m.group(1)))
    for m in _RE_ITEM.finditer(source):
        line_idx = source[: m.start()].count("\n")
        all_matches.append((line_idx, "ITEM", m.group(1)))

    all_matches.sort(key=lambda t: t[0])

    for i, (line_idx, kind, bibref) in enumerate(all_matches):
        if i + 1 < len(all_matches):
            end_line = all_matches[i + 1][0] - 1
        else:
            end_line = max(0, len(lines) - 1)
        end_char = len(lines[end_line]) if end_line < len(lines) else 0
        col = len(lines[line_idx]) - len(lines[line_idx].lstrip()) if line_idx < len(lines) else 0
        blocks.append({
            "kind": kind,
            "bibref": _normalize_bibref(bibref),
            "range": {
                "start": {"line": line_idx, "character": col},
                "end":   {"line": end_line,  "character": end_char},
            },
        })

    return blocks


def _normalize_bibref(value: str) -> str:
    """Remove '@' e espaços — formato esperado pelo coderService."""
    return str(value).lstrip("@").strip()
