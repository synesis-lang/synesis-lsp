"""shared_includes.py — Etapa 5: indice reverso dos alvos de INCLUDE SHARED ONTOLOGY.

Uma ontologia declarada com `INCLUDE SHARED ONTOLOGY` vive FORA da pasta do
projeto (outro drive, rede, `..`). Isso quebra duas premissas do LSP, ambas
assumindo projeto auto-contido:

  1. **Fingerprint do workspace** (`_compute_workspace_fingerprint`) faz `os.walk`
     so na raiz — o alvo externo nunca entra, entao editar a ontologia
     compartilhada NAO invalida o cache e o `loadProject` devolve dado obsoleto.
  2. **`onDidSaveTextDocument`** (extensao) so dispara para documentos ABERTOS no
     editor — a ontologia compartilhada pode mudar por git pull, outra janela ou
     outro processo, sem evento nenhum.

Este modulo resolve os alvos externos de cada `.synp` do workspace e monta o
indice reverso `alvo -> projetos que o incluem`. O fingerprint usa os alvos para
detectar a mudanca; a extensao usa a lista para instalar FileSystemWatchers e
saber QUAIS projetos invalidar quando um alvo muda.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class SharedIncludeIndex:
    """Indice reverso: alvo externo -> projetos (.synp) que o incluem."""

    # caminho canonico do alvo -> lista de .synp que o declaram
    targets: Dict[Path, List[Path]] = field(default_factory=dict)

    def all_targets(self) -> List[Path]:
        return sorted(self.targets.keys())

    def projects_for(self, target: Path) -> List[Path]:
        """Projetos que devem ser invalidados quando `target` muda."""
        try:
            resolved = Path(target).resolve()
        except OSError:
            resolved = Path(target)
        return self.targets.get(resolved, [])

    def is_empty(self) -> bool:
        return not self.targets


def _iter_synp_files(root: Path) -> List[Path]:
    root_path = root if root.is_dir() else root.parent
    if root.suffix.lower() == ".synp":
        return [root]
    try:
        return sorted(root_path.glob("**/*.synp"))
    except OSError:
        return []


def _shared_targets_of(synp_path: Path) -> List[Path]:
    """Alvos de INCLUDE SHARED ONTOLOGY declarados num .synp.

    Parseia o projeto e resolve so os includes marcados `shared`. Falha de parse
    nao propaga: um .synp quebrado ja e reportado por outra via, e o watcher nao
    pode derrubar o servidor por causa dele.
    """
    try:
        from synesis.ast.nodes import ProjectNode
        from synesis.parser.lexer import parse_file
        from synesis.parser.paths import resolve_include
        from synesis.parser.transformer import SynesisTransformer
    except ImportError:  # pragma: no cover - compilador ausente
        return []

    try:
        tree = parse_file(synp_path)
        out = SynesisTransformer(synp_path).transform(tree)
    except Exception as exc:
        logger.debug("shared_includes: falha ao parsear %s: %s", synp_path, exc)
        return []

    nodes = out if isinstance(out, list) else [out]
    project = next((n for n in nodes if isinstance(n, ProjectNode)), None)
    if project is None:
        return []

    project_dir = synp_path.parent
    targets: List[Path] = []
    for include in getattr(project, "includes", []):
        if not getattr(include, "shared", False):
            continue
        if include.include_type.upper() != "ONTOLOGY":
            # SHARED so vale para ONTOLOGY (E084 reporta o uso indevido).
            continue
        resolution = resolve_include(project_dir, include.path, shared=True)
        # O alvo entra no indice mesmo se ainda nao existe: o watcher precisa
        # observar o caminho para reagir quando o arquivo for criado.
        if resolution.path is not None:
            targets.append(resolution.path)
    return targets


def build_shared_include_index(root: Path) -> SharedIncludeIndex:
    """Monta o indice reverso dos INCLUDE SHARED ONTOLOGY sob `root`.

    Args:
        root: raiz do workspace (ou um .synp especifico).

    Returns:
        SharedIncludeIndex vazio quando nenhum projeto usa SHARED — o caso de
        todo projeto legado, que assim nao paga custo nenhum.
    """
    index = SharedIncludeIndex()
    for synp in _iter_synp_files(Path(root)):
        for target in _shared_targets_of(synp):
            try:
                key = target.resolve()
            except OSError:
                key = target
            index.targets.setdefault(key, [])
            if synp not in index.targets[key]:
                index.targets[key].append(synp)
    return index


def shared_targets_fingerprint(index: SharedIncludeIndex) -> str:
    """Contribuicao dos alvos externos para o fingerprint do workspace.

    Sem isto, editar a ontologia compartilhada nao muda o fingerprint e o cache
    do LSP serve dado obsoleto — o watcher chamaria loadProject em vao.

    Alvo ausente entra como `0.0` (e nao e ignorado): assim, criar o arquivo
    depois muda o fingerprint e dispara a recompilacao.
    """
    if index.is_empty():
        return ""
    parts: List[str] = []
    for target in index.all_targets():
        try:
            mtime = os.path.getmtime(target)
        except OSError:
            mtime = 0.0
        parts.append(f"{target}:{mtime}")
    return "|".join(parts)


def find_projects_for_target(root: Path, target: Path) -> List[Path]:
    """Atalho: projetos sob `root` que incluem `target` como ontologia SHARED."""
    return build_shared_include_index(root).projects_for(target)
