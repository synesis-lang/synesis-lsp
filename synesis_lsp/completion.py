"""
completion.py - Autocomplete para bibrefs, códigos, campos e blocos

Propósito:
    Fornece sugestões de completamento contextual:
    - Após @: bibrefs da bibliography
    - Códigos da ontologia (ontology_index)
    - Campos do template (field_specs)
    - Blocos SOURCE/ITEM/ONTOLOGY já preenchidos com os campos obrigatórios
      DAQUELE projeto (snippet)

Notas de implementação:
    - Depende do workspace_cache para dados do projeto compilado
    - trigger_char="@" ativa sugestões de bibrefs
    - Sem cache, retorna lista vazia
    - CompletionItemKind: Reference (bibrefs), EnumMember (códigos),
      Property (campos), Snippet (blocos)

Por que os blocos vivem aqui, e não em snippets estáticos da extensão:
    quais campos um bloco SOURCE exige depende do TEMPLATE do projeto aberto
    (`linkedin` pede slug+nome; `lattes` pede lattes_id+nome+cargo). Um arquivo
    .code-snippets é estático e não teria como saber. O LSP tem o template
    carregado, então gera o bloco certo para o projeto em questão.
"""

from __future__ import annotations

import logging
from typing import Optional

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    InsertTextFormat,
    Position,
)

logger = logging.getLogger(__name__)

#: Blocos de anotação e o atributo de TemplateNode que lista seus campos.
_ANNOTATION_BLOCKS = ("SOURCE", "ITEM", "ONTOLOGY")


def compute_completions(
    source: str,
    position: Position,
    cached_result,
    trigger_char: Optional[str] = None,
) -> CompletionList:
    """
    Computa lista de completamento.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor (0-based)
        cached_result: CachedCompilation do workspace_cache
        trigger_char: Caractere que disparou o completion (ex: "@")

    Returns:
        CompletionList com sugestões contextuais
    """
    if not cached_result:
        return CompletionList(is_incomplete=False, items=[])

    result = cached_result.result
    items: list[CompletionItem] = []

    lines = source.splitlines()
    line = lines[position.line] if position.line < len(lines) else ""

    # Após @: sugerir bibrefs
    if trigger_char == "@" or _is_after_at(line, position.character):
        bib = getattr(result, "bibliography", None) or {}
        for bibref, entry in bib.items():
            author = entry.get("author", "?")
            year = entry.get("year", "?")
            items.append(
                CompletionItem(
                    label=f"@{bibref}",
                    kind=CompletionItemKind.Reference,
                    detail=f"{author} ({year})",
                    insert_text=bibref,
                )
            )

    template = getattr(result, "template", None)
    field_specs = getattr(template, "field_specs", {}) if template else {}

    field_name, value_start = _field_in_line(line)
    in_value = field_name is not None and position.character >= value_start
    spec = _find_field_spec(field_specs, field_name) if field_name else None
    spec_type = _get_spec_type_name(spec)
    in_code_context = bool(spec) and in_value and (
        spec_type == "CODE" or _is_chain_field(spec)
    )

    # Sugerir códigos da ontologia apenas em contexto CODE/CHAIN
    lp = getattr(result, "linked_project", None)
    if lp and in_code_context:
        ontology_index = getattr(lp, "ontology_index", {}) or {}
        code_usage = getattr(lp, "code_usage", {}) or {}
        for concept in ontology_index:
            usage_count = len(code_usage.get(concept, []))
            items.append(
                CompletionItem(
                    label=concept,
                    kind=CompletionItemKind.EnumMember,
                    detail=f"Ontologia ({usage_count} usos)",
                )
            )

    # Sugerir campos do template
    if field_specs:
        for name, spec in field_specs.items():
            type_name = getattr(spec.type, "name", str(spec.type))
            scope_name = getattr(spec.scope, "name", str(spec.scope))
            description = getattr(spec, "description", "") or ""
            items.append(
                CompletionItem(
                    label=f"{name}:",
                    kind=CompletionItemKind.Property,
                    detail=f"{type_name} ({scope_name})",
                    documentation=description,
                )
            )

    # Blocos de anotacao com os campos obrigatorios DESTE projeto.
    # Suprimidos quando um bloco inteiro nao faria sentido: dentro do valor de
    # um campo (`campo: ...`) e logo apos `@`, onde o usuario quer um bibref.
    after_at = trigger_char == "@" or _is_after_at(line, position.character)
    if template and not in_value and not after_at:
        for scope_name in _ANNOTATION_BLOCKS:
            block = _block_snippet(template, scope_name)
            if block is not None:
                items.append(block)

    return CompletionList(is_incomplete=False, items=items)


