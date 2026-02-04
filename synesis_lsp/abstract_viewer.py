"""
abstract_viewer.py - Extração de campo ABSTRACT

Propósito:
    Extrair campo ABSTRACT de arquivos .syn para visualização.

Custom Request:
    synesis/getAbstract → Conteúdo do campo ABSTRACT
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_abstract(
    file_path: str,
    cached_result=None,
    workspace_root: Optional[Path] = None
) -> dict:
    """
    Extrai campo ABSTRACT do arquivo.

    Args:
        file_path: Caminho para arquivo .syn (pode ser absoluto ou relativo)
        cached_result: CachedCompilation (opcional, para acessar LinkedProject)
        workspace_root: Raiz do workspace para resolver paths relativos

    Returns:
        {
            "success": bool,
            "abstract": str,
            "file": str,
            "line": int
        }
    """
    if not file_path:
        return {"success": False, "error": "Arquivo não especificado"}

    # Resolver path
    path = Path(file_path)

    # Se relativo e temos workspace_root, resolver
    if not path.is_absolute() and workspace_root:
        path = workspace_root / path

    if not path.exists():
        return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}

    if path.suffix not in [".syn", ".synp"]:
        return {"success": False, "error": "Arquivo deve ser .syn ou .synp"}

    # Tentar extrair ABSTRACT da bibliografia se disponível
    if cached_result:
        result = getattr(cached_result, "result", None)
        if result:
            lp = getattr(result, "linked_project", None)
            if lp:
                abstract_data = _extract_from_bibliography(
                    result, lp, path, workspace_root
                )
                if abstract_data:
                    return abstract_data

                # Tentar encontrar ABSTRACT nos sources
                abstract_data = _extract_from_linked_project(lp, path, workspace_root)
                if abstract_data:
                    return abstract_data

    # Fallback: parsear arquivo diretamente
    return _parse_abstract_from_file(path, workspace_root)


def _extract_from_bibliography(
    result,
    lp,
    file_path: Path,
    workspace_root: Optional[Path],
) -> Optional[dict]:
    """
    Tenta extrair ABSTRACT do arquivo .bib associado ao SOURCE.
    """
    source = _find_source_for_file(lp, file_path, workspace_root)
    if not source:
        return None

    bibref = getattr(source, "bibref", None)
    if not bibref:
        return None

    bibref = _normalize_bibref(str(bibref))
    bibliography = (
        getattr(result, "bibliography", None)
        or getattr(lp, "bibliography", None)
        or {}
    )

    entry = bibliography.get(bibref) or bibliography.get(bibref.lower())
    if not entry:
        return None

    abstract_text = _extract_abstract_from_entry(entry)
    if not abstract_text:
        return None

    file_val, line_val = _extract_entry_location(entry, workspace_root)
    if not file_val:
        file_val = str(file_path)
    if not line_val:
        line_val = 1

    return {
        "success": True,
        "abstract": abstract_text,
        "file": file_val,
        "line": line_val,
    }


def _extract_from_linked_project(
    lp, file_path: Path, workspace_root: Optional[Path] = None
) -> Optional[dict]:
    """
    Tenta extrair ABSTRACT do LinkedProject.

    Args:
        lp: LinkedProject object
        file_path: Path do arquivo

    Returns:
        Dict com abstract, file, line ou None se não encontrado
    """
    source = _find_source_for_file(lp, file_path, workspace_root)
    if not source:
        return None

    # Verificar se source tem campo ABSTRACT
    extra_fields = getattr(source, "extra_fields", {}) or {}
    abstract_value = extra_fields.get("ABSTRACT")

    if abstract_value:
        # Extrair location
        location = getattr(source, "location", None)
        line = getattr(location, "line", 1) if location else 1

        # abstract_value pode ser string ou lista
        if isinstance(abstract_value, list):
            abstract_text = "\n".join(str(v) for v in abstract_value if v)
        else:
            abstract_text = str(abstract_value)

        return {
            "success": True,
            "abstract": abstract_text,
            "file": str(file_path),
            "line": line
        }

    return None


def _find_source_for_file(
    lp,
    file_path: Path,
    workspace_root: Optional[Path],
):
    sources = getattr(lp, "sources", {}) or {}
    for source in sources.values():
        source_file = getattr(source, "file", None)
        if source_file and _paths_match(source_file, file_path, workspace_root):
            return source

        location = getattr(source, "location", None)
        loc_file = getattr(location, "file", None) if location else None
        if loc_file and _paths_match(loc_file, file_path, workspace_root):
            return source
    return None


def _paths_match(path_value, file_path: Path, workspace_root: Optional[Path]) -> bool:
    candidate = _resolve_path(path_value, workspace_root)
    if not candidate:
        return False
    try:
        return candidate.resolve() == file_path.resolve()
    except OSError:
        return candidate == file_path


def _resolve_path(path_value, workspace_root: Optional[Path]) -> Optional[Path]:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_absolute() and workspace_root:
        path = workspace_root / path
    return path


def _extract_entry_location(entry, workspace_root: Optional[Path]) -> tuple[Optional[str], Optional[int]]:
    location = None
    if isinstance(entry, dict):
        location = entry.get("location")
    else:
        location = getattr(entry, "location", None)

    if not location:
        return None, None

    if isinstance(location, dict):
        file_val = location.get("file")
        line_val = location.get("line")
    else:
        file_val = getattr(location, "file", None)
        line_val = getattr(location, "line", None)

    if not file_val:
        return None, line_val

    path = _resolve_path(file_val, workspace_root)
    if not path:
        return None, line_val

    if workspace_root:
        try:
            return str(path.relative_to(workspace_root)), line_val
        except ValueError:
            pass
    return str(path), line_val


def _extract_abstract_from_entry(entry) -> Optional[str]:
    if isinstance(entry, dict):
        for key, value in entry.items():
            if str(key).lower() == "abstract":
                return _stringify_abstract(value)
        return None

    value = getattr(entry, "abstract", None)
    return _stringify_abstract(value)


def _stringify_abstract(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v)
    return str(value)


def _normalize_bibref(value: str) -> str:
    return value.lstrip("@").strip().lower()


def _parse_abstract_from_file(file_path: Path, workspace_root: Optional[Path]) -> dict:
    """
    Parseia arquivo .syn diretamente para extrair ABSTRACT.

    Args:
        file_path: Path absoluto para arquivo
        workspace_root: Raiz do workspace para relativizar path

    Returns:
        Dict com abstract, file, line
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Erro ao ler arquivo {file_path}: {e}")
        return {"success": False, "error": f"Erro ao ler arquivo: {e}"}

    lines = content.split("\n")

    # Procurar campo ABSTRACT
    in_abstract = False
    abstract_lines = []
    abstract_start_line = None
    current_indent = None

    for line_number, line in enumerate(lines, start=1):
        # Detectar início de ABSTRACT
        if line.strip().upper().startswith("ABSTRACT:"):
            in_abstract = True
            abstract_start_line = line_number

            # Extrair conteúdo na mesma linha (após "ABSTRACT:")
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                abstract_lines.append(parts[1].strip())

            # Calcular indentação esperada para linhas de continuação
            current_indent = len(line) - len(line.lstrip())
            continue

        # Se estamos em ABSTRACT, coletar linhas de continuação
        if in_abstract:
            # Linha vazia pode indicar continuação ou fim
            if not line.strip():
                # Se próxima linha tem conteúdo indentado, continua
                continue

            # Verificar se linha pertence ao ABSTRACT (indentação maior)
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Se indentação é maior, faz parte do ABSTRACT
            if indent > current_indent:
                abstract_lines.append(stripped)
            else:
                # Novo campo ou bloco, fim do ABSTRACT
                break

    if abstract_lines:
        # Relativizar path se possível
        relative_file = str(file_path)
        if workspace_root:
            try:
                relative_file = str(file_path.relative_to(workspace_root))
            except ValueError:
                pass

        return {
            "success": True,
            "abstract": "\n".join(abstract_lines),
            "file": relative_file,
            "line": abstract_start_line or 1
        }

    # ABSTRACT não encontrado
    return {
        "success": False,
        "error": "Campo ABSTRACT não encontrado no arquivo"
    }
