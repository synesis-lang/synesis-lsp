"""
code_usage.py - Uso de conceitos por ITEM, incluindo os que só aparecem em CHAIN

Propósito:
    Fonte única de verdade para "quantos/quais ITEMs usam este conceito".

Por que existe:
    `LinkedProject.code_usage`, montado pelo compilador, indexa **apenas campos
    do tipo CODE**. Um conceito usado somente numa CHAIN não tem entrada ali.
    Quem lê esse dicionário cru relata zero:

        hover        → "Usado em 0 itens"
        completion   → usageCount subestimado
        references   → Find All References não acha a ocorrência
        graph        → conceito omitido do grafo

    `explorer_requests.get_codes` era o único consumidor correto, porque
    complementava com as chains e normalizava as chaves em seguida. Este módulo
    extrai essa lógica para que todos os consumidores partam do mesmo lugar —
    copiar o trecho para cada um é exatamente o que produziu a divergência.

Contrato:
    As chaves são **normalizadas** (`normalize_code`) e os itens deduplicados
    por identidade. Um conceito usado em CODE e em CHAIN aparece uma vez, com a
    soma dos ITEMs distintos.
"""

from __future__ import annotations

from typing import Optional

from synesis.ast.normalize import normalize_code


def build_code_usage(lp, field_specs: Optional[dict] = None) -> dict[str, list]:
    """
    Mapeia conceito normalizado → lista de ITEMs que o usam.

    Cobre campos CODE e CHAIN. Diferentemente de `lp.code_usage`, a chave é
    normalizada e um conceito presente nas duas formas tem os ITEMs somados
    (sem repetir o mesmo ITEM).

    Args:
        lp: LinkedProject
        field_specs: field_specs do template. **Passe sempre que disponível.**
            Sem ele não há como distinguir os nós de uma chain dos nomes de
            RELAÇÃO que os ligam, e `CAUSES`/`ENABLES` entram no resultado como
            se fossem conceitos. Todos os chamadores em produção têm acesso ao
            template; o default `None` existe só para uso em teste.

    Returns:
        dict {conceito_normalizado: [ItemNode, ...]}
    """
    # Import tardio: os helpers vivem em explorer_requests, que não importa este
    # módulo — o import no topo criaria ciclo quando explorer_requests delegar.
    from synesis_lsp.explorer_requests import (
        _build_code_usage_from_sources,
        _raw_code_usage,
    )

    usage: dict[str, list] = {}

    raw = _raw_code_usage(lp)
    if raw:
        for code, items in raw.items():
            _merge(usage, normalize_code(code), items)

    # Chains não entram em lp.code_usage — daí a complementação. Quando `raw`
    # está vazio, esta chamada cobre CODE e CHAIN de uma vez.
    from_sources = _build_code_usage_from_sources(
        lp,
        field_specs,
        include_code=not raw,
        include_chain=True,
    )
    for code, items in from_sources.items():
        _merge(usage, normalize_code(code), items)

    return usage


def usage_count(lp, concept: str, field_specs: Optional[dict] = None) -> int:
    """Quantos ITEMs usam `concept`. Conveniência para hover/completion."""
    if not concept:
        return 0
    return len(build_code_usage(lp, field_specs).get(normalize_code(concept), []))


def usage_items(lp, concept: str, field_specs: Optional[dict] = None) -> list:
    """ITEMs que usam `concept`. Conveniência para references."""
    if not concept:
        return []
    return build_code_usage(lp, field_specs).get(normalize_code(concept), [])


def _merge(usage: dict[str, list], key: str, items) -> None:
    """
    Acrescenta `items` a `usage[key]`, sem repetir o mesmo ITEM.

    A deduplicação é por identidade de objeto: um ITEM que cite o conceito num
    campo CODE **e** numa CHAIN é um único uso, não dois. Comparar por valor não
    serve — ItemNode não define igualdade estrutural.
    """
    if not key or not items:
        return

    bucket = usage.setdefault(key, [])
    seen = {id(existing) for existing in bucket}
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            bucket.append(item)
