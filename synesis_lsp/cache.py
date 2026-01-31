"""
cache.py - Cache de CompilationResult por workspace

Propósito:
    Armazena resultados de compilação completa (LinkedProject, stats, etc.)
    para servir custom requests sem recompilar a cada chamada.

Componentes principais:
    - CachedCompilation: Resultado de compilação com timestamp
    - WorkspaceCache: Dicionário de cache por workspace root

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


class WorkspaceCache:
    """Cache de CompilationResult por workspace."""

    def __init__(self):
        self._cache: dict[str, CachedCompilation] = {}

    def get(self, workspace_key: str) -> Optional[CachedCompilation]:
        """Retorna compilação em cache para o workspace, ou None."""
        return self._cache.get(workspace_key)

    def put(self, workspace_key: str, result, workspace_root: Path) -> None:
        """Armazena resultado de compilação no cache."""
        self._cache[workspace_key] = CachedCompilation(
            result=result, workspace_root=workspace_root
        )
        logger.info(f"Cache atualizado para workspace: {workspace_key}")

    def invalidate(self, workspace_key: str) -> None:
        """Remove compilação do cache para o workspace."""
        if self._cache.pop(workspace_key, None):
            logger.info(f"Cache invalidado para workspace: {workspace_key}")

    def has(self, workspace_key: str) -> bool:
        """Verifica se há compilação em cache para o workspace."""
        return workspace_key in self._cache
