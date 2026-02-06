"""
ontology_annotations.py - Cruzamento de ontologia com anotações

Propósito:
    Encontrar todas as ocorrências de conceitos da ontologia
    nos arquivos de anotação.

Custom Request:
    synesis/getOntologyAnnotations → Lista de annotations por conceito
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

_ANNOTATIONS_CACHE: dict[tuple[str, float], dict] = {}
_ANNOTATIONS_CACHE_MAX = 4


def _normalize_code(value: str) -> str:
    return " ".join(str(value).strip().split()).lower()


def _iter_string_values(value):
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


def _iter_chain_values(value):
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield item
        return
    if isinstance(value, dict):
        for item in value.values():
            yield item
        return
    yield value


def _iter_value_locations(values, locations):
    if not values or not locations:
        return []
    limit = min(len(values), len(locations))
    return [(values[idx], locations[idx]) for idx in range(limit)]



def _select_code_location_values(field_name, locs, item, extra_fields, target):
    field_key = str(field_name).lower()
    if field_key not in {"code", "codes"}:
        values = [str(v) for v in _iter_string_values(extra_fields.get(field_name))]
        return field_name, values

    candidates: list[tuple[str, list[str]]] = []

    codes_list = [str(v) for v in (getattr(item, "codes", None) or [])]
    if codes_list:
        candidates.append((field_name, codes_list))

    for name, value in extra_fields.items():
        values = [str(v) for v in _iter_string_values(value)]
        if values:
            candidates.append((name, values))

    matched = [(name, values) for name, values in candidates if len(values) == len(locs)]
    if matched:
        if target:
            for name, values in matched:
                if any(_normalize_code(val) == target for val in values):
                    return name, values
        for name, values in matched:
            if str(name).lower() in {"code", "codes"}:
                return name, values
        return matched[0]

    return field_name, []


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


def _iter_chain_code_locations(chain):
    nodes = getattr(chain, "nodes", None) or []
    locations = getattr(chain, "node_locations", None) or []
    if not nodes or not locations or len(nodes) != len(locations):
        return []
    return [(nodes[idx], locations[idx]) for idx in range(len(nodes))]


def _location_line_column(location):
    if not location:
        return (None, None)
    if isinstance(location, dict):
        return (location.get("line"), location.get("column"))
    return (getattr(location, "line", None), getattr(location, "column", None))


def _chain_contains_code(chain, code: str) -> bool:
    target = _normalize_code(code)
    if isinstance(chain, str) and _normalize_code(chain) == target:
        return True
    for node in _chain_nodes(chain):
        if _normalize_code(node) == target:
            return True
    return False


def _field_value_contains_code(value, code: str) -> bool:
    target = _normalize_code(code)
    for candidate in _iter_chain_values(value):
        if _chain_contains_code(candidate, target):
            return True
    for text in _iter_string_values(value):
        if _normalize_code(text) == target:
            return True
    return False


def _merge_code_usage_with_chains(lp, ontology_index=None) -> dict:
    base_usage = getattr(lp, "code_usage", {}) or {}
    usage: dict[str, list] = {}
    seen: dict[str, set[int]] = {}

    for code, items in base_usage.items():
        norm = _normalize_code(code)
        if not norm:
            continue
        usage[norm] = list(items) if items else []
        seen[norm] = {id(item) for item in usage[norm]}

    sources = getattr(lp, "sources", {}) or {}
    if isinstance(sources, dict):
        sources_iter = sources.values()
    elif isinstance(sources, (list, tuple, set)):
        sources_iter = sources
    else:
        sources_iter = []

    for src in sources_iter:
        for item in getattr(src, "items", []) or []:
            # Add codes found in chains (item.chains + chain-like extra fields)
            chains = getattr(item, "chains", None) or []
            for chain in chains:
                for node in _chain_nodes(chain):
                    if ontology_index is not None and _normalize_code(node) not in ontology_index:
                        continue
                    _add_item_to_usage(usage, seen, node, item)

            extra_fields = getattr(item, "extra_fields", {}) or {}
            for value in extra_fields.values():
                for candidate in _iter_chain_values(value):
                    nodes = _chain_nodes(candidate)
                    if not nodes:
                        continue
                    for node in nodes:
                        if ontology_index is not None and _normalize_code(node) not in ontology_index:
                            continue
                        _add_item_to_usage(usage, seen, node, item)

    return usage


def _add_item_to_usage(usage: dict, seen: dict, code: str, item) -> None:
    norm = _normalize_code(code)
    if not norm:
        return
    bucket = usage.setdefault(norm, [])
    bucket_seen = seen.setdefault(norm, set())
    item_id = id(item)
    if item_id in bucket_seen:
        return
    bucket_seen.add(item_id)
    bucket.append(item)


def _annotations_cache_key(cached_result, workspace_root: Optional[Path]) -> Optional[tuple[str, int, float]]:
    if not cached_result:
        return None
    root = workspace_root or getattr(cached_result, "workspace_root", None)
    root_key = str(root) if root else ""
    timestamp = getattr(cached_result, "timestamp", None)
    if timestamp is None:
        return None
    return (root_key, id(cached_result), float(timestamp))


def _annotations_cache_set(key: Optional[tuple[str, float]], value: dict) -> None:
    if not key:
        return
    _ANNOTATIONS_CACHE[key] = value
    if len(_ANNOTATIONS_CACHE) > _ANNOTATIONS_CACHE_MAX:
        oldest_key = next(iter(_ANNOTATIONS_CACHE))
        if oldest_key != key:
            _ANNOTATIONS_CACHE.pop(oldest_key, None)


def _normalize_path_value(value: str) -> str:
    if not value:
        return ""
    if value.startswith("file://"):
        parsed = urlparse(value)
        path_val = unquote(parsed.path or "")
        if parsed.netloc:
            path_val = f"//{parsed.netloc}{path_val}"
        if len(path_val) >= 3 and path_val[0] == "/" and path_val[2] == ":":
            path_val = path_val[1:]
        return Path(path_val).as_posix()
    return Path(value).as_posix()


def _file_matches(active_file: str, relative_file: str) -> bool:
    normalized_active = _normalize_path_value(active_file)
    normalized_relative = _normalize_path_value(relative_file)
    return (
        normalized_active in normalized_relative
        or normalized_relative in normalized_active
    )


def _filter_annotations_by_file(payload: dict, active_file: str) -> dict:
    if not payload or "annotations" not in payload:
        return payload

    filtered = []
    for annotation in payload.get("annotations", []):
        occurrences = annotation.get("occurrences", []) or []
        filtered_occurrences = [
            occ for occ in occurrences
            if occ.get("file") and _file_matches(active_file, occ["file"])
        ]

        new_entry = dict(annotation)
        new_entry["occurrences"] = filtered_occurrences
        filtered.append(new_entry)

    return {"success": True, "annotations": filtered}


def get_ontology_annotations(
    cached_result,
    workspace_root: Optional[Path] = None,
    active_file: Optional[str] = None
) -> dict:
    """
    Retorna anotações de ontologia com occurrences.

    Args:
        cached_result: CachedCompilation com LinkedProject
        workspace_root: Raiz do workspace para relativizar paths
        active_file: Se fornecido, filtra apenas occurrences desse arquivo

    Returns:
        {
            "success": bool,
            "annotations": [
                {
                    "code": str,
                    "ontologyDefined": bool,
                    "ontologyFile": str,
                    "ontologyLine": int,
                    "occurrences": [...]
                }
            ]
        }
    """
    if not cached_result:
        return {"success": False, "error": "Workspace não compilado"}

    result = getattr(cached_result, "result", None)
    if not result:
        return {"success": False, "error": "Resultado de compilação inválido"}

    lp = getattr(result, "linked_project", None)
    if not lp:
        return {"success": False, "error": "LinkedProject não disponível"}

    effective_root = workspace_root or getattr(cached_result, "workspace_root", None)
    cache_key = _annotations_cache_key(cached_result, effective_root)
    cached_payload = _ANNOTATIONS_CACHE.get(cache_key) if cache_key else None
    if cached_payload is not None:
        if active_file:
            return _filter_annotations_by_file(cached_payload, active_file)
        return cached_payload

    # Extrair dados da ontologia e code_usage
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    code_usage = _merge_code_usage_with_chains(lp, ontology_index)

    if not ontology_index:
        logger.debug("Ontology index vazio, retornando lista vazia")
        result = {"success": True, "annotations": []}
        _annotations_cache_set(cache_key, result)
        return _filter_annotations_by_file(result, active_file) if active_file else result

    # Para cada conceito da ontologia, buscar suas occurrences
    annotations = []

    for code, onto_node in ontology_index.items():
        # Informações da definição na ontologia
        onto_location = getattr(onto_node, "location", None)
        ontology_file = None
        ontology_line = None

        if onto_location:
            onto_file_path = getattr(onto_location, "file", None)
            if onto_file_path and effective_root:
                try:
                    ontology_file = str(Path(onto_file_path).relative_to(effective_root))
                except ValueError:
                    ontology_file = onto_file_path
            else:
                ontology_file = onto_file_path

            ontology_line = getattr(onto_location, "line", None)

        # Buscar occurrences deste code
        items = code_usage.get(code, [])

        # Construir occurrences com posição detalhada
        occurrences = _build_occurrences(
            code=code,
            items=items,
            workspace_root=effective_root,
            active_file=None
        )

        # Deduplicate occurrences (Phase 1 only - exact match)
        occurrences = _dedupe_occurrences(occurrences)

        # Adicionar annotation
        annotation = {
            "code": code,
            "ontologyDefined": True,
            "occurrences": occurrences
        }

        if ontology_file:
            annotation["ontologyFile"] = ontology_file
        if ontology_line:
            annotation["ontologyLine"] = ontology_line

        annotations.append(annotation)

    # Ordenar por code name
    annotations.sort(key=lambda a: a["code"])

    result = {"success": True, "annotations": annotations}
    _annotations_cache_set(cache_key, result)
    return _filter_annotations_by_file(result, active_file) if active_file else result


def _build_occurrences(
    code: str,
    items: list,
    workspace_root: Optional[Path],
    active_file: Optional[str]
) -> list[dict]:
    """
    Constrói lista de occurrences com posição detalhada.

    Args:
        code: Código a procurar
        items: Lista de items onde o código aparece
        workspace_root: Raiz do workspace para relativizar paths
        active_file: Se fornecido, filtra apenas esse arquivo

    Returns:
        Lista de occurrences com file, itemName, line, column, context, field
    """
    occurrences = []

    for item in items:
        # Extrair location do item (fallback para source.location)
        location = getattr(item, "location", None)
        if not location or not getattr(location, "file", None):
            source = getattr(item, "source", None)
            location = getattr(source, "location", None) if source else location
        if not location:
            continue

        file_path = getattr(location, "file", None)
        if not file_path:
            continue

        # Relativizar path
        relative_file = file_path
        if workspace_root:
            try:
                relative_file = str(Path(file_path).relative_to(workspace_root))
            except ValueError:
                pass

        # Filtrar por active_file se fornecido
        if active_file:
            # Normalizar paths para comparação
            normalized_active = Path(active_file).as_posix()
            normalized_relative = Path(relative_file).as_posix()

            if normalized_active not in normalized_relative and normalized_relative not in normalized_active:
                continue

        # Extrair nome do item
        item_name = getattr(item, "name", None) or getattr(item, "id", "unknown")

        # Procurar code nos campos do item
        item_occurrences = _find_code_in_item(code, item, relative_file, item_name)
        occurrences.extend(item_occurrences)

    return occurrences


def _find_code_in_item(
    code: str,
    item,
    file_path: str,
    item_name: str
) -> list[dict]:
    """
    Procura code em todos os campos do item e retorna occurrences.

    Args:
        code: Código a procurar
        item: Item onde procurar
        file_path: Path do arquivo (relativo)
        item_name: Nome do item

    Returns:
        Lista de occurrences encontradas neste item
    """
    occurrences = []
    seen: set[tuple] = set()
    target = _normalize_code(code)

    # Extrair location base do item
    location = getattr(item, "location", None)
    item_line = getattr(location, "line", 1) if location else 1
    item_column = getattr(location, "column", 1) if location else 1

    # Procurar em extra_fields (CODE, CHAIN, etc.)
    extra_fields = getattr(item, "extra_fields", {}) or {}

    # Preferir posições precisas fornecidas pelo compilador
    code_locations = getattr(item, "code_locations", None) or {}
    for field_name, locs in code_locations.items():
        value_field, values = _select_code_location_values(
            field_name, locs, item, extra_fields, target
        )
        if not values:
            continue
        for value, loc in _iter_value_locations(values, locs):
            if _normalize_code(value) != target:
                continue
            line, column = _location_line_column(loc)
            if line is None or column is None:
                continue
            key = (file_path, line, column, (value_field or "").lower(), "code")
            if key in seen:
                continue
            seen.add(key)
            occurrences.append(
                {
                    "file": file_path,
                    "itemName": item_name,
                    "line": line,
                    "column": column,
                    "context": "code",
                    "field": value_field,
                }
            )

    # Posições precisas para chains em item.chains
    chains = getattr(item, "chains", []) or []
    for chain in chains:
        field_name = (
            getattr(chain, "field_name", None)
            or getattr(chain, "field", None)
            or "CHAIN"
        )
        for node, loc in _iter_chain_code_locations(chain):
            if _normalize_code(node) != target:
                continue
            line, column = _location_line_column(loc)
            if line is None or column is None:
                continue
            key = (file_path, line, column, str(field_name).lower(), "chain")
            if key in seen:
                continue
            seen.add(key)
            occurrences.append(
                {
                    "file": file_path,
                    "itemName": item_name,
                    "line": line,
                    "column": column,
                    "context": "chain",
                    "field": field_name,
                }
            )

    # Posições precisas para chains em extra_fields
    for field_name, field_value in extra_fields.items():
        for candidate in _iter_chain_values(field_value):
            for node, loc in _iter_chain_code_locations(candidate):
                if _normalize_code(node) != target:
                    continue
                line, column = _location_line_column(loc)
                if line is None or column is None:
                    continue
                key = (file_path, line, column, str(field_name).lower(), "chain")
                if key in seen:
                    continue
                seen.add(key)
                occurrences.append(
                    {
                        "file": file_path,
                        "itemName": item_name,
                        "line": line,
                        "column": column,
                        "context": "chain",
                        "field": field_name,
                    }
                )

    if occurrences:
        return occurrences

    logger.info(
        "getOntologyAnnotations fallback to item location (code=%s, item=%s, file=%s, line=%s, column=%s)",
        code,
        item_name,
        file_path,
        item_line,
        item_column,
    )

    for field_name, field_value in extra_fields.items():
        if not field_value:
            continue

        # Determinar context baseado no field_name
        context = "code" if "CODE" in field_name.upper() else "chain"

        # Procurar code no field_value (case-insensitive, suporta ChainNode)
        if _field_value_contains_code(field_value, code):
            # Para simplificar, usar location do item
            # (cálculo exato de posição seria mais complexo e requer source text)
            occ = {
                "file": file_path,
                "itemName": item_name,
                "line": item_line,
                "column": item_column,
                "context": context,
                "field": field_name
            }
            occurrences.append(occ)

    # Procurar em chains (se item tem chains)
    chains = getattr(item, "chains", []) or []
    for chain in chains:
        if _chain_contains_code(chain, code):
            # Tentar extrair location específica do chain
            chain_location = _extract_chain_location(chain, location)
            chain_line = getattr(chain_location, "line", item_line) if chain_location else item_line
            chain_column = getattr(chain_location, "column", item_column) if chain_location else item_column

            occ = {
                "file": file_path,
                "itemName": item_name,
                "line": chain_line,
                "column": chain_column,
                "context": "chain",
                "field": "CHAIN"
            }
            occurrences.append(occ)

    return occurrences


def _chain_to_string(chain) -> str:
    """Converte chain para string para busca."""
    if isinstance(chain, str):
        return chain
    elif isinstance(chain, tuple) and len(chain) >= 3:
        # Triple: (from, rel, to)
        return f"{chain[0]}-{chain[1]}-{chain[2]}"
    elif hasattr(chain, "__str__"):
        return str(chain)
    return ""


def _extract_chain_location(chain, fallback_location):
    """Extrai location de um chain."""
    # Prioridade: tuple[3] → chain.location → fallback
    if isinstance(chain, tuple) and len(chain) > 3:
        loc = chain[3]
        if loc and hasattr(loc, "line"):
            return loc

    chain_loc = getattr(chain, "location", None)
    if chain_loc:
        return chain_loc

    return fallback_location


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
