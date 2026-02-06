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
        bibref = _normalize_bibref(word)
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
    normalized = _normalize_code(word)
    if normalized in ontology_index or word in ontology_index:
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
    template = getattr(cached_result.result, "template", None)

    workspace_root = getattr(cached_result, "workspace_root", None)
    if not workspace_root:
        return None

    # @bibref → renomear em arquivos .syn
    if word.startswith("@"):
        return _rename_bibref(
            _normalize_bibref(word),
            _normalize_bibref(new_name),
            lp,
            workspace_root,
        )

    # código → renomear em arquivos .syn e .syno
    ontology_index = getattr(lp, "ontology_index", {}) or {}
    normalized = _normalize_code(word)
    if normalized in ontology_index or word in ontology_index:
        return _rename_code(word, normalized, new_name, lp, workspace_root, template)

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
    pattern = re.compile(r"@" + re.escape(old_bibref) + r"(?![\w.-])", re.IGNORECASE)

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

    _log_rename_summary("bibref", old_bibref, new_bibref, changes)
    return WorkspaceEdit(changes=changes)


def _rename_code(
    old_code_raw: str,
    old_code_key: str,
    new_code: str,
    lp,
    workspace_root: Path,
    template=None,
) -> Optional[WorkspaceEdit]:
    """Renomeia código em ontologia e em todos os arquivos .syn/.syno."""
    files_to_edit: set[Path] = set()

    # Varredura completa dos arquivos do workspace
    files_to_edit.update(_collect_files(workspace_root, ".syn"))
    files_to_edit.update(_collect_files(workspace_root, ".syno"))

    if not files_to_edit:
        return None

    pattern = _build_code_pattern(old_code_raw, old_code_key)
    ontology_code_fields = _ontology_code_fields(template)
    item_code_fields = _item_code_fields(template)
    item_chain_fields = _item_chain_fields(template)

    changes: dict[str, list[TextEdit]] = {}

    for file_path in files_to_edit:
        suffix = file_path.suffix.lower()
        if suffix == ".syno":
            edits = _find_and_replace_in_syno(
                file_path, pattern, new_code, ontology_code_fields
            )
        elif suffix == ".syn":
            edits = _find_and_replace_in_syn(
                file_path, pattern, new_code, item_code_fields, item_chain_fields
            )
        else:
            edits = _find_and_replace_in_file(file_path, pattern, new_code)
        if edits:
            uri = file_path.as_uri()
            changes[uri] = edits

    if not changes:
        return None

    _log_rename_summary("code", old_code_raw, new_code, changes)
    return WorkspaceEdit(changes=changes)


def _normalize_bibref(bibref: str) -> str:
    return bibref.lstrip("@").strip().lower()


def _normalize_code(code: str) -> str:
    return " ".join(code.strip().split()).lower()


def _collect_files(workspace_root: Path, suffix: str) -> set[Path]:
    files: set[Path] = set()
    try:
        for path in workspace_root.rglob(f"*{suffix}"):
            if path.is_file():
                files.add(path)
    except OSError as exc:
        logger.warning(f"Erro ao varrer arquivos {suffix}: {exc}")
    return files


def _build_code_pattern(old_code_raw: str, old_code_key: str) -> re.Pattern:
    if old_code_raw != old_code_key:
        pattern = (
            r"(?<![\w.-])(?:"
            + re.escape(old_code_raw)
            + r"|"
            + re.escape(old_code_key)
            + r")(?![\w.-])"
        )
    else:
        pattern = r"(?<![\w.-])" + re.escape(old_code_raw) + r"(?![\w.-])"
    return re.compile(pattern, re.IGNORECASE)


def _ontology_code_fields(template) -> set[str]:
    fields: set[str] = set()
    if not template:
        return fields
    field_specs = getattr(template, "field_specs", None) or {}
    for name, spec in field_specs.items():
        scope = getattr(spec, "scope", None)
        field_type = getattr(spec, "type", None)
        scope_name = getattr(scope, "name", None)
        type_name = getattr(field_type, "name", None)
        if scope_name == "ONTOLOGY" and type_name in {"CODE", "CHAIN"}:
            fields.add(str(name).lower())
    return fields


def _item_code_fields(template) -> set[str]:
    fields: set[str] = set()
    if not template:
        return fields
    field_specs = getattr(template, "field_specs", None) or {}
    for name, spec in field_specs.items():
        scope = getattr(spec, "scope", None)
        field_type = getattr(spec, "type", None)
        scope_name = getattr(scope, "name", None)
        type_name = getattr(field_type, "name", None)
        if scope_name == "ITEM" and type_name == "CODE":
            fields.add(str(name).lower())
    return fields


