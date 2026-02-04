"""
template_diagnostics.py - Diagnosticos baseados em template (fallback)

Proposito:
    Fornecer diagnosticos minimos para arquivos .syn quando o compilador
    nao reporta campos desconhecidos/obrigatorios. Usa o template do projeto
    para checar nomes de campos e escopos.

Notas:
    - Implementacao heuristica (parse por linhas)
    - Nao substitui o compilador; apenas complementa quando necessario
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

_BLOCK_RE = re.compile(r"^\s*(SOURCE|ITEM|ONTOLOGY)\b")
_END_RE = re.compile(r"^\s*END\b")
_FIELD_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*:")

_COMMAND_RE = re.compile(r"^\s*([A-Z][A-Z_]*)(?:\s+([A-Z_]+))?\b")


def build_template_diagnostics(
    source: str,
    uri: str,
    template,
    existing_field_errors: Optional[set[tuple[str, Optional[str]]]] = None,
) -> list[Diagnostic]:
    """
    Gera diagnosticos de campo com base no template.

    Args:
        source: Texto do documento.
        uri: URI do documento (para filtrar .syn).
        template: TemplateNode com field_specs/required_fields/bundled_fields.
        existing_field_errors: set de (field_name, block_type) já reportados.
    """
    if not _is_syn_document(uri):
        return []
    if not template:
        return []

    existing_field_errors = existing_field_errors or set()

    field_specs = getattr(template, "field_specs", {}) or {}
    required_by_scope = _scope_to_fields(getattr(template, "required_fields", {}) or {})
    bundled_by_scope = _scope_to_bundles(getattr(template, "bundled_fields", {}) or {})
    forbidden_by_scope = _scope_to_fields(getattr(template, "forbidden_fields", {}) or {})

    diagnostics: list[Diagnostic] = []
    blocks = _parse_blocks(source)

    for block in blocks:
        scope = block["scope"]
        fields = block["fields"]

        for field_name, (line, column) in fields.items():
            field_key = (field_name, scope)
            if field_key in existing_field_errors:
                continue

            spec = field_specs.get(field_name)
            if not spec:
                message = _unknown_field_message(field_name, field_specs.keys())
                diagnostics.append(_make_diag(line, column, message))
                continue

            spec_scope = _scope_name(getattr(spec, "scope", None))
            if spec_scope and spec_scope != scope:
                message = (
                    f"Campo '{field_name}' nao e permitido em {scope}. "
                    f"Escopo esperado: {spec_scope}."
                )
                diagnostics.append(_make_diag(line, column, message))
                continue

            forbidden = set(forbidden_by_scope.get(scope, []))
            if field_name in forbidden:
                message = f"Campo '{field_name}' e proibido em {scope}."
                diagnostics.append(_make_diag(line, column, message))

        required_fields = set(required_by_scope.get(scope, []))
        missing = required_fields - set(fields.keys())
        for field_name in sorted(missing):
            field_key = (field_name, scope)
            if field_key in existing_field_errors:
                continue
            message = f"Campo obrigatorio ausente em {scope}: '{field_name}'."
            diagnostics.append(_make_diag(block["line"], 1, message))

        bundle_pairs = bundled_by_scope.get(scope, [])
        for a, b in bundle_pairs:
            a_present = a in fields
            b_present = b in fields
            if a_present ^ b_present:
                message = (
                    f"Bundle incompleto em {scope}: "
                    f"'{a}' e '{b}' devem aparecer juntos."
                )
                diagnostics.append(_make_diag(block["line"], 1, message))

    return diagnostics


def build_command_diagnostics(source: str, uri: str) -> list[Diagnostic]:
    """
    Gera avisos para comandos inválidos (palavras reservadas).
    """
    file_kind = _file_kind(uri)
    allowed = _allowed_commands(file_kind)
    if not allowed:
        return []

    diagnostics: list[Diagnostic] = []
    for line_idx, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            continue

        match = _COMMAND_RE.match(line)
        if not match:
            continue

        first = match.group(1) or ""
        second = match.group(2) or ""
        command = f"{first} {second}".strip() if first == "END" else first

        if command not in allowed:
            message = (
                f"Comando invalido '{command}'. "
                f"Esperado: {', '.join(sorted(allowed))}."
            )
            diagnostics.append(_make_diag(line_idx, match.start(1) + 1, message, DiagnosticSeverity.Warning))

    return diagnostics


def _is_syn_document(uri: str) -> bool:
    if not uri:
        return False
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = unquote(parsed.path or "")
    else:
        path = uri
    return path.lower().endswith(".syn")


def _file_kind(uri: str) -> str:
    if not uri:
        return ""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = unquote(parsed.path or "")
    else:
        path = uri
    lower = path.lower()
    if lower.endswith(".syn"):
        return "syn"
    if lower.endswith(".syno"):
        return "syno"
    if lower.endswith(".synt"):
        return "synt"
    if lower.endswith(".synp"):
        return "synp"
    return ""


def _allowed_commands(kind: str) -> set[str]:
    if kind == "syn":
        return {
            "SOURCE",
            "ITEM",
            "END SOURCE",
            "END ITEM",
        }
    if kind == "syno":
        return {
            "ONTOLOGY",
            "END ONTOLOGY",
        }
    if kind == "synp":
        return {
            "PROJECT",
            "END PROJECT",
            "TEMPLATE",
            "INCLUDE",
            "METADATA",
            "END METADATA",
            "DESCRIPTION",
            "END DESCRIPTION",
        }
    if kind == "synt":
        return {
            "TEMPLATE",
            "PROJECT",
            "END PROJECT",
            "SOURCE",
            "ITEM",
            "ONTOLOGY",
            "END SOURCE",
            "END ITEM",
            "END ONTOLOGY",
            "FIELD",
            "END FIELD",
            "VALUES",
            "END VALUES",
            "RELATIONS",
            "END RELATIONS",
            "SCOPE",
            "TYPE",
            "DESCRIPTION",
            "FORMAT",
            "ARITY",
            "REQUIRED",
            "OPTIONAL",
            "FORBIDDEN",
            "BUNDLE",
        }
    return set()


def _parse_blocks(source: str) -> list[dict]:
    blocks: list[dict] = []
    current = None
    for idx, line in enumerate(source.splitlines()):
        block_match = _BLOCK_RE.match(line)
        if block_match:
            current = {"scope": block_match.group(1), "fields": {}, "line": idx}
            blocks.append(current)
            continue
        if current and _END_RE.match(line):
            current = None
            continue
        if not current:
            continue
        field_match = _FIELD_RE.match(line)
        if field_match:
            field = field_match.group(1)
            column = line.find(field) + 1  # 1-based
            current["fields"][field] = (idx, column)
    return blocks


def _scope_name(scope) -> Optional[str]:
    if not scope:
        return None
    name = getattr(scope, "name", None)
    if name:
        return str(name).upper()
    return str(scope).split(".")[-1].upper()


def _scope_to_fields(mapping) -> dict[str, list[str]]:
    scoped: dict[str, list[str]] = {}
    for scope, fields in mapping.items():
        name = _scope_name(scope)
        if not name:
            continue
        if isinstance(fields, (set, tuple)):
            scoped[name] = list(fields)
        else:
            scoped[name] = list(fields or [])
    return scoped


def _scope_to_bundles(mapping) -> dict[str, list[tuple[str, str]]]:
    scoped: dict[str, list[tuple[str, str]]] = {}
    for scope, bundles in mapping.items():
        name = _scope_name(scope)
        if not name:
            continue
        pairs: list[tuple[str, str]] = []
        for bundle in bundles or []:
            if isinstance(bundle, (list, tuple)) and len(bundle) >= 2:
                pairs.append((bundle[0], bundle[1]))
        scoped[name] = pairs
    return scoped


def _unknown_field_message(field_name: str, known_fields: Iterable[str]) -> str:
    suggestions = difflib.get_close_matches(field_name, list(known_fields), n=3, cutoff=0.6)
    if suggestions:
        return f"Campo desconhecido '{field_name}'. Voce quis dizer: {', '.join(suggestions)}?"
    return f"Campo desconhecido '{field_name}'."


def _make_diag(line: int, column: int, message: str, severity: DiagnosticSeverity = DiagnosticSeverity.Error) -> Diagnostic:
    line = max(0, line)
    column = max(1, column)
    start = Position(line=line, character=column - 1)
    end = Position(line=line, character=column)
    return Diagnostic(
        range=Range(start=start, end=end),
        severity=severity,
        source="synesis-lsp",
        message=message,
    )
