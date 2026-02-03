"""
workspace_diagnostics.py - Diagnósticos para todo o workspace

Propósito:
    Validar todos os arquivos Synesis no workspace, não apenas
    os arquivos abertos no editor.

LSP Feature:
    workspace/diagnostic → Diagnostics para todos os arquivos
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lsprotocol.types import Diagnostic, WorkspaceFullDocumentDiagnosticReport

logger = logging.getLogger(__name__)


def compute_workspace_diagnostics(
    workspace_root: Path,
    validate_func
) -> dict[str, list[Diagnostic]]:
    """
    Gera diagnósticos para todos os arquivos no workspace.

    Args:
        workspace_root: Raiz do workspace
        validate_func: Função para validar um arquivo individual

    Returns:
        Dict mapeando URIs para listas de Diagnostic
    """
    diagnostics_map = {}

    if not workspace_root or not workspace_root.exists():
        logger.warning(f"Workspace root não existe: {workspace_root}")
        return diagnostics_map

    # Encontrar todos os arquivos Synesis
    synesis_files = _find_synesis_files(workspace_root)

    logger.info(f"Validando {len(synesis_files)} arquivos no workspace")

    # Validar cada arquivo
    for file_path in synesis_files:
        try:
            uri = file_path.as_uri()
            diagnostics = validate_func(uri, file_path)

            if diagnostics:
                diagnostics_map[uri] = diagnostics
            else:
                # Arquivo sem erros
                diagnostics_map[uri] = []

        except Exception as e:
            logger.warning(f"Erro ao validar {file_path}: {e}", exc_info=True)
            # Continuar com próximo arquivo

    logger.info(f"Workspace diagnostics completo: {len(diagnostics_map)} arquivos processados")

    return diagnostics_map


def _find_synesis_files(workspace_root: Path) -> list[Path]:
    """
    Encontra todos os arquivos Synesis no workspace.

    Args:
        workspace_root: Raiz do workspace

    Returns:
        Lista de Path para arquivos .syn, .synp, .synt, .syno
    """
    synesis_extensions = [".syn", ".synp", ".synt", ".syno"]
    files = []

    try:
        for ext in synesis_extensions:
            # Buscar recursivamente
            files.extend(workspace_root.rglob(f"*{ext}"))
    except Exception as e:
        logger.warning(f"Erro ao buscar arquivos no workspace: {e}")

    return files


def build_workspace_diagnostic_report(
    uri: str,
    diagnostics: list[Diagnostic],
    version: Optional[int] = None
) -> WorkspaceFullDocumentDiagnosticReport:
    """
    Constrói report de diagnóstico para workspace.

    Args:
        uri: URI do documento
        diagnostics: Lista de diagnósticos
        version: Versão do documento

    Returns:
        WorkspaceFullDocumentDiagnosticReport
    """
    return WorkspaceFullDocumentDiagnosticReport(
        uri=uri,
        version=version,
        items=diagnostics,
        kind="full"
    )


def validate_workspace_file(
    uri: str,
    file_path: Path,
    validate_single_file_func
) -> list[Diagnostic]:
    """
    Valida um arquivo individual do workspace.

    Args:
        uri: URI do arquivo
        file_path: Path absoluto do arquivo
        validate_single_file_func: Função de validação do adaptador

    Returns:
        Lista de Diagnostic
    """
    try:
        # Ler conteúdo do arquivo
        source = file_path.read_text(encoding="utf-8")

        # Validar usando adaptador
        validation_result = validate_single_file_func(source, uri)

        # Converter para diagnósticos LSP
        from synesis_lsp.converters import build_diagnostics
        diagnostics = build_diagnostics(validation_result)

        return diagnostics

    except Exception as e:
        logger.warning(f"Erro ao validar arquivo {file_path}: {e}", exc_info=True)
        return []
