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

from synesis.ast.normalize import normalize_code as _normalize_code

logger = logging.getLogger(__name__)


def _sanitize_id(name: str) -> str:
    """Sanitiza nome para uso como ID de nó Mermaid.js."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def get_relation_graph(
    cached_result,
    bibref: Optional[str] = None,
    item: Optional[str] = None,
    item_line: Optional[int] = None,
    item_file: Optional[str] = None,
    file: Optional[str] = None,
) -> dict:
    """
    Gera código Mermaid.js a partir das relações do projeto.

    Filtros (mutuamente exclusivos, por prioridade):
        file   → agrega todos os bibrefs (SOURCE + ITEM) presentes no arquivo
        item   → chains apenas do ITEM especificado
        bibref → chains do SOURCE especificado (todos os ITEMs do SOURCE)
        (none) → grafo completo do projeto
    """
    if not cached_result:
        return {"success": False, "error": "Projeto não carregado"}

    lp = getattr(cached_result.result, "linked_project", None)
    if not lp:
        return {"success": False, "error": "Projeto não carregado"}

    template = getattr(getattr(cached_result, "result", None), "template", None)

    triples = getattr(lp, "all_triples", None)
    if not triples and not bibref and not item and not file:
        logger.debug("get_relation_graph: No triples found")
        return {"success": True, "mermaidCode": "graph LR\n    empty[Sem relações]"}

    logger.debug(f"get_relation_graph: Found {len(triples) if triples else 0} total triples")

    # Filtro por arquivo: agrega todos os bibrefs do arquivo
    if file:
        logger.debug(f"get_relation_graph: Filtering by file='{file}'")
        triples = _triples_for_file(lp, template, file, cached_result)
        if not triples:
            return {
                "success": True,
                "mermaidCode": "graph LR\n    empty[Sem relações no arquivo]",
            }
        logger.debug(f"get_relation_graph: Filtered to {len(triples)} triples (file scope)")
    # Filtro por ITEM específico (bibref + arquivo + linha para desambiguar ITEMs com mesmo bibref)
    elif item:
        logger.debug(f"get_relation_graph: Filtering by item='{item}' file={item_file} line={item_line}")
        triples = _triples_for_item(lp, template, item, item_line, item_file)
        if not triples:
            return {
                "success": True,
                "mermaidCode": f"graph LR\n    empty[Sem relações para {item}]",
            }
        logger.debug(f"get_relation_graph: Filtered to {len(triples)} triples (item scope)")
    # Filtro por SOURCE (todos os ITEMs do SOURCE)
    elif bibref:
        logger.debug(f"get_relation_graph: Filtering by bibref='{bibref}'")
        triples = _triples_for_bibref(lp, template, bibref)
        if not triples:
            return {
                "success": True,
                "mermaidCode": f"graph LR\n    empty[Sem relações para {bibref}]",
            }
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


def _has_chain_relations(template) -> bool:
    if not template:
        return False
    field_specs = getattr(template, "field_specs", None) or {}
    chain_spec = field_specs.get("chain")
    if chain_spec and getattr(chain_spec, "relations", None):
        return True
    return False


def _normalize_bibref(value: str) -> str:
    return value.lstrip("@").strip().lower()


def _find_source_by_bibref(lp, bibref: str):
    normalized = _normalize_bibref(bibref)
    sources = getattr(lp, "sources", {}) or {}
    if isinstance(sources, dict):
        source = sources.get(normalized)
        if source:
            return source
        # Fallback: scan dict values
        for src in sources.values():
            if _normalize_bibref(getattr(src, "bibref", "")) == normalized:
                return src
        return None
    if isinstance(sources, (list, tuple, set)):
        for src in sources:
            if _normalize_bibref(getattr(src, "bibref", "")) == normalized:
                return src
    return None


def _chain_has_relations(chain, template) -> bool:
    relations = getattr(chain, "relations", None)
    if isinstance(relations, (list, tuple)) and relations:
        return True
    return _has_chain_relations(template)


def _item_chain_triples(item, template) -> list[tuple[str, str, str]]:
    """Extrai as triples dos chains de um único ITEM (chains nomeados + extra_fields)."""
    triples: list[tuple[str, str, str]] = []
    for chain in getattr(item, "chains", None) or []:
        if hasattr(chain, "to_triples"):
            triples.extend(
                chain.to_triples(has_relations=_chain_has_relations(chain, template))
            )
        else:
            triple = _extract_chain_triple(chain)
            if triple:
                triples.append(triple)
    # campos CHAIN com nome customizado ficam em extra_fields
    for val in (getattr(item, "extra_fields", None) or {}).values():
        if hasattr(val, "to_triples"):
            triples.extend(
                val.to_triples(has_relations=_chain_has_relations(val, template))
            )
    return triples


def _triples_for_file(lp, template, file_path: str, cached_result) -> list[tuple[str, str, str]]:
    """
    Agrega triples apenas dos ITEMs cujo location.file bate com o arquivo.

    Importante: filtra por ITEM, não por bibref. Num projeto onde todos os ITEMs
    compartilham o mesmo SOURCE (ex.: @biblia com um ITEM por versículo espalhados
    em vários .syn), expandir por bibref devolveria o grafo do projeto inteiro. Aqui
    coletamos somente as chains dos ITEMs declarados neste arquivo.
    """
    from pathlib import Path

    norm_file = Path(file_path).resolve()

    sources = getattr(lp, "sources", {}) or {}
    src_iter = sources.values() if isinstance(sources, dict) else sources

    seen: set[tuple] = set()
    result: list[tuple[str, str, str]] = []
    item_count = 0

    for src in src_iter:
        for it in getattr(src, "items", None) or []:
            it_loc = getattr(it, "location", None)
            it_file = getattr(it_loc, "file", None) if it_loc else None
            if it_file is None:
                continue
            try:
                if Path(it_file).resolve() != norm_file:
                    continue
            except Exception:
                continue

            item_count += 1
            for triple in _item_chain_triples(it, template):
                if triple not in seen:
                    seen.add(triple)
                    result.append(triple)

    logger.debug(
        f"_triples_for_file: '{file_path}' — {item_count} items, {len(result)} triples"
    )
    return result


def _triples_for_item(
    lp,
    template,
    item_bibref: str,
    item_line: Optional[int] = None,
    item_file: Optional[str] = None,
) -> list[tuple[str, str, str]]:
    """
    Extrai triples dos chains do ITEM especificado.

    Usa (item_file, item_line) para desambiguar quando múltiplos ITEMs
    compartilham o mesmo bibref (ex: todos os versículos de @biblia num projeto
    onde cada passagem é um ITEM diferente no mesmo SOURCE).
    """
    from pathlib import Path

    normalized = _normalize_bibref(item_bibref)
    norm_file = Path(item_file).resolve() if item_file else None

    logger.debug(
        f"_triples_for_item: bibref={item_bibref!r} normalized={normalized!r} "
        f"item_line={item_line!r} item_file={item_file!r} norm_file={norm_file!r}"
    )

    sources = getattr(lp, "sources", {}) or {}
    items_iter = sources.values() if isinstance(sources, dict) else sources

    for src in items_iter:
        for item in getattr(src, "items", None) or []:
            if _normalize_bibref(getattr(item, "bibref", "") or "") != normalized:
                continue

            loc = getattr(item, "location", None)
            loc_file = getattr(loc, "file", None) if loc else None
            loc_line = getattr(loc, "line", None) if loc else None
            item_start_0 = max(0, loc_line - 1) if loc_line is not None else None
            logger.debug(
                f"_triples_for_item: candidate item loc_file={loc_file!r} "
                f"loc_line={loc_line!r} item_start_0={item_start_0!r}"
            )

            # Filtro por arquivo
            if norm_file is not None and loc is not None:
                if loc_file is not None:
                    try:
                        resolved = Path(loc_file).resolve()
                        if resolved != norm_file:
                            logger.debug(
                                f"_triples_for_item: skip — file mismatch "
                                f"{resolved!r} != {norm_file!r}"
                            )
                            continue
                    except Exception:
                        pass

            # Filtro por linha (0-based)
            if item_line is not None and loc is not None:
                if item_start_0 != item_line:
                    logger.debug(
                        f"_triples_for_item: skip — line mismatch "
                        f"{item_start_0!r} != {item_line!r}"
                    )
                    continue

            triples = _item_chain_triples(item, template)
            logger.debug(f"_triples_for_item: matched item — {len(triples)} triples")
            if triples:
                return triples

    logger.debug("_triples_for_item: no matching item found")
    return []


def _triples_for_bibref(lp, template, bibref: str) -> list[tuple[str, str, str]]:
    # Stage 1: Extração direta dos chains do SOURCE (escopo restrito)
    source = _find_source_by_bibref(lp, bibref)
    if source:
        triples = []
        for item in getattr(source, "items", None) or []:
            for chain in getattr(item, "chains", None) or []:
                if hasattr(chain, "to_triples"):
                    triples.extend(
                        chain.to_triples(
                            has_relations=_chain_has_relations(chain, template)
                        )
                    )
                else:
                    triple = _extract_chain_triple(chain)
                    if triple:
                        triples.append(triple)
        if triples:
            return triples

    # Stage 2 (fallback): Filtro por códigos em all_triples
    relevant = _codes_for_bibref(lp, bibref)
    if not relevant:
        return []

    triples = []
    for subj, rel, obj in getattr(lp, "all_triples", None) or []:
        if _normalize_code(subj) in relevant or _normalize_code(obj) in relevant:
            triples.append((subj, rel, obj))

    return triples


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

    nodes = getattr(chain, "nodes", None)
    if isinstance(nodes, (list, tuple)) and len(nodes) >= 3:
        subj, rel, obj = nodes[0], nodes[1], nodes[2]
        if isinstance(subj, str) and isinstance(rel, str) and isinstance(obj, str):
            return subj, rel, obj

    return None


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
    ontology_codes = {
        _normalize_code(code) for code in getattr(lp, "ontology_index", {}) or {}
    }
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
            for code in _iter_codes_from_item_all(item, ontology_codes=ontology_codes):
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


def _iter_codes_from_item_all(
    item,
    ontology_codes: Optional[set[str]] = None
) -> Iterable[str]:
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
        # ChainNode: use nodes list when available
        nodes = getattr(chain, "nodes", None)
        if isinstance(nodes, (list, tuple)):
            for node in nodes:
                if not isinstance(node, str) or not node.strip():
                    continue
                if ontology_codes:
                    if _normalize_code(node) in ontology_codes:
                        yield node
                else:
                    yield node
            continue

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
