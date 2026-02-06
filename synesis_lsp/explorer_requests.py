"""
explorer_requests.py - Custom requests para Synesis Explorer

Propósito:
    Três custom requests que substituem os parsers regex do Explorer
    com dados reais do compilador (via workspace_cache/LinkedProject).

Custom Requests:
    synesis/getReferences  → Lista de SOURCEs com contagem de items
    synesis/getCodes       → Lista de códigos com frequência de uso e occurrences
    synesis/getRelations   → Lista de triples (relações entre conceitos) com location/type

Notas de implementação:
    - Todas dependem do workspace_cache (Step 1)
    - Se cache vazio, retornam {"success": False, "error": "..."}
    - Dados extraídos de LinkedProject (sources, code_usage, all_triples)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

_RELATIONS_CACHE: dict[tuple[str, float], dict] = {}
_RELATIONS_CACHE_MAX = 4


def _relations_cache_key(cached_result, workspace_root: Optional[Path]) -> Optional[tuple[str, int, float]]:
    if not cached_result:
        return None
    root = workspace_root or getattr(cached_result, "workspace_root", None)
    root_key = str(root) if root else ""
    timestamp = getattr(cached_result, "timestamp", None)
    if timestamp is None:
        return None
    return (root_key, id(cached_result), float(timestamp))


def _relations_cache_set(key: Optional[tuple[str, float]], value: dict) -> None:
    if not key:
        return
    _RELATIONS_CACHE[key] = value
    if len(_RELATIONS_CACHE) > _RELATIONS_CACHE_MAX:
        oldest_key = next(iter(_RELATIONS_CACHE))
        if oldest_key != key:
            _RELATIONS_CACHE.pop(oldest_key, None)


def get_references(cached_result) -> dict:
    """
    Retorna lista de SOURCEs com contagem de items.

    Cada referência inclui: bibref, itemCount, fields, location.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    workspace_root = getattr(cached_result, "workspace_root", None)
    refs = []
    for bibref, src in lp.sources.items():
        ref_entry = {
            "bibref": src.bibref,
            "itemCount": len(src.items),
            "fields": dict(src.fields) if src.fields else {},
        }
        if src.location:
            ref_entry["location"] = {
                "file": _relativize_path(str(src.location.file), workspace_root),
                "line": src.location.line,
                "column": src.location.column,
            }
        refs.append(ref_entry)

    return {"success": True, "references": refs}


