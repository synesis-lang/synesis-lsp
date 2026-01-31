"""
signature_help.py - Ajuda de assinatura para campos Synesis

Propósito:
    Exibe definição do campo (tipo, escopo, descrição) durante
    preenchimento de valores. Trigger: após "campo:".

Notas de implementação:
    - Detecta padrão "campo:" na linha atual
    - Busca FieldSpec no template do projeto compilado
    - Retorna SignatureHelp com informações do campo
    - Se cache vazio ou campo desconhecido, retorna None
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lsprotocol.types import (
    ParameterInformation,
    SignatureHelp,
    SignatureInformation,
    Position,
)

logger = logging.getLogger(__name__)

# Regex para extrair nome do campo na linha (ex: "  tema: valor")
_FIELD_PATTERN = re.compile(r"^\s+(\w+)\s*:")


def compute_signature_help(
    source: str,
    position: Position,
    cached_result,
) -> Optional[SignatureHelp]:
    """
    Computa SignatureHelp para campo sendo preenchido.

    Args:
        source: Texto-fonte do documento
        position: Posição do cursor (0-based)
        cached_result: CachedCompilation do workspace_cache

    Returns:
        SignatureHelp com definição do campo, ou None
    """
    if not cached_result:
        return None

    lines = source.splitlines()
    if position.line >= len(lines):
        return None

    line = lines[position.line]

    # Detecta se estamos após "campo:"
    match = _FIELD_PATTERN.match(line)
    if not match:
        return None

    field_name = match.group(1)

    # Verifica se o cursor está após o ":"
    colon_pos = line.index(":", match.start(1))
    if position.character <= colon_pos:
        return None

    # Busca FieldSpec no template
    template = getattr(cached_result.result, "template", None)
    if not template:
        return None

    field_specs = getattr(template, "field_specs", {}) or {}
    spec = field_specs.get(field_name)
    if not spec:
        return None

    # Constrói informação da assinatura
    type_name = getattr(spec.type, "name", str(spec.type))
    scope_name = getattr(spec.scope, "name", str(spec.scope))
    description = getattr(spec, "description", "") or ""

    label = f"{field_name}: <{type_name}>"
    doc = f"**{field_name}**\n\n"
    doc += f"- Tipo: `{type_name}`\n"
    doc += f"- Escopo: `{scope_name}`\n"
    if description:
        doc += f"- Descrição: {description}\n"

    # Parâmetro: o valor esperado
    param = ParameterInformation(
        label=f"<{type_name}>",
        documentation=description or f"Valor do tipo {type_name}",
    )

    sig = SignatureInformation(
        label=label,
        documentation=doc,
        parameters=[param],
    )

    return SignatureHelp(
        signatures=[sig],
        active_signature=0,
        active_parameter=0,
    )
