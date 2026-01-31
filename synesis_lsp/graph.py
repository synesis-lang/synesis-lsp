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
from typing import Optional

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
        return {"success": True, "mermaidCode": "graph LR\n    empty[Sem relações]"}

    # Se bibref fornecido, filtrar relações
    if bibref:
        code_usage = getattr(lp, "code_usage", {}) or {}
        # Encontrar códigos usados pelo bibref
        relevant_codes = set()
        sources = getattr(lp, "sources", {}) or {}
        normalized = bibref.lstrip("@").strip()
        src = sources.get(normalized)
        if src:
            for item in getattr(src, "items", []):
                for field_val in getattr(item, "extra_fields", {}).values():
                    if isinstance(field_val, list):
                        for code in field_val:
                            if isinstance(code, str):
                                relevant_codes.add(code.lower())
                    elif isinstance(field_val, str):
                        relevant_codes.add(field_val.lower())

        if not relevant_codes:
            return {
                "success": True,
                "mermaidCode": f"graph LR\n    empty[Sem relações para {bibref}]",
            }

        triples = [
            (s, r, o)
            for s, r, o in triples
            if s.lower() in relevant_codes or o.lower() in relevant_codes
        ]

    if not triples:
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

    return {"success": True, "mermaidCode": "\n".join(lines)}