def get_codes(cached_result) -> dict:
    """
    Retorna lista de códigos com frequência de uso.

    Cada código inclui: code, usageCount, ontologyDefined, occurrences.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    workspace_root = getattr(cached_result, "workspace_root", None)
    template = getattr(getattr(cached_result, "result", None), "template", None)
    field_specs = getattr(template, "field_specs", {}) if template else {}

    code_fields, chain_fields, chain_relations = _item_field_maps(field_specs)
    include_code = True
    include_chain = True

    codes = []
    raw_usage = _get_code_usage(lp, field_specs) or {}
    code_usage: dict[str, list] = {}
    for code, items in raw_usage.items():
        norm_code = _normalize_code(code)
        code_usage.setdefault(norm_code, []).extend(items)

    # Garantir presença de todos os códigos da ontologia, mesmo sem uso
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    for code in ontology_index.keys():
        code_usage.setdefault(code, [])

    # Deduplicar items por identidade de objeto (normalizacao pode mesclar
    # listas de chaves diferentes que referenciam o mesmo ItemNode)
    for code in code_usage:
        items = code_usage[code]
        seen_ids: set[int] = set()
        unique: list = []
        for item in items:
            item_id = id(item)
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                unique.append(item)
        code_usage[code] = unique

    for code, items in (code_usage or {}).items():
        occurrences = _build_code_occurrences(
            code,
            items,
            field_specs,
            workspace_root,
            code_fields=code_fields,
            chain_fields=chain_fields,
            chain_relations=chain_relations,
        )
        occurrences = _filter_occurrences_by_template(
            occurrences,
            include_code=include_code,
            include_chain=include_chain,
        )
        occurrences = _dedupe_occurrences(occurrences)
        codes.append(
            {
                "code": code,
                "usageCount": len(items),
                "ontologyDefined": _normalize_code(code) in lp.ontology_index,
                "occurrences": occurrences,
            }
        )

    return {"success": True, "codes": codes}


def get_relations(cached_result) -> dict:
    """
    Retorna lista de triples (relações entre conceitos).

    Cada relação inclui: from, relation, to, location?, type?.
    """
    lp = _get_linked_project(cached_result)
    if lp is None:
        return {"success": False, "error": "Projeto não carregado"}

    workspace_root = getattr(cached_result, "workspace_root", None)
    cache_key = _relations_cache_key(cached_result, workspace_root)
    cached = _RELATIONS_CACHE.get(cache_key) if cache_key else None
    if cached is not None:
        return cached

    relation_index = _build_relation_index(lp, workspace_root)
    relations = []
    triples = getattr(lp, "all_triples", None) or []
    for s, r, o in triples:
        entry = {"from": s, "relation": r, "to": o}
        key = _normalize_triple(s, r, o)
        indexed = relation_index.get(key)
        if indexed:
            if indexed.get("location"):
                entry["location"] = indexed["location"]
            if indexed.get("type"):
                entry["type"] = indexed["type"]
        relations.append(entry)

    result = {"success": True, "relations": relations}
    _relations_cache_set(cache_key, result)
    return result


def _get_linked_project(cached_result) -> Optional[object]:
    """Extrai linked_project do cached_result, ou None."""
    if not cached_result:
        return None
    result = getattr(cached_result, "result", None)
    if not result:
        return None
    lp = getattr(result, "linked_project", None)
    return lp


def _iter_sources(sources) -> Iterable:
    if isinstance(sources, dict):
        yield from sources.values()
        return
    if isinstance(sources, (list, tuple, set)):
        yield from sources
        return


def _normalize_code(value: str) -> str:
    return value.strip().lower()


def _normalize_triple(subject: str, relation: str, obj: str) -> tuple[str, str, str]:
    return (
        _normalize_code(subject),
        _normalize_code(relation),
        _normalize_code(obj),
    )


def _normalize_file_path(path_str: str) -> Optional[Path]:
    if not path_str:
        return None
    if path_str.startswith("file://"):
        parsed = urlparse(path_str)
        path_val = unquote(parsed.path or "")
        if parsed.netloc:
            path_val = f"//{parsed.netloc}{path_val}"
        if len(path_val) >= 3 and path_val[0] == "/" and path_val[2] == ":":
            path_val = path_val[1:]
        return Path(path_val)
    return Path(path_str)


def _relativize_path(path_str: str, workspace_root: Optional[Path]) -> str:
    path = _normalize_file_path(path_str)
    if not path:
        return path_str
    if workspace_root:
        try:
            return path.relative_to(workspace_root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


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


def _iter_chain_values(value) -> Iterable:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield item
        return
    if isinstance(value, dict):
        for item in value.values():
            yield item
        return
    yield value


def _chain_nodes(chain) -> list[str]:
    if chain is None:
        return []
    if isinstance(chain, str):
        if "->" in chain:
            return [part.strip() for part in chain.split("->") if part.strip()]
        return [chain]
    if isinstance(chain, dict):
        nodes = chain.get("nodes")
        if isinstance(nodes, (list, tuple)):
            return [n for n in nodes if isinstance(n, str) and n.strip()]
        # Try common triple dict shapes
        for keys in (("from", "relation", "to"), ("subject", "relation", "object")):
            if all(k in chain for k in keys):
                parts = [chain[keys[0]], chain[keys[1]], chain[keys[2]]]
                return [p for p in parts if isinstance(p, str) and p.strip()]
        return []
    nodes = getattr(chain, "nodes", None)
    if isinstance(nodes, (list, tuple)):
        return [n for n in nodes if isinstance(n, str) and n.strip()]
    if isinstance(chain, (list, tuple, set)):
        return [n for n in chain if isinstance(n, str) and n.strip()]
    return []


def _extract_chain_codes(chain, field_spec=None) -> list[str]:
    nodes = [n.strip() for n in _chain_nodes(chain) if isinstance(n, str) and n.strip()]
    if not nodes:
        return []
    has_relations = bool(getattr(field_spec, "relations", None))
    if has_relations:
        relations = getattr(chain, "relations", None)
        if isinstance(relations, (list, tuple)) and relations:
            return nodes
        if len(nodes) >= 3 and len(nodes) % 2 == 1:
            return nodes[::2]
    return nodes


def _chain_value_contains_code(value, code: str, field_spec=None) -> bool:
    target = _normalize_code(code)
    for candidate in _iter_chain_values(value):
        for chain_code in _extract_chain_codes(candidate, field_spec):
            if _normalize_code(chain_code) == target:
                return True
    return False


def _value_contains_code(value, code: str) -> bool:
    target = _normalize_code(code)
    for item in _iter_string_values(value):
        if _normalize_code(item) == target:
            return True
    return False


def _is_chain_field(spec) -> bool:
    if not spec:
        return False
    if getattr(spec, "relations", None):
        return True
    spec_type = getattr(spec, "type", None)
    type_name = getattr(spec_type, "name", None) or str(spec_type or "")
    return "CHAIN" in type_name.upper()


def _is_code_field(spec) -> bool:
    if not spec:
        return False
    spec_type = getattr(spec, "type", None)
    type_name = getattr(spec_type, "name", None) or str(spec_type or "")
    return "CODE" in type_name.upper() and "CHAIN" not in type_name.upper()


def _item_field_maps(field_specs: dict) -> tuple[set[str], set[str], dict[str, bool]]:
    code_fields: set[str] = {"code", "codes"}
    chain_fields: set[str] = {"chain", "chains"}
    chain_relations: dict[str, bool] = {}

    for name, spec in (field_specs or {}).items():
        scope = getattr(spec, "scope", None)
        scope_name = getattr(scope, "name", None) or str(scope or "")
        scope_name = scope_name.split(".")[-1].upper()
        if scope_name != "ITEM":
            continue

        spec_type = getattr(spec, "type", None)
        type_name = getattr(spec_type, "name", None) or str(spec_type or "")
        field_name = str(name).lower()

        if type_name.upper() == "CODE":
            code_fields.add(field_name)

        if _is_chain_field(spec):
            chain_fields.add(field_name)
            chain_relations[field_name] = bool(getattr(spec, "relations", None))

    for field_name in chain_fields:
        chain_relations.setdefault(field_name, False)

    return code_fields, chain_fields, chain_relations


def _get_code_usage(lp, field_specs) -> dict:
    raw_usage = None
    for attr_name in (
        "code_usage",
        "code_usage_index",
        "code_usage_by_code",
        "code_usage_map",
    ):
        value = getattr(lp, attr_name, None)
        if value and hasattr(value, "items"):
            raw_usage = value
            break

    if not raw_usage:
        return _build_code_usage_from_sources(
            lp,
            field_specs,
            include_code=True,
            include_chain=True,
        )

    usage: dict[str, list] = {}
    for code, items in raw_usage.items():
        usage[code] = list(items)

    # Complementar com códigos de CHAIN que não aparecem em code_usage.
    chain_usage = _build_code_usage_from_sources(
        lp,
        field_specs,
        include_code=False,
        include_chain=True,
    )
    for code, items in chain_usage.items():
        if code in usage:
            continue
        usage[code] = list(items)

    return usage


def _build_code_usage_from_sources(
    lp,
    field_specs,
    *,
    include_code: bool = True,
    include_chain: bool = True,
) -> dict:
    usage: dict[str, list] = {}
    sources = getattr(lp, "sources", {}) or {}
    for src in _iter_sources(sources):
        for item in getattr(src, "items", []) or []:
            for code in _iter_codes_from_item(
                item,
                field_specs,
                include_code=include_code,
                include_chain=include_chain,
            ):
                usage.setdefault(code, []).append(item)
    return usage


def _iter_codes_from_item(
    item,
    field_specs,
    *,
    include_code: bool = True,
    include_chain: bool = True,
) -> Iterable[str]:
    if include_code:
        codes = getattr(item, "codes", None) or []
        for code in codes:
            if isinstance(code, str) and code.strip():
                yield code

    if include_chain:
        chains = getattr(item, "chains", None) or []
        chain_spec = field_specs.get("chain") if field_specs else None
        for chain in chains:
            for chain_code in _extract_chain_codes(chain, chain_spec):
                if isinstance(chain_code, str) and chain_code.strip():
                    yield chain_code

    extra_fields = getattr(item, "extra_fields", {}) or {}
    for field_name, value in extra_fields.items():
        spec = field_specs.get(field_name) if field_specs else None
        if _is_chain_field(spec):
            if include_chain:
                for candidate in _iter_chain_values(value):
                    for chain_code in _extract_chain_codes(candidate, spec):
                        if isinstance(chain_code, str) and chain_code.strip():
                            yield chain_code
            continue
        if not _is_code_field(spec):
            continue
        if not include_code:
            continue
        for code in _iter_string_values(value):
            if isinstance(code, str) and code.strip():
                yield code




def _get_item_location(item):
    """Resolve best-available location for an item."""
    loc = getattr(item, "location", None)
    if loc and getattr(loc, "file", None):
        return loc
    source = getattr(item, "source", None)
    source_loc = getattr(source, "location", None) if source else None
    if source_loc and getattr(source_loc, "file", None):
        return source_loc
    return loc or source_loc


def _location_to_occurrence(
    location,
    workspace_root: Optional[Path],
    fallback_file: Optional[str] = None,
) -> Optional[tuple[str, int, int]]:
    if not location:
        return None
    if isinstance(location, dict):
        file_val = location.get("file")
        line = location.get("line")
        column = location.get("column")
    else:
        file_val = getattr(location, "file", None)
        line = getattr(location, "line", None)
        column = getattr(location, "column", None)
    if not file_val:
        file_val = fallback_file
    if not file_val or line is None or column is None:
        return None
    return (
        _relativize_path(str(file_val), workspace_root),
        int(line),
        int(column),
    )


def _iter_value_locations(values: list[str], locations: list) -> Iterable[tuple[str, object]]:
    if not values or not locations:
        return []
    limit = min(len(values), len(locations))
    return [(values[idx], locations[idx]) for idx in range(limit)]



def _select_code_location_values(
    field_name,
    locs,
    item,
    extra_fields,
    normalized_code,
    code_fields: set[str],
    chain_fields: set[str],
):
    field_key = str(field_name).lower()
    if field_key not in {"code", "codes"}:
        values = [str(v) for v in _iter_string_values(extra_fields.get(field_name))]
        return field_name, values

    candidates: list[tuple[str, list[str]]] = []

    codes_list = [str(v) for v in (getattr(item, "codes", None) or [])]
    if codes_list:
        candidates.append((field_name, codes_list))

    candidate_fields = set(code_fields or set()) - set(chain_fields or set())
    for name, value in extra_fields.items():
        if candidate_fields and name not in candidate_fields:
            continue
        values = [str(v) for v in _iter_string_values(value)]
        if values:
            candidates.append((name, values))

    matched = [(name, values) for name, values in candidates if len(values) == len(locs)]
    if matched:
        if normalized_code:
            for name, values in matched:
                if any(_normalize_code(val) == normalized_code for val in values):
                    return name, values
        for name, values in matched:
            if str(name).lower() in {"code", "codes"}:
                return name, values
        return matched[0]

    return field_name, []


def _iter_chain_code_locations(chain, has_relations: bool) -> list[tuple[str, object]]:
    nodes = getattr(chain, "nodes", None) or []
    locations = getattr(chain, "node_locations", None) or []
    if not nodes or not locations or len(nodes) != len(locations):
        return []
    if has_relations and len(nodes) >= 3 and len(nodes) % 2 == 1:
        indices = range(0, len(nodes), 2)
    else:
        indices = range(len(nodes))
    return [(nodes[idx], locations[idx]) for idx in indices]


def _append_precise_occurrences(
    occurrences: list[dict],
    seen: set[tuple],
    normalized_code: str,
    item,
    field_specs: dict,
    workspace_root: Optional[Path],
    code_fields: set[str],
    chain_fields: set[str],
    chain_relations: dict[str, bool],
) -> tuple[bool, bool]:
    """
    Append precise occurrences from compiler-provided locations.

    Returns:
        tuple[bool, bool]: (found_any, found_code_precise)
            - found_any: True if any occurrence was found (even if already in seen)
            - found_code_precise: True if a precise CODE occurrence was found
    """
    found_any = False
    found_code_precise = False
    item_loc = _get_item_location(item)
    fallback_file = getattr(item_loc, "file", None) if item_loc else None

    code_locations = getattr(item, "code_locations", None) or {}
    extra_fields = getattr(item, "extra_fields", {}) or {}

    for field_name, locs in code_locations.items():
        value_field, values = _select_code_location_values(
            field_name,
            locs,
            item,
            extra_fields,
            normalized_code,
            code_fields,
            chain_fields,
        )
        if not values:
            continue
        for value, loc in _iter_value_locations(values, locs):
            if _normalize_code(value) != normalized_code:
                continue
            loc_info = _location_to_occurrence(loc, workspace_root, fallback_file)
            if not loc_info:
                continue
            file_rel, line, column = loc_info
            key = (file_rel, line, column, value_field, "code")
            if key in seen:
                found_any = True
                found_code_precise = True
                continue
            seen.add(key)
            occurrences.append(
                {
                    "file": file_rel,
                    "line": line,
                    "column": column,
                    "context": "code",
                    "field": value_field,
                }
            )
            found_any = True
            found_code_precise = True

    for chain in getattr(item, "chains", None) or []:
        field_name = (
            getattr(chain, "field_name", None)
            or getattr(chain, "field", None)
            or "chain"
        )
        has_relations = chain_relations.get(str(field_name).lower(), False)
        for value, loc in _iter_chain_code_locations(chain, has_relations):
            if _normalize_code(value) != normalized_code:
                continue
            loc_info = _location_to_occurrence(loc, workspace_root, fallback_file)
            if not loc_info:
                continue
            file_rel, line, column = loc_info
            key = (file_rel, line, column, field_name, "chain")
            if key in seen:
                found_any = True
                continue
            seen.add(key)
            occurrences.append(
                {
                    "file": file_rel,
                    "line": line,
                    "column": column,
                    "context": "chain",
                    "field": field_name,
                }
            )
            found_any = True

    for field_name, value in extra_fields.items():
        spec = field_specs.get(field_name) if field_specs else None
        has_relations = bool(getattr(spec, "relations", None))
        for chain in _iter_chain_values(value):
            for chain_value, loc in _iter_chain_code_locations(chain, has_relations):
                if _normalize_code(chain_value) != normalized_code:
                    continue
                loc_info = _location_to_occurrence(loc, workspace_root, fallback_file)
                if not loc_info:
                    continue
                file_rel, line, column = loc_info
                key = (file_rel, line, column, field_name, "chain")
                if key in seen:
                    found_any = True
                    continue
                seen.add(key)
                occurrences.append(
                    {
                        "file": file_rel,
                        "line": line,
                        "column": column,
                        "context": "chain",
                        "field": field_name,
                    }
                )
                found_any = True

    return found_any, found_code_precise


def _build_code_occurrences(
    code,
    items,
    field_specs,
    workspace_root: Optional[Path],
    source_text=None,
    *,
    code_fields: Optional[set[str]] = None,
    chain_fields: Optional[set[str]] = None,
    chain_relations: Optional[dict[str, bool]] = None,
) -> list[dict]:
    occurrences: list[dict] = []
    seen: set[tuple] = set()
    normalized_code = _normalize_code(code)

    if code_fields is None or chain_fields is None or chain_relations is None:
        code_fields, chain_fields, chain_relations = _item_field_maps(field_specs or {})

    for item in items:
        item_loc = _get_item_location(item)
        if not item_loc:
            continue
        file_val = getattr(item_loc, "file", None)
        if not file_val:
            continue
        file_path = _relativize_path(str(file_val), workspace_root)
        line = getattr(item_loc, "line", None)
        column = getattr(item_loc, "column", None)
        if line is None or column is None:
            continue

        # Prefer exact positions from compiler-provided locations
        found_any, _found_code_precise = _append_precise_occurrences(
            occurrences,
            seen,
            normalized_code,
            item,
            field_specs,
            workspace_root,
            code_fields,
            chain_fields,
            chain_relations,
        )
        if found_any:
            continue

        # Coarse fallback (no regex): item/chain locations only
        item_label = (
            getattr(item, "bibref", None)
            or getattr(item, "name", None)
            or getattr(item, "id", None)
            or "unknown-item"
        )
        logger.info(
            "getCodes fallback to item location (code=%s, item=%s, file=%s, line=%s, column=%s)",
            code,
            item_label,
            file_path,
            line,
            column,
        )
        extra_fields = getattr(item, "extra_fields", {}) or {}
        for field_name, value in extra_fields.items():
            spec = field_specs.get(field_name) if field_specs else None
            is_chain_field = _is_chain_field(spec)

            if is_chain_field:
                if not _chain_value_contains_code(value, code, spec):
                    continue
                for candidate in _iter_chain_values(value):
                    chain_codes = _extract_chain_codes(candidate, spec)
                    if not any(_normalize_code(c) == normalized_code for c in chain_codes):
                        continue
                    chain_loc = getattr(candidate, "location", None)
                    occ_line = getattr(chain_loc, "line", line) if chain_loc else line
                    occ_column = getattr(chain_loc, "column", column) if chain_loc else column
                    key = (file_path, occ_line, occ_column, field_name, "chain")
                    if key not in seen:
                        seen.add(key)
                        occurrences.append({
                            "file": file_path,
                            "line": occ_line,
                            "column": occ_column,
                            "context": "chain",
                            "field": field_name,
                        })
                continue

            if not _value_contains_code(value, code):
                continue

            key = (file_path, line, column, field_name, "code")
            if key not in seen:
                seen.add(key)
                occurrences.append({
                    "file": file_path,
                    "line": line,
                    "column": column,
                    "context": "code",
                    "field": field_name,
                })

        chains = getattr(item, "chains", None) or []
        chain_spec = field_specs.get("chain") if field_specs else None
        for chain in chains:
            chain_codes = _extract_chain_codes(chain, chain_spec)
            if not chain_codes:
                continue
            if any(_normalize_code(c) == normalized_code for c in chain_codes):
                field_name = (
                    getattr(chain, "field_name", None)
                    or getattr(chain, "field", None)
                    or "CHAIN"
                )
                chain_loc = getattr(chain, "location", None)
                occ_line = getattr(chain_loc, "line", line) if chain_loc else line
                occ_column = getattr(chain_loc, "column", column) if chain_loc else column
                key = (file_path, occ_line, occ_column, field_name, "chain")
                if key not in seen:
                    seen.add(key)
                    occurrences.append({
                        "file": file_path,
                        "line": occ_line,
                        "column": occ_column,
                        "context": "chain",
                        "field": field_name,
                    })

        codes_list = getattr(item, "codes", None) or []
        if any(_normalize_code(c) == normalized_code for c in codes_list):
            key = (file_path, line, column, "CODE", "code")
            if key not in seen:
                seen.add(key)
                occurrences.append({
                    "file": file_path,
                    "line": line,
                    "column": column,
                    "context": "code",
                    "field": "CODE",
                })

    return occurrences


def _filter_occurrences_by_template(
    occurrences: list[dict],
    *,
    include_code: bool,
    include_chain: bool,
) -> list[dict]:
    if include_code and include_chain:
        return occurrences
    if not include_code and not include_chain:
        return []
    filtered = []
    for occ in occurrences:
        context = (occ or {}).get("context")
        if context == "code" and include_code:
            filtered.append(occ)
        elif context == "chain" and include_chain:
            filtered.append(occ)
    return filtered




def _dedupe_occurrences(occurrences: list[dict]) -> list[dict]:
    """
    Remove exact duplicates based on file/line/column/context/field.

    This prevents duplicates that may arise from multiple compilation phases
    (transformer + linker) both populating code_locations.  Field names are
    normalized to lowercase so that "CODE" and "code" are treated as the same.
    """
    if not occurrences:
        return []

    seen: set[tuple] = set()
    result: list[dict] = []
    for occ in occurrences:
        if not occ:
            continue
        key = (
            occ.get("file"),
            occ.get("line"),
            occ.get("column"),
            occ.get("context"),
            (occ.get("field") or "").lower(),
        )
        if key not in seen:
            seen.add(key)
            result.append(occ)

    return result


def _extract_chain_triple(chain) -> Optional[tuple[str, str, str]]:
    if isinstance(chain, (list, tuple)) and len(chain) >= 3:
        subj, rel, obj = chain[0], chain[1], chain[2]
        if isinstance(subj, str) and isinstance(rel, str) and isinstance(obj, str):
            return subj, rel, obj

    nodes = getattr(chain, "nodes", None)
    if isinstance(nodes, (list, tuple)) and len(nodes) >= 3:
        subj, rel, obj = nodes[0], nodes[1], nodes[2]
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


def _extract_chain_type(chain) -> Optional[str]:
    """
    Detect chain type: "qualified" or "simple".

    Qualified: has explicit type attribute or "::" separator
    Simple: plain triple without type
    """
    # Check for explicit type attribute (means qualified)
    for key in ("type", "chain_type", "kind", "label"):
        value = None
        if isinstance(chain, dict):
            value = chain.get(key)
        else:
            value = getattr(chain, key, None)
        if value:
            return "qualified"

    # Check string format for "::" separator (means qualified)
    chain_str = _chain_to_string(chain)
    if chain_str and "::" in chain_str:
        return "qualified"

    # Default: simple chain
    return "simple"


def _chain_to_string(chain) -> Optional[str]:
    """Convert chain to string representation for format detection."""
    if isinstance(chain, str):
        return chain

    if isinstance(chain, dict):
        # Try to reconstruct string from components
        type_prefix = chain.get("type", "")
        if "from" in chain and "relation" in chain and "to" in chain:
            from_code = chain["from"]
            relation = chain["relation"]
            to_code = chain["to"]
            if type_prefix:
                return f"{type_prefix}::{from_code}-{relation}-{to_code}"
            return f"{from_code}-{relation}-{to_code}"

    # Try object __str__ method
    str_method = getattr(chain, "__str__", None)
    if str_method and callable(str_method):
        try:
            return str_method()
        except Exception:
            pass

    return None


def _location_dict(location, workspace_root: Optional[Path]) -> Optional[dict]:
    if not location:
        return None
    if isinstance(location, dict):
        file_val = location.get("file")
        line = location.get("line")
        column = location.get("column")
    else:
        file_val = getattr(location, "file", None)
        line = getattr(location, "line", None)
        column = getattr(location, "column", None)
    if not file_val or line is None or column is None:
        return None
    return {
        "file": _relativize_path(str(file_val), workspace_root),
        "line": line,
        "column": column,
    }


def _build_relation_index(lp, workspace_root: Optional[Path]) -> dict:
    index: dict[tuple[str, str, str], dict] = {}
    sources = getattr(lp, "sources", {}) or {}
    for src in _iter_sources(sources):
        for item in getattr(src, "items", []) or []:
            for chain in getattr(item, "chains", None) or []:
                _index_chain(index, chain, item, workspace_root)

    # Fallback 1: merge explicit relation index mappings, se existirem
    _merge_relation_index_from_mapping(index, lp, workspace_root)

    # Fallback: busca chains em outros índices, se disponíveis
    for chain in _iter_lp_chains(lp):
        _index_chain(index, chain, None, workspace_root)
    return index


def _merge_relation_index_from_mapping(index: dict, lp, workspace_root: Optional[Path]) -> None:
    for attr_name in (
        "relation_index",
        "relations_index",
        "relation_locations",
        "relation_location_index",
        "triple_index",
    ):
        mapping = getattr(lp, attr_name, None)
        if not isinstance(mapping, dict):
            continue

        for raw_key, value in mapping.items():
            if not isinstance(raw_key, (list, tuple)) or len(raw_key) < 3:
                continue
            subj, rel, obj = raw_key[0], raw_key[1], raw_key[2]
            if not all(isinstance(v, str) for v in (subj, rel, obj)):
                continue

            key = _normalize_triple(subj, rel, obj)
            if key in index:
                continue

            entry = {}

            # Try to extract location from value
            loc = None
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                loc = _location_dict(value[3], workspace_root)
            if not loc and isinstance(value, dict) and "location" in value:
                loc = _location_dict(value.get("location"), workspace_root)
            if not loc:
                loc = _location_dict(value, workspace_root)

            if loc:
                entry["location"] = loc

            # Try to extract type if available
            chain_type = _extract_chain_type(value)
            if chain_type:
                entry["type"] = chain_type

            if entry:
                index[key] = entry


def _iter_lp_chains(lp) -> Iterable:
    for attr_name in (
        "chains",
        "all_chains",
        "chain_index",
        "relation_index",
        "relations",
        "relation_triples",
    ):
        value = getattr(lp, attr_name, None)
        if value is None:
            continue
        yield from _flatten_values(value)


def _flatten_values(value, _seen=None) -> Iterable:
    if _seen is None:
        _seen = set()
    obj_id = id(value)
    if obj_id in _seen:
        return
    _seen.add(obj_id)

    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_values(item, _seen)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _flatten_values(item, _seen)
        return
    yield value


def _index_chain(index: dict, chain, item, workspace_root: Optional[Path]) -> None:
    """
    Index chain with improved location and type extraction.

    Location priority: tuple[3] → chain.location → dict["location"] → item.location
    Type: qualified (has type or "::") or simple
    """
    triple = _extract_chain_triple(chain)
    if not triple:
        return
    key = _normalize_triple(*triple)
    if key in index:
        return  # Don't overwrite existing (first occurrence wins)

    entry = {}

    # === Extract Location (priority order) ===
    loc = None

    # Priority 1: Check tuple[3] (chain location in tuple format)
    if isinstance(chain, (list, tuple)) and len(chain) >= 4:
        loc = _location_dict(chain[3], workspace_root)

    # Priority 2: Check chain.location attribute
    if not loc:
        chain_loc = getattr(chain, "location", None)
        if chain_loc:
            loc = _location_dict(chain_loc, workspace_root)

    # Priority 3: Check dict["location"]
    if not loc and isinstance(chain, dict) and "location" in chain:
        loc = _location_dict(chain["location"], workspace_root)

    # Priority 4: Use item location as fallback
    if not loc and item is not None:
        item_loc = getattr(item, "location", None)
        if not item_loc or not getattr(item_loc, "file", None):
            source = getattr(item, "source", None)
            item_loc = getattr(source, "location", None) if source else item_loc
        if item_loc:
            loc = _location_dict(item_loc, workspace_root)

    if loc:
        entry["location"] = loc

    # === Extract Type ===
    chain_type = _extract_chain_type(chain)
    if chain_type:
        entry["type"] = chain_type

    # Only add to index if we have at least one piece of info
    if entry:
        index[key] = entry
