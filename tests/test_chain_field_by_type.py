"""Campos CHAIN identificados pelo TIPO, não pelo nome `chain` (auditoria de 2026-10-09).

O parser só põe em `item.chains` os campos `chain`/`chains`; os demais CHAIN ficam
em `extra_fields` e já eram lidos pelo tipo. Faltava: a spec de `item.chains` vinha
de `field_specs.get("chain")` (um campo `chains` perdia as RELATIONS), e o grafo e
as estatísticas só consultavam o campo chamado `chain`.
"""

from types import SimpleNamespace

from synesis_lsp.explorer_requests import (
    _extract_chain_codes,
    _traditional_chain_spec,
    any_chain_has_relations,
)
from synesis_lsp.graph import _has_chain_relations


def _spec(tipo, relations=None):
    return SimpleNamespace(type=SimpleNamespace(name=tipo), relations=relations)


def test_spec_de_item_chains_aceita_chains_e_outra_caixa():
    specs = {"Chains": _spec("CHAIN", {"CAUSA": "x"}), "text": _spec("QUOTATION")}
    spec = _traditional_chain_spec(specs)
    assert spec is specs["Chains"]
    # com a spec certa, a relação não é lida como conceito
    cadeia = SimpleNamespace(nodes=["a", "CAUSA", "b"], relations=[])
    assert _extract_chain_codes(cadeia, spec) == ["a", "b"]


def test_campo_arbitrario_nao_e_a_spec_de_item_chains():
    assert _traditional_chain_spec({"relacoes": _spec("CHAIN", {"R": "x"})}) is None


def test_relacoes_em_qualquer_campo_chain():
    assert any_chain_has_relations({"relacoes": _spec("CHAIN", {"R": "x"})})
    assert not any_chain_has_relations({"ligacoes": _spec("CHAIN"), "texto": _spec("TEXT")})


def test_grafo_detecta_relacoes_em_chain_de_outro_nome():
    template = SimpleNamespace(field_specs={"relacoes": _spec("CHAIN", {"R": "x"})})
    assert _has_chain_relations(template)
    assert not _has_chain_relations(SimpleNamespace(field_specs={"ligacoes": _spec("CHAIN")}))
