"""
ontology_topics.py - Extração de hierarquia de tópicos de arquivos .syno

Propósito:
    Parsear arquivos .syno respeitando indentação para construir
    árvore de conceitos hierárquica.

Custom Request:
    synesis/getOntologyTopics → Lista hierárquica de topics
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TOPICS_CACHE: dict[tuple[str, float], dict] = {}
_TOPICS_CACHE_MAX = 4


def _topics_cache_key(cached_result, workspace_root: Optional[Path]) -> Optional[tuple[str, int, float]]:
    if not cached_result:
        return None
    root = workspace_root or getattr(cached_result, "workspace_root", None)
    root_key = str(root) if root else ""
    timestamp = getattr(cached_result, "timestamp", None)
    if timestamp is None:
        return None
    return (root_key, id(cached_result), float(timestamp))


def _topics_cache_set(key: Optional[tuple[str, float]], value: dict) -> None:
    if not key:
        return
    _TOPICS_CACHE[key] = value
    if len(_TOPICS_CACHE) > _TOPICS_CACHE_MAX:
        oldest_key = next(iter(_TOPICS_CACHE))
        if oldest_key != key:
            _TOPICS_CACHE.pop(oldest_key, None)


def get_ontology_topics(cached_result, workspace_root: Optional[Path] = None) -> dict:
    """
    Retorna hierarquia de tópicos da ontologia.

    Args:
        cached_result: CachedCompilation com LinkedProject
        workspace_root: Raiz do workspace para relativizar paths

    Returns:
        {
            "success": bool,
            "topics": [
                {
                    "name": str,
                    "level": int,
                    "file": str (relativo),
                    "line": int,
                    "children": [...]
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
    cache_key = _topics_cache_key(cached_result, effective_root)
    cached = _TOPICS_CACHE.get(cache_key) if cache_key else None
    if cached is not None:
        return cached

    # Extrair informações da ontologia
    ontology_index = getattr(lp, "ontology_index", {}) or {}

    if not ontology_index:
        logger.debug("Ontology index vazio, retornando lista vazia")
        result = {"success": True, "topics": []}
        _topics_cache_set(cache_key, result)
        return result

    # Agrupar conceitos por arquivo .syno
    files_to_parse: dict[Path, list[tuple[str, int]]] = {}

    for code, onto_node in ontology_index.items():
        location = getattr(onto_node, "location", None)
        if not location:
            continue

        file_path = getattr(location, "file", None)
        line = getattr(location, "line", None)

        if file_path and line:
            path = Path(file_path)
            if path.suffix == ".syno":
                if path not in files_to_parse:
                    files_to_parse[path] = []
                files_to_parse[path].append((code, line))

    if not files_to_parse:
        logger.debug("Nenhum arquivo .syno encontrado")
        result = {"success": True, "topics": []}
        _topics_cache_set(cache_key, result)
        return result

    # Parsear cada arquivo .syno
    all_topics = []
    for syno_path, concepts in files_to_parse.items():
        try:
            topics = _parse_syno_file(syno_path, effective_root, concepts)
            all_topics.extend(topics)
        except Exception as e:
            logger.warning(f"Erro ao parsear {syno_path}: {e}", exc_info=True)

    result = {"success": True, "topics": all_topics}
    _topics_cache_set(cache_key, result)
    return result


def _parse_syno_file(
    file_path: Path,
    workspace_root: Optional[Path],
    concepts: list[tuple[str, int]]
) -> list[dict]:
    """
    Parseia arquivo .syno e extrai hierarquia.

    Args:
        file_path: Caminho absoluto para arquivo .syno
        workspace_root: Raiz do workspace para relativizar paths
        concepts: Lista de (code, line) conhecidos da ontology_index

    Returns:
        Lista de tópicos raiz (cada um pode ter children)
    """
    if not file_path.exists():
        logger.warning(f"Arquivo não encontrado: {file_path}")
        return []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Erro ao ler {file_path}: {e}")
        return []

    lines = content.split("\n")

    # Relativizar path
    relative_file = str(file_path)
    if workspace_root:
        try:
            relative_file = str(file_path.relative_to(workspace_root))
        except ValueError:
            pass

    # Criar mapa de conceitos conhecidos (code -> line)
    concept_lines = {code: line for code, line in concepts}

    # Parsear linha por linha
    topics = []
    stack = []  # (level, topic_dict)

    in_ontology = False
    chain_fields = {"parent", "parents", "is_a", "isa", "chain", "chains"}

    for line_number, line in enumerate(lines, start=1):
        # Ignorar linhas vazias
        if not line.strip():
            continue

        # Calcular nível baseado em indentação (assumindo 4 espaços ou 1 tab = 1 nível)
        stripped = line.lstrip()
        if not stripped:
            continue

        indent = len(line) - len(stripped)
        level = indent // 4  # 4 espaços = 1 nível

        # Se tem tabs, contar tabs como nível
        if "\t" in line[:indent]:
            level = line[:indent].count("\t")

        header_match = re.match(r"^ONTOLOGY\s+(\S+)", stripped, flags=re.IGNORECASE)
        if header_match:
            in_ontology = True
            name = header_match.group(1).strip()
        elif stripped.upper().startswith("END ONTOLOGY"):
            in_ontology = False
            continue
        else:
            if not in_ontology:
                continue
            field_match = re.match(r"^([\w._-]+)\s*:\s*(.+)$", stripped)
            if not field_match:
                continue
            field_name = field_match.group(1).lower()
            if field_name not in chain_fields:
                continue
            name = field_match.group(2).strip()
            if not name:
                continue

        # Criar tópico
        topic = {
            "name": name,
            "level": level,
            "file": relative_file,
            "line": line_number,
            "children": []
        }

        # Construir hierarquia usando stack
        # Remove do stack todos os itens no mesmo nível ou mais profundo
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Adiciona como filho do pai
            parent_level, parent_topic = stack[-1]
            parent_topic["children"].append(topic)
        else:
            # Tópico raiz
            topics.append(topic)

        # Adiciona ao stack
        stack.append((level, topic))

    return topics
