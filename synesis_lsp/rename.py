"""
rename.py - Renomear bibrefs e códigos em todo o workspace

Propósito:
    Suporta textDocument/rename e textDocument/prepareRename para
    renomear bibrefs (@ref) e códigos da ontologia em todos os
    arquivos .syn e .syno do projeto.

Notas de implementação:
    - prepareRename verifica se o símbolo sob o cursor é renomeável
    - rename usa LinkedProject para localizar arquivos afetados
    - Para bibrefs: busca em SourceNode.location.file e ItemNode.location.file
    - Para códigos: busca em OntologyNode.location.file e arquivos .syn via code_usage
    - Lê arquivos do disco para encontrar ocorrências textuais
    - Produz WorkspaceEdit com TextEdits por arquivo
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from lsprotocol.types import (
    Position,
    Range,
    TextEdit,
    WorkspaceEdit,
)

from synesis_lsp.hover import _get_word_at_position

logger = logging.getLogger(__name__)


def prepare_rename(
    source: str, position: Position, cached_result
) -> Optional[Range]:
    """
    Verifica se o símbolo na posição é renomeável.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor
        cached_result: CachedCompilation do workspace_cache

    Returns:
        Range do símbolo se renomeável, None caso contrário
    """
    if not cached_result:
        return None

    lines = source.splitlines()
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    word = _get_word_at_position(line, position.character)
    if not word:
        return None

    lp = getattr(cached_result.result, "linked_project", None)
    if not lp:
        return None

    # @bibref → renomeável se existe em sources
    if word.startswith("@"):
        bibref = word[1:]
        sources = getattr(lp, "sources", {}) or {}
        if bibref in sources:
            start, end = _word_range(line, position.character)
            return Range(
                start=Position(line=position.line, character=start),
                end=Position(line=position.line, character=end),
            )
        return None

    # código → renomeável se existe na ontologia
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    if word in ontology_index:
        start, end = _word_range(line, position.character)
        return Range(
            start=Position(line=position.line, character=start),
            end=Position(line=position.line, character=end),
        )

    return None


def compute_rename(
    source: str,
    position: Position,
    new_name: str,
    cached_result,
) -> Optional[WorkspaceEdit]:
    """
    Computa WorkspaceEdit para renomear bibref ou código.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor
        new_name: Novo nome para o símbolo
        cached_result: CachedCompilation do workspace_cache

    Returns:
        WorkspaceEdit com TextEdits por arquivo, ou None
    """
    if not cached_result:
        return None

    lines = source.splitlines()
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    word = _get_word_at_position(line, position.character)
    if not word:
        return None

    lp = getattr(cached_result.result, "linked_project", None)
    if not lp:
        return None

    workspace_root = getattr(cached_result, "workspace_root", None)
    if not workspace_root:
        return None

    # @bibref → renomear em arquivos .syn
    if word.startswith("@"):
        return _rename_bibref(word[1:], new_name.lstrip("@"), lp, workspace_root)

    # código → renomear em arquivos .syn e .syno
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    if word in ontology_index:
        return _rename_code(word, new_name, lp, workspace_root)

    return None


def _rename_bibref(
    old_bibref: str, new_bibref: str, lp, workspace_root: Path
) -> Optional[WorkspaceEdit]:
    """Renomeia bibref em todos os arquivos que o referenciam."""
    sources = getattr(lp, "sources", {}) or {}
    src = sources.get(old_bibref)
    if not src:
        return None

    # Coletar arquivos afetados
    files_to_edit: set[Path] = set()

    # Arquivo onde o SOURCE é definido
    src_loc = getattr(src, "location", None)
    if src_loc and hasattr(src_loc, "file"):
        files_to_edit.add(workspace_root / str(src_loc.file))

    # Arquivos onde items referenciam este bibref
    for item in getattr(src, "items", []):
        item_loc = getattr(item, "location", None)
        if item_loc and hasattr(item_loc, "file"):
            files_to_edit.add(workspace_root / str(item_loc.file))

    if not files_to_edit:
        return None

    # Padrão para encontrar @old_bibref (com word boundary)
    pattern = re.compile(r"@" + re.escape(old_bibref) + r"(?!\w)")

    changes: dict[str, list[TextEdit]] = {}

    for file_path in files_to_edit:
        edits = _find_and_replace_in_file(
            file_path, pattern, f"@{new_bibref}"
        )
        if edits:
            uri = file_path.as_uri()
            changes[uri] = edits

    if not changes:
        return None

    return WorkspaceEdit(changes=changes)


def _rename_code(
    old_code: str, new_code: str, lp, workspace_root: Path
) -> Optional[WorkspaceEdit]:
    """Renomeia código em ontologia e em todos os arquivos .syn."""
    files_to_edit: set[Path] = set()

    # Arquivo da ontologia onde o código é definido
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    onto = ontology_index.get(old_code)
    if onto:
        onto_loc = getattr(onto, "location", None)
        if onto_loc and hasattr(onto_loc, "file"):
            files_to_edit.add(workspace_root / str(onto_loc.file))

    # Arquivos .syn que usam este código
    code_usage = getattr(lp, "code_usage", {}) or {}
    items = code_usage.get(old_code, [])
    for item in items:
        item_loc = getattr(item, "location", None)
        if item_loc and hasattr(item_loc, "file"):
            files_to_edit.add(workspace_root / str(item_loc.file))

    if not files_to_edit:
        return None

    # Padrão para encontrar old_code com word boundary
    # Precisa dar match em contextos como "  old_code" ou "campo: old_code old_code2"
    pattern = re.compile(r"(?<!\w)" + re.escape(old_code) + r"(?!\w)")

    changes: dict[str, list[TextEdit]] = {}

    for file_path in files_to_edit:
        edits = _find_and_replace_in_file(file_path, pattern, new_code)
        if edits:
            uri = file_path.as_uri()
            changes[uri] = edits

    if not changes:
        return None

    return WorkspaceEdit(changes=changes)


def _find_and_replace_in_file(
    file_path: Path, pattern: re.Pattern, replacement: str
) -> list[TextEdit]:
    """
    Lê arquivo e gera TextEdits para cada ocorrência do padrão.

    Args:
        file_path: Caminho absoluto do arquivo
        pattern: Regex compilado para busca
        replacement: Texto substituto

    Returns:
        Lista de TextEdit para este arquivo
    """
    edits: list[TextEdit] = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Não foi possível ler {file_path}: {e}")
        return edits

    for line_num, line in enumerate(content.splitlines()):
        for match in pattern.finditer(line):
            start_char = match.start()
            end_char = match.end()
            edits.append(
                TextEdit(
                    range=Range(
                        start=Position(line=line_num, character=start_char),
                        end=Position(line=line_num, character=end_char),
                    ),
                    new_text=replacement,
                )
            )

    return edits


def _word_range(line: str, character: int) -> tuple[int, int]:
    """Retorna (start, end) da palavra na posição do cursor."""
    word_chars = re.compile(r"[@\w]")

    start = character
    while start > 0 and word_chars.match(line[start - 1]):
        start -= 1

    end = character
    while end < len(line) and word_chars.match(line[end]):
        end += 1

    return start, end
