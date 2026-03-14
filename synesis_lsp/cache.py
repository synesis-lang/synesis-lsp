"""
cache.py - Cache de CompilationResult por workspace e FileState por documento

Propósito:
    Armazena resultados de compilação completa (LinkedProject, stats, etc.)
    para servir custom requests sem recompilar a cada chamada.
    Também gerencia FileState por URI para evitar revalidação de documentos
    cujo conteúdo e contexto não mudaram (padrão Pyright sourceFile.ts).

Componentes principais:
    - CachedCompilation: Resultado de compilação com timestamp
    - WorkspaceCache: Dicionário de cache por workspace root
    - FileState: Dirty flags por documento (Fase 2 — padrão Pyright WriteableData)

Notas de implementação:
    - Compilação completa (~3.7s) é custosa; cache é essencial
    - Invalidar quando .synp/.synt/.bib/.syn/.syno mudam
    - Cada workspace tem no máximo um CompilationResult em cache
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedCompilation:
    """Resultado de compilação em cache com timestamp."""

    result: object  # CompilationResult do synesis
    timestamp: float = field(default_factory=time.time)
    workspace_root: Path = field(default_factory=lambda: Path("."))
    fingerprint: Optional[str] = None


class WorkspaceCache:
    """Cache de CompilationResult por workspace."""

    def __init__(self):
        self._cache: dict[str, CachedCompilation] = {}

    def get(self, workspace_key: str) -> Optional[CachedCompilation]:
        """Retorna compilação em cache para o workspace, ou None."""
        return self._cache.get(workspace_key)

    def put(
        self,
        workspace_key: str,
        result,
        workspace_root: Path,
        fingerprint: Optional[str] = None,
    ) -> None:
        """Armazena resultado de compilação no cache."""
        self._cache[workspace_key] = CachedCompilation(
            result=result,
            workspace_root=workspace_root,
            fingerprint=fingerprint,
        )
        logger.info(f"Cache atualizado para workspace: {workspace_key}")

    def invalidate(self, workspace_key: str) -> None:
        """Remove compilação do cache para o workspace."""
        if self._cache.pop(workspace_key, None):
            logger.info(f"Cache invalidado para workspace: {workspace_key}")

    def has(self, workspace_key: str) -> bool:
        """Verifica se há compilação em cache para o workspace."""
        return workspace_key in self._cache


@dataclass
class FileState:
    """
    Dirty flags por documento, inspirado em sourceFile.ts (Pyright WriteableData).

    Permite pular revalidação quando nem o conteúdo nem a versão de contexto
    do workspace mudaram desde a última validação.

    Campos:
        content_hash:           hash(source) do conteúdo atual
        validated_content_hash: hash(source) no momento da última validação completa
        context_version:        _context_versions[workspace_key] usada na última validação
        last_diagnostics:       diagnósticos publicados na última validação (para republish)
    """

    content_hash: int = 0
    validated_content_hash: int = -1
    context_version: int = 0
    last_diagnostics: list = field(default_factory=list)
