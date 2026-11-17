"""
hierarchy.py - Rastreio da hierarquia adotada (papeis HIERARCHY) no LSP

Proposito:
    Etapa A2d do plano ROLE/EXPORT (Spec v7, §12): mostrar no editor a
    hierarquia que o projeto declara no .syno (campos com ROLE HIERARCHY
    KIND/PART/INSTANCE), lida do LinkedProject compilado (`role_hierarchy`).

Componentes principais:
    - hierarchy_references: blocos ONTOLOGY que citam o conceito num campo HIERARCHY
    - type_hierarchy_item / supertypes / subtypes: "Show Type Hierarchy"
    - hierarchy_hover_lines: pais e filhos por especie, ITEMs proprios e da
      subarvore (uniao, sem contar duas vezes) e fundamentacao

Notas:
    So le o projeto compilado; nada aqui recompila. Com um compilador sem papeis
    (`role_hierarchy` ausente), tudo devolve vazio, e o comportamento anterior
    do LSP fica como estava.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lsprotocol.types import (
    Location,
    Position,
    Range,
    SymbolKind,
    TypeHierarchyItem,
)

SPECIES = ("KIND", "PART", "INSTANCE")


def concept_key(name: str) -> str:
    from synesis.ast.normalize import normalize_code

    return str(normalize_code(name))


def _project(cached_result) -> Tuple[Any, Any]:
    result = getattr(cached_result, "result", None) if cached_result else None
    lp = getattr(result, "linked_project", None) if result else None
    template = getattr(result, "template", None) if result else None
    return lp, template


def _hierarchy(lp) -> Any:
    return getattr(lp, "role_hierarchy", None) if lp else None


def _hierarchy_fields(template) -> Dict[str, str]:
    """{campo: especie} dos campos com papel HIERARCHY."""
    out: Dict[str, str] = {}
    for name, spec in (getattr(template, "field_specs", None) or {}).items():
        role = getattr(spec, "role", None) or ""
        if role.startswith("HIERARCHY "):
            out[name] = role.split(" ", 1)[1]
    return out


def _species_between(hierarchy, child: str, parent: str) -> str:
    for species in SPECIES:
        if (child, parent) in set(map(tuple, hierarchy.relations.get(species, []))):
            return species
    return ""


def _location(loc, workspace_root: Optional[Path]) -> Optional[Location]:
    if loc is None or not getattr(loc, "file", None):
        return None
    path = Path(str(loc.file))
    if not path.is_absolute():
        path = (workspace_root / path) if workspace_root else path.resolve()
    line = max(0, (loc.line or 1) - 1)
    col = max(0, (loc.column or 1) - 1)
    pos = Position(line=line, character=col)
    return Location(uri=path.as_uri(), range=Range(start=pos, end=pos))


# --------------------------------------------------------------- referencias

def hierarchy_references(cached_result, word: str, workspace_root: Optional[Path]) -> List[Location]:
    """Linhas `tipo_de: <conceito>` (e PART/INSTANCE) que citam o conceito."""
    lp, template = _project(cached_result)
    fields = _hierarchy_fields(template)
    if not lp or not fields:
        return []
    target = concept_key(word)
    out: List[Location] = []
    for node in (getattr(lp, "ontology_index", None) or {}).values():
        for fname in fields:
            values = node.fields.get(fname)
            values = values if isinstance(values, list) else ([values] if values else [])
            if not any(concept_key(str(v)) == target for v in values):
                continue
            entry = next((e for e in getattr(node, "entries", None) or [] if e.name == fname), None)
            loc = _location(entry.location if entry is not None else node.location, workspace_root)
            if loc:
                out.append(loc)
    return out


# ------------------------------------------------------------ type hierarchy

def _item(lp, key: str, workspace_root: Optional[Path], detail: str = "") -> Optional[TypeHierarchyItem]:
    node = (getattr(lp, "ontology_index", None) or {}).get(key)
    if node is None:
        return None
    loc = _location(node.location, workspace_root)
    if loc is None:
        return None
    return TypeHierarchyItem(
        name=node.concept,
        kind=SymbolKind.Class,
        uri=loc.uri,
        range=loc.range,
        selection_range=loc.range,
        detail=detail or None,
        data={"concept": key},
    )


def type_hierarchy_item(cached_result, word: str, workspace_root: Optional[Path]) -> Optional[List[TypeHierarchyItem]]:
    lp, _template = _project(cached_result)
    if _hierarchy(lp) is None:
        return None
    item = _item(lp, concept_key(word), workspace_root)
    return [item] if item else None


def supertypes(cached_result, item: TypeHierarchyItem, workspace_root: Optional[Path]) -> List[TypeHierarchyItem]:
    lp, _template = _project(cached_result)
    hierarchy = _hierarchy(lp)
    key = (item.data or {}).get("concept") if isinstance(item.data, dict) else None
    if hierarchy is None or not key:
        return []
    out = []
    for parent in sorted(hierarchy.parents.get(key, ())):
        found = _item(lp, parent, workspace_root, _species_between(hierarchy, key, parent))
        if found:
            out.append(found)
    return out


def subtypes(cached_result, item: TypeHierarchyItem, workspace_root: Optional[Path]) -> List[TypeHierarchyItem]:
    lp, _template = _project(cached_result)
    hierarchy = _hierarchy(lp)
    key = (item.data or {}).get("concept") if isinstance(item.data, dict) else None
    if hierarchy is None or not key:
        return []
    out = []
    for child in sorted(hierarchy.children.get(key, ())):
        found = _item(lp, child, workspace_root, _species_between(hierarchy, child, key))
        if found:
            out.append(found)
    return out


# --------------------------------------------------------------------- hover

def _items_of(lp, key: str, field_specs) -> Set[int]:
    from synesis_lsp.code_usage import usage_items

    node = (getattr(lp, "ontology_index", None) or {}).get(key)
    name = node.concept if node is not None else key
    return {id(i) for i in usage_items(lp, name, field_specs)}


def hierarchy_hover_lines(cached_result, word: str) -> List[str]:
    """Linhas Markdown do hover de um conceito: hierarquia e evidencias."""
    lp, template = _project(cached_result)
    key = concept_key(word)
    index = getattr(lp, "ontology_index", None) or {}
    aliases = getattr(lp, "aliases", None) or {}
    if key in aliases and aliases[key] in index:
        # Etapa U: o preterido aponta o conceito que vale; nao tem posicao propria.
        return [f"**Alias (USE):** use → `{index[aliases[key]].concept}`; "
                "mentions of this name count for the target."]
    hierarchy = _hierarchy(lp)
    if hierarchy is None:
        return []
    if key not in index:
        return []
    names = {k: n.concept for k, n in index.items()}
    lines: List[str] = []
    preteridos = sorted(index[a].concept for a, t in aliases.items() if t == key and a in index)
    if preteridos:
        lines.append("**Aliases (USE):** " + ", ".join(f"`{p}`" for p in preteridos))
    parents = sorted(hierarchy.parents.get(key, ()))
    children = sorted(hierarchy.children.get(key, ()))
    if parents:
        lines.append("**Parents:** " + ", ".join(
            f"`{names.get(p, p)}` ({_species_between(hierarchy, key, p)})" for p in parents))
    else:
        lines.append("**Parents:** none (top concept)")
    if children:
        lines.append("**Children:** " + ", ".join(
            f"`{names.get(c, c)}` ({_species_between(hierarchy, c, key)})" for c in children))
    field_specs = getattr(template, "field_specs", None)
    own = _items_of(lp, key, field_specs)
    for alias_key in (a for a, t in aliases.items() if t == key):
        own |= _items_of(lp, alias_key, field_specs)  # projeção resolvida
    union = set(own)
    descendants = hierarchy.descendants(key)
    for d in descendants:
        union |= _items_of(lp, d, field_specs)
    lines.append(f"**ITEMs:** {len(own)} own, {len(union)} in the subtree ({len(descendants)} descendant(s))")
    if not union:
        lines.append("**Ungrounded:** no mention of its own or of a descendant")
    return lines


# ----------------------------------------------------- arvore do explorador

def hierarchy_tree(cached_result, workspace_root: Optional[Path]) -> Optional[List[dict]]:
    """Arvore da hierarquia adotada, no formato do explorador de ontologia.

    Cada no: {"name", "level", "file", "line", "children", "species",
    "items", "itemsSubtree", "ungrounded"}. Raiz = conceitos de topo. Um conceito
    com dois pais aparece nos dois ramos (DAG); um ciclo nao entra em laco.
    None quando o template nao declara papel HIERARCHY (o explorador volta a
    agrupar por topico).
    """
    lp, template = _project(cached_result)
    hierarchy = _hierarchy(lp)
    if hierarchy is None or not _hierarchy_fields(template):
        return None
    index = getattr(lp, "ontology_index", None) or {}
    field_specs = getattr(template, "field_specs", None)
    own = {key: _items_of(lp, key, field_specs) for key in index}
    subtree: Dict[str, int] = {}
    for key in index:
        union = set(own[key])
        for d in hierarchy.descendants(key):
            union |= own.get(d, set())
        subtree[key] = len(union)

    def rel_file(loc) -> str:
        path = Path(str(loc.file))
        if workspace_root:
            try:
                return str(path.relative_to(workspace_root))
            except ValueError:
                pass
        return str(path)

    def node(key: str, level: int, species: str, trail: frozenset) -> dict:
        onto = index[key]
        children = [] if key in trail else [
            node(c, level + 1, _species_between(hierarchy, c, key), trail | {key})
            for c in sorted(hierarchy.children.get(key, ()), key=lambda k: index[k].concept.lower())
            if c in index
        ]
        loc = onto.location
        return {
            "name": onto.concept,
            "level": level,
            "file": rel_file(loc) if loc is not None else "",
            "line": loc.line if loc is not None else 0,
            "children": children,
            "species": species,
            "items": len(own[key]),
            "itemsSubtree": subtree[key],
            "ungrounded": subtree[key] == 0,
        }

    tops = sorted((k for k in index if not hierarchy.parents.get(k)), key=lambda k: index[k].concept.lower())
    return [node(k, 0, "", frozenset()) for k in tops]


def subtree_evidence(cached_result, word: str, workspace_root: Optional[Path]) -> List[dict]:
    """ITEMs do conceito e de todos os descendentes (uniao), para "evidencias da subarvore"."""
    lp, template = _project(cached_result)
    hierarchy = _hierarchy(lp)
    index = getattr(lp, "ontology_index", None) or {}
    key = concept_key(word)
    if key not in index:
        return []
    from synesis_lsp.code_usage import usage_items

    field_specs = getattr(template, "field_specs", None)
    keys = [key] + (sorted(hierarchy.descendants(key)) if hierarchy is not None else [])
    seen: Set[int] = set()
    out: List[dict] = []
    for k in keys:
        for item in usage_items(lp, index[k].concept, field_specs):
            if id(item) in seen:
                continue
            seen.add(id(item))
            loc = getattr(item, "location", None)
            where = _location(loc, workspace_root)
            if where is None:
                continue
            out.append({
                "concept": index[k].concept,
                "bibref": str(getattr(item, "bibref", "")),
                "uri": where.uri,
                "line": where.range.start.line,
                "quote": (getattr(item, "quote", "") or "")[:160],
            })
    return out
