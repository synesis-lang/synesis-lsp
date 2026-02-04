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
    file_cache: dict[str, list[str]] = {}
    item_occ_cache: dict[tuple[str, int], dict[str, list[dict]]] = {}

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

    for code, items in (code_usage or {}).items():
        occurrences = _build_code_occurrences(
            code,
            items,
            field_specs,
            workspace_root,
            file_cache=file_cache,
            item_occ_cache=item_occ_cache,
            code_fields=code_fields,
            chain_fields=chain_fields,
            chain_relations=chain_relations,
        )
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
    if _is_chain_field(spec):
        return True
    spec_type = getattr(spec, "type", None)
    type_name = getattr(spec_type, "name", None) or str(spec_type or "")
    return "CODE" in type_name.upper()


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
    chain_spec = field_specs.get("chain") if field_specs else None
    for chain in chains:
        for chain_code in _extract_chain_codes(chain, chain_spec):
            if isinstance(chain_code, str) and chain_code.strip():
                yield chain_code

    extra_fields = getattr(item, "extra_fields", {}) or {}
    for field_name, value in extra_fields.items():
        spec = field_specs.get(field_name) if field_specs else None
        if _is_chain_field(spec):
            for candidate in _iter_chain_values(value):
                for chain_code in _extract_chain_codes(candidate, spec):
                    if isinstance(chain_code, str) and chain_code.strip():
                        yield chain_code
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


def _build_code_occurrences(
    code,
    items,
    field_specs,
    workspace_root: Optional[Path],
    source_text=None,
    *,
    file_cache: Optional[dict[str, list[str]]] = None,
    item_occ_cache: Optional[dict[tuple[str, int], dict[str, list[dict]]]] = None,
    code_fields: Optional[set[str]] = None,
    chain_fields: Optional[set[str]] = None,
    chain_relations: Optional[dict[str, bool]] = None,
) -> list[dict]:
    occurrences: list[dict] = []
    seen: set[tuple] = set()
    normalized_code = _normalize_code(code)

    file_cache = file_cache or {}
    item_occ_cache = item_occ_cache or {}
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

        # Prefer exact positions from raw source text (CODE/CHAIN fields)
        found_text = False
        text_occurrences = _get_item_text_occurrences(
            item,
            workspace_root,
            file_cache,
            item_occ_cache,
            code_fields,
            chain_fields,
            chain_relations,
        )
        if text_occurrences:
            for occ in text_occurrences.get(normalized_code, []):
                key = (occ["file"], occ["line"], occ["column"], occ["field"], occ["context"])
                if key not in seen:
                    seen.add(key)
                    occurrences.append(occ)
                    found_text = True
        if found_text:
            continue

        # Search in extra_fields with exact positioning (compiler-driven fallback)
        extra_fields = getattr(item, "extra_fields", {}) or {}
        for field_name, value in extra_fields.items():
            spec = field_specs.get(field_name) if field_specs else None
            is_chain_field = _is_chain_field(spec)

            if is_chain_field:
                if not _chain_value_contains_code(value, code, spec):
                    continue

                field_loc = _extract_field_location(item, field_name, source_text)
                for candidate in _iter_chain_values(value):
                    chain_codes = _extract_chain_codes(candidate, spec)
                    if not any(_normalize_code(c) == normalized_code for c in chain_codes):
                        continue

                    chain_loc = getattr(candidate, "location", None)
                    if chain_loc:
                        occ_line = getattr(chain_loc, "line", line)
                        occ_column = getattr(chain_loc, "column", column)
                    elif field_loc:
                        occ_line, occ_column = field_loc
                    else:
                        occ_line, occ_column = line, column

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

            context = "code"

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
        chain_spec = field_specs.get("chain") if field_specs else None
        for chain in chains:
            chain_codes = _extract_chain_codes(chain, chain_spec)
            if not chain_codes:
                continue

            # Check if code matches subject or object
            if any(_normalize_code(c) == normalized_code for c in chain_codes):
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


def _resolve_file_for_read(file_val: str, workspace_root: Optional[Path]) -> Optional[Path]:
    path = _normalize_file_path(file_val)
    if not path:
        return None
    if path.is_absolute():
        return path
    if workspace_root:
        return workspace_root / path
    return path


def _strip_comment(text: str) -> str:
    idx = text.find("#")
    return text if idx < 0 else text[:idx]


def _split_with_offsets(text: str, delimiter: str) -> list[tuple[str, int]]:
    segments: list[tuple[str, int]] = []
    start = 0
    while True:
        idx = text.find(delimiter, start)
        if idx == -1:
            segments.append((text[start:], start))
            break
        segments.append((text[start:idx], start))
        start = idx + len(delimiter)
    return segments


def _iter_code_tokens(value_text: str, base_offset: int) -> list[tuple[str, int]]:
    text = _strip_comment(value_text)
    tokens: list[tuple[str, int]] = []
    start = 0
    while start <= len(text):
        comma_idx = text.find(",", start)
        if comma_idx == -1:
            segment = text[start:]
            segment_start = start
        else:
            segment = text[start:comma_idx]
            segment_start = start

        token_text = segment.strip()
        if token_text:
            leading_ws = len(segment) - len(segment.lstrip())
            token_start = segment_start + leading_ws
            tokens.append((token_text, base_offset + token_start))

        if comma_idx == -1:
            break
        start = comma_idx + 1

    return tokens


