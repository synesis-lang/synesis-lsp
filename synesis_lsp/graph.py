"""
graph.py - Geração de grafo Mermaid.js a partir de relações do projeto

Propósito:
    Converte all_triples do LinkedProject em código Mermaid.js para
    visualização de relações entre conceitos da ontologia.

Notas de implementação:
    - Depende do workspace_cache para linked_project.all_triples
    - Filtra por bibref se fornecido (via code_usage)
    - Sanitiza IDs para compatibilidade com Mermaid.js
    - Retorna dict com success/error ou mermaidCode
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _sanitize_id(name: str) -> str:
    """Sanitiza nome para uso como ID de nó Mermaid.js."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def get_relation_graph(cached_result, bibref: Optional[str] = None) -> dict:
    """
    Gera código Mermaid.js a partir das relações do projeto.

    Args:
        cached_result: CachedCompilation do workspace_cache
        bibref: Se fornecido, filtra relações que envolvem códigos
                usados por esse bibref

    Returns:
        dict com 'success' e 'mermaidCode' ou 'error'
    """
    if not cached_result:
        return {"success": False, "error": "Projeto não carregado"}

    lp = getattr(cached_result.result, "linked_project", None)
    if not lp:
        return {"success": False, "error": "Projeto não carregado"}

    triples = getattr(lp, "all_triples", None)
    if not triples:
        logger.debug("get_relation_graph: No triples found")
        return {"success": True, "mermaidCode": "graph LR\n    empty[Sem relações]"}

    logger.debug(f"get_relation_graph: Found {len(triples)} total triples")

    # Se bibref fornecido, filtrar relações
    if bibref:
        logger.debug(f"get_relation_graph: Filtering by bibref='{bibref}'")

        relevant_codes = _codes_for_bibref(lp, bibref)

        if not relevant_codes:
            logger.debug(f"get_relation_graph: No codes found for bibref '{bibref}'")
            return {
                "success": True,
                "mermaidCode": f"graph LR\n    empty[Sem relações para {bibref}]",
            }

        logger.debug(f"get_relation_graph: Found {len(relevant_codes)} codes for bibref: {relevant_codes}")

        triples = [
            (s, r, o)
            for s, r, o in triples
            if _normalize_code(s) in relevant_codes or _normalize_code(o) in relevant_codes
        ]

        logger.debug(f"get_relation_graph: Filtered to {len(triples)} triples")

    if not triples:
        logger.debug("get_relation_graph: No triples after filtering")
        return {"success": True, "mermaidCode": "graph LR\n    empty[Sem relações]"}

    lines = ["graph LR"]
    seen = set()
    for subj, rel, obj in triples:
        key = (subj, rel, obj)
        if key in seen:
            continue
        seen.add(key)
        s_id = _sanitize_id(subj)
        o_id = _sanitize_id(obj)
        lines.append(f"    {s_id}[{subj}] -->|{rel}| {o_id}[{obj}]")

    mermaid_code = "\n".join(lines)
    logger.debug(f"get_relation_graph: Generated {len(lines)-1} edges")

    return {"success": True, "mermaidCode": mermaid_code}


def _normalize_bibref(value: str) -> str:
    return value.lstrip("@").strip().lower()


def _normalize_code(value: str) -> str:
    return value.strip().lower()


def _codes_for_bibref(lp, bibref: str) -> set[str]:
    """
    Find all codes used by items that reference the given bibref.

    Uses enhanced _item_bibref() with more fallback strategies.
    Stage 2 uses _iter_codes_from_item_all() without ontology filter.
    """
    normalized = _normalize_bibref(bibref)
    if not normalized:
        return set()

    relevant: set[str] = set()

    # Stage 1: Try code_usage (with enhanced _item_bibref)
    code_usage = getattr(lp, "code_usage", {}) or {}
    if code_usage:
        for code, items in code_usage.items():
            for item in _iter_items(items):
                item_bibref = _item_bibref(item)  # Now has more fallbacks
                if not item_bibref:
                    continue
                if _normalize_bibref(item_bibref) == normalized:
                    relevant.add(_normalize_code(code))
                    break  # Found match, move to next code

    # If stage 1 found codes, return early
    if relevant:
        logger.debug(f"_codes_for_bibref: Stage 1 found {len(relevant)} codes via code_usage")
        return relevant

    # Stage 2: Fallback to sources iteration (use _iter_codes_from_item_all)
    sources = getattr(lp, "sources", {}) or {}
    for src in _iter_sources(sources):
        src_bibref = getattr(src, "bibref", None)
        if not src_bibref:
            continue

        # Check if source matches bibref
        if _normalize_bibref(str(src_bibref)) != normalized:
            continue

        # Extract ALL codes from items in this source (no ontology filter)
        for item in getattr(src, "items", []) or []:
            for code in _iter_codes_from_item_all(item):
                relevant.add(_normalize_code(code))

    if relevant:
        logger.debug(f"_codes_for_bibref: Stage 2 found {len(relevant)} codes via sources")

    return relevant


