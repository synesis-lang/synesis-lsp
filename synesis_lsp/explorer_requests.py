"""
explorer_requests.py - Custom requests para Synesis Explorer

Propósito:
    Três custom requests que substituem os parsers regex do Explorer
    com dados reais do compilador (via workspace_cache/LinkedProject).

Custom Requests:
    synesis/getReferences  → Lista de SOURCEs com contagem de items
    synesis/getCodes       → Lista de códigos com frequência de uso
    synesis/getRelations   → Lista de triples (relações entre conceitos)

Notas de implementação:
    - Todas dependem do workspace_cache (Step 1)
    - Se cache vazio, retornam {"success": False, "error": "..."}
    - Dados extraídos de LinkedProject (sources, code_usage, all_triples)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_references(cached_result) -> dict:
    """
    Retorna lista de SOURCEs com contagem de items.

    Cada referência inclui: bibref, itemCount, fields, location.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    refs = []
    for bibref, src in lp.sources.items():
        ref_entry = {
            "bibref": src.bibref,
            "itemCount": len(src.items),
            "fields": dict(src.fields) if src.fields else {},
        }
        if src.location:
            ref_entry["location"] = {
                "file": str(src.location.file),
                "line": src.location.line,
                "column": src.location.column,
            }
        refs.append(ref_entry)

    return {"success": True, "references": refs}


def get_codes(cached_result) -> dict:
    """
    Retorna lista de códigos com frequência de uso.

    Cada código inclui: code, usageCount, ontologyDefined.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    codes = []
    for code, items in lp.code_usage.items():
        codes.append({
            "code": code,
            "usageCount": len(items),
            "ontologyDefined": code in lp.ontology_index,
        })

    return {"success": True, "codes": codes}


def get_relations(cached_result) -> dict:
    """
    Retorna lista de triples (relações entre conceitos).

    Cada relação inclui: from, relation, to.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    relations = [
        {"from": s, "relation": r, "to": o}
        for s, r, o in lp.all_triples
    ]

    return {"success": True, "relations": relations}


def _get_linked_project(cached_result) -> Optional[object]:
    """Extrai linked_project do cached_result, ou None."""
    if not cached_result:
        return None
    result = getattr(cached_result, "result", None)
    if not result:
        return None
    lp = getattr(result, "linked_project", None)
    return lp