def _scope_fields(template, scope_name: str) -> tuple[list[str], list[str], list[tuple]]:
    """(obrigatorios, opcionais, bundles opcionais) de um escopo do template.

    As chaves de required_fields/optional_fields sao membros do enum Scope; a
    comparacao e por `.value`/nome para nao depender de importar o enum aqui
    (o LSP tolera versoes distintas do compilador).
    """
    def _pick(mapping) -> list:
        for key, value in (mapping or {}).items():
            key_name = getattr(key, "value", None) or getattr(key, "name", None) or str(key)
            if str(key_name).upper() == scope_name:
                return list(value or [])
        return []

    return (
        _pick(getattr(template, "required_fields", None)),
        _pick(getattr(template, "optional_fields", None)),
        _pick(getattr(template, "optional_bundles", None)),
    )


def _block_snippet(template, scope_name: str) -> Optional[CompletionItem]:
    """Monta o snippet de um bloco de anotacao para o template do projeto.

    Inclui os campos OBRIGATORIOS daquele escopo — que e a informacao que o
    pesquisador nao tem de cor e que muda de projeto para projeto. Opcionais
    ficam de fora para o bloco nao virar um formulario gigante; eles ja sao
    sugeridos individualmente pelo completion de campos.
    """
    required, optional, bundles = _scope_fields(template, scope_name)
    if not required and not optional:
        return None  # escopo nao declarado neste template

    # ONTOLOGY identifica o bloco por nome de conceito; os demais, por bibref.
    header_arg = "${1:nome_do_conceito}" if scope_name == "ONTOLOGY" else "@${1:bibref}"
    lines = [f"{scope_name} {header_arg}"]

    tab = 2
    for field in required:
        lines.append(f"    {field}: ${{{tab}:valor}}")
        tab += 1
    lines.append(f"END {scope_name}")
    lines.append("$0")

    if required:
        detail = f"{len(required)} campo(s) obrigatorio(s): " + ", ".join(required)
    else:
        detail = "sem campos obrigatorios neste template"

    documentation = detail
    if optional:
        documentation += "\n\nOpcionais: " + ", ".join(optional)
    if bundles:
        pairs = "; ".join("+".join(b) for b in bundles)
        documentation += f"\n\nBundles opcionais (tudo ou nada): {pairs}"

    return CompletionItem(
        label=f"{scope_name} (bloco)",
        kind=CompletionItemKind.Snippet,
        detail=detail,
        documentation=documentation,
        insert_text="\n".join(lines),
        insert_text_format=InsertTextFormat.Snippet,
        # Ordena os blocos antes dos campos soltos: quem digita "SOURCE"
        # quase sempre quer o bloco, nao um campo de nome parecido.
        sort_text=f"0_{scope_name}",
        filter_text=scope_name,
    )


def _is_after_at(line: str, character: int) -> bool:
    """Verifica se o cursor está logo após um '@'."""
    if character <= 0:
        return False
    # Busca o @ mais próximo à esquerda do cursor
    prefix = line[:character]
    # Verifica se o último caractere não-alfanumérico antes do cursor é @
    for i in range(len(prefix) - 1, -1, -1):
        ch = prefix[i]
        if ch == "@":
            return True
        if not ch.isalnum() and ch != "_":
            return False
    return False


def _field_in_line(line: str) -> tuple[Optional[str], int]:
    """
    Retorna (field_name, value_start_index) se a linha contém 'field: value'.
    Caso contrário, retorna (None, 0).
    """
    import re

    match = re.match(r"^(\s*)([\w._-]+)(\s*:)\s*(.*)$", line)
    if not match:
        return (None, 0)
    field_name = match.group(2)
    value_start = match.start(4)
    return (field_name, value_start)


def _get_spec_type_name(spec) -> Optional[str]:
    if not spec:
        return None
    spec_type = getattr(spec, "type", None)
    return getattr(spec_type, "name", None) or str(spec_type or "")


def _is_chain_field(spec) -> bool:
    if not spec:
        return False
    if getattr(spec, "relations", None):
        return True
    type_name = _get_spec_type_name(spec)
    return "CHAIN" in type_name.upper()


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