def _iter_sources(sources) -> Iterable:
    if isinstance(sources, dict):
        yield from sources.values()
        return
    if isinstance(sources, (list, tuple, set)):
        yield from sources
        return


def _iter_items(items) -> Iterable:
    if isinstance(items, dict):
        yield from items.values()
        return
    if isinstance(items, (list, tuple, set)):
        yield from items
        return
    if items is not None:
        yield items


def _item_bibref(item) -> Optional[str]:
    """
    Extract bibref from item using multiple fallback strategies.

    Tries: bibref, source_bibref, bibref_id, ref → source.bibref → parent.bibref
    """
    if not item:
        return None

    # Strategy 1: Direct bibref attributes
    for key in ("bibref", "source_bibref", "bibref_id", "ref"):
        value = getattr(item, key, None)
        if value:
            return str(value)

    # Strategy 2: Navigate through source
    source = getattr(item, "source", None)
    if source is not None:
        source_bibref = getattr(source, "bibref", None)
        if source_bibref:
            return str(source_bibref)

    # Strategy 3: Navigate through parent
    parent = getattr(item, "parent", None)
    if parent is not None:
        parent_bibref = getattr(parent, "bibref", None)
        if parent_bibref:
            return str(parent_bibref)

    return None


def _iter_string_values(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_string_values(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)


def _iter_codes_from_item(item, ontology_codes: set[str]) -> Iterable[str]:
    codes = getattr(item, "codes", None) or []
    for code in codes:
        if isinstance(code, str) and code.strip():
            yield code

    chains = getattr(item, "chains", None) or []
    for chain in chains:
        triple = _extract_chain_triple(chain)
        if not triple:
            continue
        subj, _rel, obj = triple
        if isinstance(subj, str) and subj.strip():
            yield subj
        if isinstance(obj, str) and obj.strip():
            yield obj

    extra_fields = getattr(item, "extra_fields", {}) or {}
    if ontology_codes:
        for value in extra_fields.values():
            for code in _iter_string_values(value):
                if _normalize_code(code) in ontology_codes:
                    yield code


def _iter_codes_from_item_all(item) -> Iterable[str]:
    """
    Extract ALL codes from item without ontology filtering.

    Enhancement over _iter_codes_from_item():
        - No ontology_codes filter (extracts all codes)
        - Used for bibref filtering fallback
    """
    # Extract from codes list
    codes = getattr(item, "codes", None) or []
    for code in codes:
        if isinstance(code, str) and code.strip():
            yield code

    # Extract from chains (subject and object)
    chains = getattr(item, "chains", None) or []
    for chain in chains:
        triple = _extract_chain_triple(chain)
        if not triple:
            continue
        subj, _rel, obj = triple
        if isinstance(subj, str) and subj.strip():
            yield subj
        if isinstance(obj, str) and obj.strip():
            yield obj

    # Extract from extra_fields (all codes, no ontology filter)
    extra_fields = getattr(item, "extra_fields", {}) or {}
    for value in extra_fields.values():
        # Try chains first
        for candidate in _iter_chain_values(value):
            triple = _extract_chain_triple(candidate)
            if triple:
                subj, _rel, obj = triple
                if isinstance(subj, str) and subj.strip():
                    yield subj
                if isinstance(obj, str) and obj.strip():
                    yield obj
                continue  # Don't process as string code

        # Try string codes
        for code in _iter_string_values(value):
            if isinstance(code, str) and code.strip():
                yield code


def _iter_chain_values(value) -> Iterable:
    """Iterator for chain objects in nested structures."""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield item
        return
    if isinstance(value, dict):
        for item in value.values():
            yield item
        return
    yield value


def _extract_chain_triple(chain) -> Optional[tuple[str, str, str]]:
    if isinstance(chain, (list, tuple)) and len(chain) >= 3:
        subj, rel, obj = chain[0], chain[1], chain[2]
        if isinstance(subj, str) and isinstance(rel, str) and isinstance(obj, str):
            return subj, rel, obj

    if isinstance(chain, dict):
        for keys in (("from", "relation", "to"), ("subject", "relation", "object")):
            if all(k in chain for k in keys):
                subj, rel, obj = chain[keys[0]], chain[keys[1]], chain[keys[2]]
                if isinstance(subj, str) and isinstance(rel, str) and isinstance(obj, str):
                    return subj, rel, obj

    candidates = [
        ("from_code", "relation", "to_code"),
        ("source", "relation", "target"),
        ("subject", "relation", "object"),
        ("subj", "rel", "obj"),
        ("from", "relation", "to"),
        ("left", "relation", "right"),
    ]
    for subj_key, rel_key, obj_key in candidates:
        subj = getattr(chain, subj_key, None)
        rel = getattr(chain, rel_key, None)
        obj = getattr(chain, obj_key, None)
        if isinstance(subj, str) and isinstance(rel, str) and isinstance(obj, str):
            return subj, rel, obj

    return None
