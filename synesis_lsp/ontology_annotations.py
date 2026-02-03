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

logger = logging.getLogger(__name__)


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

    # Extrair dados da ontologia e code_usage
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    code_usage = getattr(lp, "code_usage", {}) or {}

    if not ontology_index:
        logger.debug("Ontology index vazio, retornando lista vazia")
        return {"success": True, "annotations": []}

    # Para cada conceito da ontologia, buscar suas occurrences
    annotations = []

    for code, onto_node in ontology_index.items():
        # Informações da definição na ontologia
        onto_location = getattr(onto_node, "location", None)
        ontology_file = None
        ontology_line = None

        if onto_location:
            onto_file_path = getattr(onto_location, "file", None)
            if onto_file_path and workspace_root:
                try:
                    ontology_file = str(Path(onto_file_path).relative_to(workspace_root))
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
            workspace_root=workspace_root,
            active_file=active_file
        )

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

    return {"success": True, "annotations": annotations}


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
        # Extrair location do item
        location = getattr(item, "location", None)
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

    # Extrair location base do item
    location = getattr(item, "location", None)
    item_line = getattr(location, "line", 1) if location else 1
    item_column = getattr(location, "column", 1) if location else 1

    # Procurar em extra_fields (CODE, CHAIN, etc.)
    extra_fields = getattr(item, "extra_fields", {}) or {}

    for field_name, field_value in extra_fields.items():
        if not field_value:
            continue

        # Determinar context baseado no field_name
        context = "code" if "CODE" in field_name.upper() else "chain"

        # field_value pode ser string ou lista
        if isinstance(field_value, list):
            # Concatenar lista em string
            field_str = " ".join(str(v) for v in field_value if v)
        else:
            field_str = str(field_value)

        # Procurar code no field_value
        if code in field_str:
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
        chain_str = _chain_to_string(chain)
        if code in chain_str:
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
