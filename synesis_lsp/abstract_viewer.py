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

    # Tentar extrair ABSTRACT do LinkedProject se disponível
    if cached_result:
        result = getattr(cached_result, "result", None)
        if result:
            lp = getattr(result, "linked_project", None)
            if lp:
                # Tentar encontrar ABSTRACT nos sources
                abstract_data = _extract_from_linked_project(lp, path)
                if abstract_data:
                    return abstract_data

    # Fallback: parsear arquivo diretamente
    return _parse_abstract_from_file(path, workspace_root)


def _extract_from_linked_project(lp, file_path: Path) -> Optional[dict]:
    """
    Tenta extrair ABSTRACT do LinkedProject.

    Args:
        lp: LinkedProject object
        file_path: Path do arquivo

    Returns:
        Dict com abstract, file, line ou None se não encontrado
    """
    sources = getattr(lp, "sources", {}) or {}
    file_str = str(file_path)

    # Procurar source que corresponde ao arquivo
    for source_key, source in sources.items():
        source_file = getattr(source, "file", None)
        if source_file and Path(source_file) == file_path:
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
