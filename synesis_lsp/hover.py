"""
hover.py - Informação contextual ao passar o mouse (textDocument/hover)

Propósito:
    Fornece informação contextual para elementos Synesis quando o usuário
    posiciona o cursor sobre eles no editor.

Mapeamento de hover:
    @bibref       → Bibliografia (título, autor, ano, tipo)
    campo:        → Template FieldSpec (tipo, escopo, descrição)
    código/valor  → Ontologia (conceito, descrição, campos, uso)

Notas de implementação:
    - Depende do workspace_cache (Step 1) para dados do projeto compilado
    - Se cache vazio, retorna None (degradação graciosa)
    - Formata resposta como Markdown via MarkupContent
    - _get_word_at_position extrai a palavra sob o cursor
    - _is_field_name verifica se a palavra é nome de campo (seguida de ":")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lsprotocol.types import Hover, MarkupContent, MarkupKind, Position

logger = logging.getLogger(__name__)

# Caracteres válidos em palavras Synesis (bibrefs, campos, códigos)
# Inclui hífen e ponto para bibrefs compostos (ex: @martinez-gordon2022)
_WORD_CHARS = re.compile(r"[@\w._-]")


def compute_hover(
    source: str, position: Position, cached_result
) -> Optional[Hover]:
    """
    Computa hover baseado na posição do cursor.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor (0-based)
        cached_result: CachedCompilation do workspace_cache (pode ser None)

    Returns:
        Hover com MarkupContent ou None se nada encontrado
    """
    lines = source.splitlines()
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    word = _get_word_at_position(line, position.character)
    if not word:
        return None

    # 1. @bibref → bibliografia
    if word.startswith("@"):
        return _hover_bibref(word, cached_result)

    if not cached_result:
        return None

    result = cached_result.result
    template = getattr(result, "template", None)
    field_specs = getattr(template, "field_specs", None) if template else None

    field_name, value_start = _field_in_line(line)
    in_value = field_name is not None and position.character >= value_start
    spec = _find_field_spec(field_specs, field_name) if field_name else None
    spec_type = getattr(getattr(spec, "type", None), "name", None) if spec else None

    # Hover em nome de campo (qualquer tipo)
    if _is_field_name(line, position.character, word):
        return _hover_field(word, cached_result)

    block_hover = _hover_block(word, cached_result)
    if block_hover:
        return block_hover

    # Hover em valores apenas para CODE/CHAIN conforme template
    if spec_type in {"CODE", "CHAIN"} and in_value:
        if spec_type == "CHAIN":
            rel_hover = _hover_relation(word, cached_result)
            if rel_hover:
                return rel_hover
        return _hover_code(word, cached_result)

    return None


def _hover_bibref(word: str, cached_result) -> Optional[Hover]:
    """Hover para @bibref: mostra dados bibliográficos."""
    if not cached_result:
        return None

    result = cached_result.result
    bibliography = getattr(result, "bibliography", None)
    if not bibliography:
        return None

    # Remove @ para buscar na bibliografia
    bibref = word[1:]

    # Tenta busca direta e normalizada (lowercase)
    entry = bibliography.get(bibref) or bibliography.get(bibref.lower())
    if not entry:
        return None

    title = entry.get("title", "N/A")
    author = entry.get("author", "N/A")
    year = entry.get("year", "N/A")
    entry_type = entry.get("ENTRYTYPE", "N/A")

    md = f"**{title}**\n\n"
    md += f"*{author}* ({year})\n\n"
    md += f"Type: `{entry_type}`"

    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))


def _hover_field(word: str, cached_result) -> Optional[Hover]:
    """Hover para campo: mostra especificação do template."""
    if not cached_result:
        return None

    result = cached_result.result
    template = getattr(result, "template", None)
    if not template:
        return None

    field_specs = getattr(template, "field_specs", None)
    if not field_specs:
        return None

    spec = _find_field_spec(field_specs, word)
    if not spec:
        return None

    md = f"**Campo: `{spec.name}`**\n\n"
    md += f"- Tipo: `{spec.type.name}`\n"
    md += f"- Escopo: `{spec.scope.name}`\n"
    if spec.description:
        md += f"- Descrição: {spec.description}\n"

    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))


def _normalize_code(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def _hover_code(word: str, cached_result) -> Optional[Hover]:
    """Hover para código: mostra ontologia e contagem de uso."""
    if not cached_result:
        return None

    result = cached_result.result
    lp = getattr(result, "linked_project", None)
    if not lp:
        return None

    ontology_index = getattr(lp, "ontology_index", None)
    if not ontology_index:
        return None

    normalized = _normalize_code(word)
    onto = ontology_index.get(word) or ontology_index.get(normalized)
    if not onto:
        return None

    code_usage = getattr(lp, "code_usage", {})
    usage_count = len(code_usage.get(normalized, code_usage.get(word, [])))

    md = f"**Ontologia: `{onto.concept}`**\n\n"
    if onto.description:
        md += f"{onto.description}\n\n"

    fields = getattr(onto, "fields", {})
    for k, v in fields.items():
        # Trunca valores longos
        val = str(v)[:80]
        md += f"- {k}: {val}\n"

    md += f"\nUsado em **{usage_count}** itens"

    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))


def _hover_relation(word: str, cached_result) -> Optional[Hover]:
    """Hover para relações de CHAIN (ex: ENABLES, INFLUENCES)."""
    if not cached_result:
        return None

    result = cached_result.result
    template = getattr(result, "template", None)
    if not template:
        return None

    field_specs = getattr(template, "field_specs", None)
    if not field_specs:
        return None

    target = word.strip().lower()
    for spec in field_specs.values():
        relations = getattr(spec, "relations", None)
        if not relations:
            continue
        for key, description in relations.items():
            if str(key).strip().lower() == target:
                md = f"**Relação: `{key}`**\n\n"
                if description:
                    md += f"{description}\n"
                return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))

    return None


def _find_field_spec(field_specs, name: Optional[str]):
    if not field_specs or not name:
        return None
    spec = field_specs.get(name)
    if spec:
        return spec
    lowered = str(name).lower()
    for key, value in field_specs.items():
        if str(key).lower() == lowered:
            return value
    return None


def _hover_block(word: str, cached_result) -> Optional[Hover]:
    if not cached_result:
        return None

    block = word.strip().upper()
    if block not in {"SOURCE", "ITEM", "ONTOLOGY"}:
        return None

    result = cached_result.result
    template = getattr(result, "template", None)
    field_specs = getattr(template, "field_specs", None) if template else None
    if not field_specs:
        return None

    fields = []
    for spec in field_specs.values():
        scope = getattr(spec, "scope", None)
        scope_name = getattr(scope, "name", None) or str(scope or "")
        scope_name = scope_name.split(".")[-1].upper()
        if scope_name == block:
            fields.append(spec)

    if not fields:
        return None

    fields.sort(key=lambda entry: str(entry.name).lower())
    preview = fields[:10]

    md = f"**Bloco {block}**\n\n"
    md += f"Campos definidos ({len(fields)}):\n"
    for spec in preview:
        type_name = getattr(spec.type, "name", str(spec.type))
        md += f"- `{spec.name}` ({type_name})\n"

    if len(fields) > len(preview):
        md += f"... e mais {len(fields) - len(preview)} campos"

    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))


def _get_word_at_position(line: str, character: int) -> Optional[str]:
    """
    Extrai a palavra na posição do cursor.

    Expande para esquerda e direita a partir do cursor,
    incluindo caracteres de palavra e @.
    """
    if character >= len(line):
        return None

    # Verifica se o cursor está sobre um caractere válido
    if not _WORD_CHARS.match(line[character]):
        return None

    # Expande para a esquerda
    start = character
    while start > 0 and _WORD_CHARS.match(line[start - 1]):
        start -= 1

    # Expande para a direita
    end = character
    while end < len(line) and _WORD_CHARS.match(line[end]):
        end += 1

    word = line[start:end]
    return word if word else None


def _field_in_line(line: str) -> tuple[Optional[str], int]:
    """
    Retorna (field_name, value_start_index) se a linha contém 'field: value'.
    Caso contrário, retorna (None, 0).
    """
    match = re.match(r"^(\s*)([\w._-]+)(\s*:)\s*(.*)$", line)
    if not match:
        return (None, 0)
    field_name = match.group(2)
    value_start = match.start(4)
    return (field_name, value_start)


def _is_field_name(line: str, character: int, word: str) -> bool:
    """
    Verifica se a palavra é um nome de campo (seguida de ':').

    Ex: '    ordem_1a: valor' → True para 'ordem_1a'
    """
    # Encontra a posição da palavra na linha
    word_end = character
    while word_end < len(line) and _WORD_CHARS.match(line[word_end]):
        word_end += 1

    # Verifica se há ':' após a palavra (possivelmente com espaços)
    rest = line[word_end:].lstrip()
    return rest.startswith(":")