def _item_chain_fields(template) -> set[str]:
    fields: set[str] = set()
    if not template:
        return fields
    field_specs = getattr(template, "field_specs", None) or {}
    for name, spec in field_specs.items():
        scope = getattr(spec, "scope", None)
        field_type = getattr(spec, "type", None)
        scope_name = getattr(scope, "name", None)
        type_name = getattr(field_type, "name", None)
        if scope_name == "ITEM" and type_name == "CHAIN":
            fields.add(str(name).lower())
    return fields


def _find_and_replace_in_syn(
    file_path: Path,
    pattern: re.Pattern,
    replacement: str,
    item_code_fields: set[str],
    item_chain_fields: set[str],
) -> list[TextEdit]:
    edits: list[TextEdit] = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Não foi possível ler {file_path}: {e}")
        return edits

    lines = content.splitlines()
    in_item = False
    current_code_field = False
    current_field_indent: Optional[int] = None

    for line_num, line in enumerate(lines):
        stripped = line.strip()

        if stripped.upper().startswith("ITEM "):
            in_item = True
            current_code_field = False
            current_field_indent = None
            continue

        if stripped.upper().startswith("END ITEM"):
            in_item = False
            current_code_field = False
            current_field_indent = None
            continue

        if not in_item:
            continue

        field_match = re.match(r"^(\s*)([\w._-]+)(\s*:)\s*(.*)$", line)
        if field_match:
            field_name = field_match.group(2).lower()
            current_code_field = (
                field_name in item_code_fields
                or field_name in item_chain_fields
            )
            current_field_indent = len(field_match.group(1)) if current_code_field else None
            if current_code_field:
                value = field_match.group(4)
                value_start = field_match.start(4)
                for match in pattern.finditer(value):
                    start_char = value_start + match.start()
                    end_char = value_start + match.end()
                    edits.append(
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=start_char),
                                end=Position(line=line_num, character=end_char),
                            ),
                            new_text=replacement,
                        )
                    )
            continue

        if not stripped or stripped.startswith("#"):
            continue

        if current_code_field:
            line_indent = len(line) - len(line.lstrip(" \t"))
            if current_field_indent is not None and line_indent <= current_field_indent:
                current_code_field = False
                current_field_indent = None
                continue
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


def _log_rename_summary(kind: str, old_value: str, new_value: str, changes: dict) -> None:
    try:
        file_count = len(changes)
        edit_count = sum(len(edits) for edits in changes.values())
    except Exception:
        file_count = 0
        edit_count = 0
    logger.info(
        "rename %s '%s' -> '%s': %s files, %s edits",
        kind,
        old_value,
        new_value,
        file_count,
        edit_count,
    )


def _find_and_replace_in_syno(
    file_path: Path,
    pattern: re.Pattern,
    replacement: str,
    ontology_code_fields: set[str],
) -> list[TextEdit]:
    edits: list[TextEdit] = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Não foi possível ler {file_path}: {e}")
        return edits

    lines = content.splitlines()
    in_ontology = False
    current_code_field = False
    current_field_indent: Optional[int] = None

    for line_num, line in enumerate(lines):
        stripped = line.strip()

        if stripped.upper().startswith("ONTOLOGY "):
            in_ontology = True
            current_code_field = False
            current_field_indent = None
            header_match = re.match(r"^(\s*ONTOLOGY\s+)(\S+)", line, flags=re.IGNORECASE)
            if header_match:
                value = header_match.group(2)
                for match in pattern.finditer(value):
                    start_char = header_match.start(2) + match.start()
                    end_char = header_match.start(2) + match.end()
                    edits.append(
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=start_char),
                                end=Position(line=line_num, character=end_char),
                            ),
                            new_text=replacement,
                        )
                    )
            continue

        if stripped.upper().startswith("END ONTOLOGY"):
            in_ontology = False
            current_code_field = False
            current_field_indent = None
            continue

        if not in_ontology:
            continue

        field_match = re.match(r"^(\s*)([\w._-]+)(\s*:)\s*(.*)$", line)
        if field_match:
            field_name = field_match.group(2).lower()
            current_code_field = field_name in ontology_code_fields
            current_field_indent = len(field_match.group(1)) if current_code_field else None
            if current_code_field:
                value = field_match.group(4)
                value_start = field_match.start(4)
                for match in pattern.finditer(value):
                    start_char = value_start + match.start()
                    end_char = value_start + match.end()
                    edits.append(
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=start_char),
                                end=Position(line=line_num, character=end_char),
                            ),
                            new_text=replacement,
                        )
                    )
            continue

        if not stripped or stripped.startswith("#"):
            current_code_field = False
            current_field_indent = None
            continue

        if current_code_field:
            line_indent = len(line) - len(line.lstrip(" \t"))
            if current_field_indent is not None and line_indent <= current_field_indent:
                current_code_field = False
                current_field_indent = None
                continue
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
    word_chars = re.compile(r"[@\w._-]")

    start = character
    while start > 0 and word_chars.match(line[start - 1]):
        start -= 1

    end = character
    while end < len(line) and word_chars.match(line[end]):
        end += 1

    return start, end
