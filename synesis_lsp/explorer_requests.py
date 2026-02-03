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

    codes = []
    code_usage = _get_code_usage(lp, field_specs)
    for code, items in (code_usage or {}).items():
        occurrences = _build_code_occurrences(
            code,
            items,
            field_specs,
            workspace_root,
        )
        codes.append(
            {
                "code": code,
                "usageCount": len(items),
                "ontologyDefined": code in lp.ontology_index,
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
    if _is_chain_field(spec):
        return True
    spec_type = getattr(spec, "type", None)
    type_name = getattr(spec_type, "name", None) or str(spec_type or "")
    return "CODE" in type_name.upper()


def _get_code_usage(lp, field_specs) -> dict:
    for attr_name in (
        "code_usage",
        "code_usage_index",
        "code_usage_by_code",
        "code_usage_map",
    ):
        value = getattr(lp, attr_name, None)
        if value and hasattr(value, "items"):
            return value
    return _build_code_usage_from_sources(lp, field_specs)


def _build_code_usage_from_sources(lp, field_specs) -> dict:
    usage: dict[str, list] = {}
    sources = getattr(lp, "sources", {}) or {}
    for src in _iter_sources(sources):
        for item in getattr(src, "items", []) or []:
            for code in _iter_codes_from_item(item, field_specs):
                usage.setdefault(code, []).append(item)
    return usage


def _iter_codes_from_item(item, field_specs) -> Iterable[str]:
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
    for field_name, value in extra_fields.items():
        spec = field_specs.get(field_name) if field_specs else None
        if _is_chain_field(spec):
            for candidate in _iter_chain_values(value):
                triple = _extract_chain_triple(candidate)
                if not triple:
                    continue
                subj, _rel, obj = triple
                if isinstance(subj, str) and subj.strip():
                    yield subj
                if isinstance(obj, str) and obj.strip():
                    yield obj
            continue
        if not _is_code_field(spec):
            continue
        for code in _iter_string_values(value):
            if isinstance(code, str) and code.strip():
                yield code


def _stringify_value(value) -> str:
    """
    Convert field value to string for token searching.

    Handles: strings, lists, dicts, tuples.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ' '.join(str(v) for v in value)
    if isinstance(value, dict):
        return ' '.join(str(v) for v in value.values())
    return str(value)


def _extract_field_location(item, field_name, source_text=None) -> Optional[tuple[int, int]]:
    """
    Extract the line/column where a field's value starts within an item.

    Strategy:
        1. Check if item has field_locations dict/attribute
        2. Check if field object has location attribute
        3. Fallback: use item.location (existing behavior)
    """
    # Strategy 1: Check item.field_locations
    field_locations = getattr(item, 'field_locations', None)
    if field_locations and field_name in field_locations:
        loc = field_locations[field_name]
        return (loc.line, loc.column)

    # Strategy 2: Check field object location
    extra_fields = getattr(item, 'extra_fields', {})
    if field_name in extra_fields:
        field_obj = extra_fields[field_name]
        loc = getattr(field_obj, 'location', None)
        if loc:
            return (loc.line, loc.column)

    # Strategy 3: Check codes/chains lists for location
    if field_name == "CODE":
        codes = getattr(item, 'codes', [])
        if codes:
            loc = getattr(codes, 'location', None)
            if loc:
                return (loc.line, loc.column)

    if field_name == "CHAIN" or _is_chain_field_name(field_name):
        chains = getattr(item, 'chains', [])
        if chains and len(chains) > 0:
            loc = getattr(chains[0], 'location', None)
            if loc:
                return (loc.line, loc.column)

    # Fallback: use item location
    item_loc = getattr(item, 'location', None)
    if item_loc:
        return (item_loc.line, item_loc.column)

    return None


def _is_chain_field_name(field_name: str) -> bool:
    """Check if field name suggests it's a chain field."""
    return "CHAIN" in field_name.upper()


def _find_code_in_field_value(
    field_value: str,
    code: str,
    field_start_line: int,
    field_start_column: int
) -> list[tuple[int, int]]:
    """
    Find exact positions of code within field value.

    Args:
        field_value: The field value text (possibly multiline)
        code: The code to search for (normalized comparison)
        field_start_line: 1-based line number where field starts
        field_start_column: 1-based column where field value starts

    Returns:
        List of (line, column) tuples (1-based) for each occurrence.
        Empty list if code not found.
    """
    import re

    normalized_code = _normalize_code(code)
    positions = []

    # Handle multiline values
    lines = field_value.split('\n')

    for line_offset, line_text in enumerate(lines):
        # Calculate absolute line number
        abs_line = field_start_line + line_offset

        # Tokenize by word boundaries
        for match in re.finditer(r'\b\w+\b', line_text):
            if _normalize_code(match.group(0)) == normalized_code:
                # Calculate column:
                # - First line: relative to field_start_column
                # - Other lines: relative to line start (column 1)
                if line_offset == 0:
                    abs_column = field_start_column + match.start()
                else:
                    abs_column = match.start() + 1  # 1-based

                positions.append((abs_line, abs_column))

    return positions


def _build_code_occurrences(code, items, field_specs, workspace_root: Optional[Path], source_text=None) -> list[dict]:
    occurrences: list[dict] = []
    seen: set[tuple] = set()
    normalized_code = _normalize_code(code)

    for item in items:
        item_loc = getattr(item, "location", None)
        if not item_loc:
            continue
        file_path = _relativize_path(str(item_loc.file), workspace_root)
        line = getattr(item_loc, "line", None)
        column = getattr(item_loc, "column", None)
        if line is None or column is None:
            continue

        # Search in extra_fields with exact positioning
        extra_fields = getattr(item, "extra_fields", {}) or {}
        for field_name, value in extra_fields.items():
            if not _value_contains_code(value, code):
                continue

            spec = field_specs.get(field_name) if field_specs else None
            context = "chain" if _is_chain_field(spec) else "code"

            # Try to get exact field location
            field_loc = _extract_field_location(item, field_name, source_text)
            if field_loc:
                field_line, field_column = field_loc
                field_value_str = _stringify_value(value)

                # Find exact token positions within field value
                positions = _find_code_in_field_value(
                    field_value_str, code, field_line, field_column
                )

                for pos_line, pos_column in positions:
                    key = (file_path, pos_line, pos_column, field_name, context)
                    if key not in seen:
                        seen.add(key)
                        occurrences.append({
                            "file": file_path,
                            "line": pos_line,
                            "column": pos_column,
                            "context": context,
                            "field": field_name,
                        })
            else:
                # Fallback to item location if field location unavailable
                key = (file_path, line, column, field_name, context)
                if key not in seen:
                    seen.add(key)
                    occurrences.append({
                        "file": file_path,
                        "line": line,
                        "column": column,
                        "context": context,
                        "field": field_name,
                    })

        # Search in chains with exact positioning
        chains = getattr(item, "chains", None) or []
        for chain in chains:
            triple = _extract_chain_triple(chain)
            if not triple:
                continue
            subj, rel, obj = triple

            # Check if code matches subject or object
            if _normalize_code(subj) == normalized_code or _normalize_code(obj) == normalized_code:
                field_name = (
                    getattr(chain, "field_name", None)
                    or getattr(chain, "field", None)
                    or "CHAIN"
                )

                # Try to extract chain location
                chain_loc = getattr(chain, 'location', None)
                if chain_loc:
                    chain_line = getattr(chain_loc, 'line', line)
                    chain_column = getattr(chain_loc, 'column', column)
                else:
                    chain_line = line
                    chain_column = column

                key = (file_path, chain_line, chain_column, field_name, "chain")
                if key not in seen:
                    seen.add(key)
                    occurrences.append({
                        "file": file_path,
                        "line": chain_line,
                        "column": chain_column,
                        "context": "chain",
                        "field": field_name,
                    })

        # Fallback: Search in codes list if not found in extra_fields or chains
        codes_list = getattr(item, "codes", None) or []
        if any(_normalize_code(c) == normalized_code for c in codes_list):
            # Check if already covered by extra_fields
            already_covered = any(
                occ["file"] == file_path and
                occ["field"] in ["CODE", "CODES"] and
                (occ["line"], occ["column"]) != (line, column)
                for occ in occurrences
            )

            if not already_covered:
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

    # Fallback: busca chains em outros índices, se disponíveis
    for chain in _iter_lp_chains(lp):
        _index_chain(index, chain, None, workspace_root)
    return index


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
