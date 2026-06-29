"""
template_info.py - Serializa TemplateNode para o cliente synesis-explorer

Propósito:
    Custom request synesis/getTemplate — substitui templateParser.js na extensão.
    Expõe field-specs e requirements por escopo diretamente do TemplateNode compilado.

Custom Request:
    synesis/getTemplate → field-specs e requirements do template carregado

Shape de resposta:
    {
        "success": bool,
        "template": {
            "name": str,
            "fields": [
                {
                    "name": str,
                    "type": str,        # "TEXT" | "CODE" | "CHAIN" | "QUOTATION" | ...
                    "scope": str,       # "SOURCE" | "ITEM" | "ONTOLOGY"
                    "relations": [...] | null,
                    "arity": str | null,  # ex: ">= 2"
                    "values": [...] | null
                }
            ],
            "requirements": {
                "SOURCE":   {"required": [...], "optional": [...], "forbidden": [...],
                             "bundles": [[...]], "optional_bundles": [[...]]},
                "ITEM":     { ... },
                "ONTOLOGY": { ... }
            }
        }
    }
"""

from __future__ import annotations

from typing import Any


def serialize_template(template) -> dict[str, Any]:
    """
    Serializa TemplateNode para o shape consumido pelo templateManager.js.

    Args:
        template: synesis.ast.nodes.TemplateNode

    Returns:
        dict pronto para ser enviado como resposta JSON ao cliente
    """
    fields = _serialize_fields(template)
    requirements = _serialize_requirements(template)
    return {
        "name": template.name,
        "fields": fields,
        "requirements": requirements,
    }


def _serialize_fields(template) -> list[dict[str, Any]]:
    """Converte field_specs em lista plana compatível com templateManager.buildFieldRegistry."""
    result = []
    for spec in template.field_specs.values():
        # relations: dict {name: description} → lista de nomes (o que templateParser devolvia)
        relations = list(spec.relations.keys()) if spec.relations else None

        # arity: string raw (">=2", "=1") — templateParser devolvia {operator, value}
        # mantemos string raw; o cliente pode parsear se necessário, ou usar como label
        arity = None
        if spec.arity:
            arity = _parse_arity(spec.arity)

        # values: lista de OrderedValue → [{index, label, description}]
        values = None
        if spec.values:
            values = [
                {
                    "index": v.index if hasattr(v, "index") else None,
                    "label": v.label if hasattr(v, "label") else str(v),
                    "description": v.description if hasattr(v, "description") else "",
                }
                for v in spec.values
            ]

        location = getattr(spec, "location", None)
        line = getattr(location, "line", None)      # 1-based
        column = getattr(location, "column", None)  # 1-based

        result.append({
            "name": spec.name,
            "type": spec.type.value if hasattr(spec.type, "value") else str(spec.type),
            "scope": spec.scope.value if hasattr(spec.scope, "value") else str(spec.scope),
            "relations": relations,
            "arity": arity,
            "values": values,
            "line": (line - 1) if isinstance(line, int) else None,    # 0-based para LSP/VSCode
            "column": (column - 1) if isinstance(column, int) else None,
        })

    return result


def _serialize_requirements(template) -> dict[str, dict[str, Any]]:
    """Serializa required/optional/forbidden/bundles/optional_bundles por escopo."""
    result: dict[str, dict] = {}

    try:
        from synesis.ast.nodes import Scope
        scopes = list(Scope)
    except ImportError:
        return result

    for scope in scopes:
        key = scope.value  # "SOURCE" | "ITEM" | "ONTOLOGY"
        result[key] = {
            "required": list(template.required_fields.get(scope, [])),
            "optional": list(template.optional_fields.get(scope, [])),
            "forbidden": list(template.forbidden_fields.get(scope, [])),
            "bundles": [list(b) for b in template.bundled_fields.get(scope, [])],
            "optional_bundles": [list(b) for b in template.optional_bundles.get(scope, [])],
        }

    return result


def _parse_arity(arity_str: str) -> dict[str, Any] | None:
    """
    Converte string de arity (ex: '>= 2') em {operator, value}.
    Compatível com o shape que templateParser.extractArity produzia.
    """
    import re
    m = re.match(r"\s*(>=|<=|=|>|<)\s*(\d+(?:\.\d+)?)\s*$", str(arity_str))
    if not m:
        return None
    raw_val = m.group(2)
    try:
        val = int(raw_val) if "." not in raw_val else float(raw_val)
    except ValueError:
        return None
    return {"operator": m.group(1), "value": val}