def _segment_to_token(segment: str, segment_start: int) -> Optional[tuple[str, int]]:
    leading_ws = len(segment) - len(segment.lstrip())
    trimmed = segment.strip()
    if not trimmed:
        return None

    token_text = trimmed
    token_start = leading_ws

    if "::" in trimmed:
        idx = trimmed.rfind("::") + 2
        while idx < len(trimmed) and trimmed[idx].isspace():
            idx += 1
        if idx < len(trimmed):
            token_text = trimmed[idx:].strip()
            token_start = leading_ws + idx

    return (token_text, segment_start + token_start)


def _iter_chain_tokens(value_text: str, base_offset: int, has_relations: bool) -> list[tuple[str, int]]:
    text = _strip_comment(value_text)
    segments = _split_with_offsets(text, "->")
    nodes: list[tuple[str, int]] = []
    for segment, segment_start in segments:
        token = _segment_to_token(segment, segment_start)
        if token:
            nodes.append(token)

    if not nodes:
        return []

    if has_relations and len(nodes) >= 3 and len(nodes) % 2 == 1:
        nodes = nodes[::2]

    return [(token, base_offset + start) for token, start in nodes]


def _record_value_occurrences(
    occurrences: dict[str, list[dict]],
    value_text: str,
    base_offset: int,
    line_idx: int,
    file_rel: str,
    field_name: str,
    is_chain: bool,
    has_relations: bool,
) -> None:
    context = "chain" if is_chain else "code"
    if is_chain:
        tokens = _iter_chain_tokens(value_text, base_offset, has_relations)
    else:
        tokens = _iter_code_tokens(value_text, base_offset)

    for token_text, start_idx in tokens:
        code_key = _normalize_code(token_text)
        if not code_key:
            continue
        occurrences.setdefault(code_key, []).append(
            {
                "file": file_rel,
                "line": line_idx + 1,
                "column": start_idx + 1,
                "context": context,
                "field": field_name,
            }
        )


def _parse_item_block_occurrences(
    lines: list[str],
    start_idx: int,
    code_fields: set[str],
    chain_fields: set[str],
    chain_relations: dict[str, bool],
    file_rel: str,
) -> dict[str, list[dict]]:
    occurrences: dict[str, list[dict]] = {}
    if start_idx < 0 or start_idx >= len(lines):
        return occurrences

    item_line = lines[start_idx]
    item_indent = len(item_line) - len(item_line.lstrip(" \t"))

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if stripped.upper().startswith("END ITEM") and indent <= item_indent:
            end_idx = idx
            break

    current_field: Optional[str] = None
    current_field_indent: Optional[int] = None
    current_field_is_chain = False
    current_field_has_relations = False

    for idx in range(start_idx + 1, end_idx):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip(" \t"))

        if current_field and indent <= (current_field_indent or 0) and not stripped.startswith("#"):
            current_field = None
            current_field_indent = None
            current_field_is_chain = False
            current_field_has_relations = False

        if stripped.startswith("#"):
            continue

        field_match = re.match(r"^(\s*)([\w._-]+)\s*:\s*(.*)$", line)
        if field_match:
            field_name = field_match.group(2)
            field_key = field_name.lower()
            current_field_indent = len(field_match.group(1))

            if field_key in chain_fields:
                current_field = field_name
                current_field_is_chain = True
                current_field_has_relations = chain_relations.get(field_key, False)
            elif field_key in code_fields:
                current_field = field_name
                current_field_is_chain = False
                current_field_has_relations = False
            else:
                current_field = None
                current_field_indent = None
                current_field_is_chain = False
                current_field_has_relations = False

            if current_field:
                value_text = field_match.group(3)
                if value_text.strip():
                    _record_value_occurrences(
                        occurrences,
                        value_text,
                        field_match.start(3),
                        idx,
                        file_rel,
                        current_field,
                        current_field_is_chain,
                        current_field_has_relations,
                    )
            continue

        if not current_field:
            continue

        if indent <= (current_field_indent or 0):
            current_field = None
            current_field_indent = None
            current_field_is_chain = False
            current_field_has_relations = False
            continue

        _record_value_occurrences(
            occurrences,
            line,
            0,
            idx,
            file_rel,
            current_field,
            current_field_is_chain,
            current_field_has_relations,
        )

    return occurrences


def _get_item_text_occurrences(
    item,
    workspace_root: Optional[Path],
    file_cache: dict[str, list[str]],
    item_occ_cache: dict[tuple[str, int], dict[str, list[dict]]],
    code_fields: set[str],
    chain_fields: set[str],
    chain_relations: dict[str, bool],
) -> Optional[dict[str, list[dict]]]:
    item_loc = _get_item_location(item)
    if not item_loc:
        return None
    file_val = getattr(item_loc, "file", None)
    line = getattr(item_loc, "line", None)
    if not file_val or line is None:
        return None

    file_path = _resolve_file_for_read(str(file_val), workspace_root)
    if not file_path:
        return None

    cache_key = (str(file_path), int(line))
    if cache_key in item_occ_cache:
        return item_occ_cache[cache_key]

    lines = file_cache.get(str(file_path))
    if lines is None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            item_occ_cache[cache_key] = {}
            return item_occ_cache[cache_key]
        lines = content.splitlines()
        file_cache[str(file_path)] = lines

    file_rel = _relativize_path(str(file_val), workspace_root)
    occurrences = _parse_item_block_occurrences(
        lines,
        int(line) - 1,
        code_fields,
        chain_fields,
        chain_relations,
        file_rel,
    )
    item_occ_cache[cache_key] = occurrences
    return occurrences


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
