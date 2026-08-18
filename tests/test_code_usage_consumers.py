"""
test_code_usage_consumers.py - Consumidores concordam sobre o uso de conceitos

`hover`, `completion`, `references` e `graph` liam `lp.code_usage` cru, que
indexa apenas campos CODE. Um conceito usado só em CHAIN aparecia como zero em
todos eles, enquanto `getCodes` — único consumidor correto — reportava o número
certo.

O teste de concordância (`test_todos_os_consumidores_concordam`) é o que impede
a divergência de voltar por um caminho novo: qualquer consumidor que passe a ler
o dicionário cru volta a discordar dos demais.
"""

from __future__ import annotations

import pytest
import synesis
from lsprotocol.types import Position

from synesis_lsp.code_usage import build_code_usage, usage_count
from synesis_lsp.completion import compute_completions
from synesis_lsp.explorer_requests import get_codes
from synesis_lsp.graph import _codes_for_bibref
from synesis_lsp.hover import compute_hover
from synesis_lsp.references import compute_references

TEMPLATE = """\
TEMPLATE t

SOURCE FIELDS
    OPTIONAL description
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation
    OPTIONAL code
    OPTIONAL chain
END ITEM FIELDS

ONTOLOGY FIELDS
    OPTIONAL definition
END ONTOLOGY FIELDS

FIELD description TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD code TYPE CODE
    SCOPE ITEM
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        CAUSES: relacao causal
    END RELATIONS
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

BIB = "@article{silva2020, title={E}, author={S, M}, year={2020}}\n"

ONTOLOGY = """\
ONTOLOGY Aceitacao_Social
    definition: Aprovacao publica
END ONTOLOGY

ONTOLOGY Percepcao_Risco
    definition: Avaliacao de ameaca
END ONTOLOGY
"""

# Aceitacao_Social: CODE + CHAIN -> 2 | Percepcao_Risco: só CHAIN -> 1
SYN = """\
SOURCE @silva2020
    description: Fonte
END SOURCE

ITEM @silva2020
    citation: "usa code"
    code: Aceitacao_Social
END ITEM

ITEM @silva2020
    citation: "usa chain"
    chain: Percepcao_Risco -> CAUSES -> Aceitacao_Social
END ITEM
"""

SO_EM_CHAIN = "Percepcao_Risco"
EM_CODE_E_CHAIN = "Aceitacao_Social"


class _Cached:
    def __init__(self, result, workspace_root):
        self.result = result
        self.workspace_root = workspace_root


@pytest.fixture
def projeto(tmp_path):
    (tmp_path / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "t.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "t.syno").write_text(ONTOLOGY, encoding="utf-8")
    (tmp_path / "t.syn").write_text(SYN, encoding="utf-8")
    (tmp_path / "t.synp").write_text(
        'PROJECT t\n'
        '    TEMPLATE "t.synt"\n'
        '    INCLUDE BIBLIOGRAPHY "t.bib"\n'
        '    INCLUDE ANNOTATIONS "t.syn"\n'
        '    INCLUDE ONTOLOGY "t.syno"\n'
        'END PROJECT\n',
        encoding="utf-8",
    )
    result = synesis.SynesisCompiler(tmp_path / "t.synp").compile()
    assert result.success, "fixture deve compilar limpa"
    return result, tmp_path


@pytest.fixture
def ctx(projeto):
    result, tmp_path = projeto
    return {
        "cached": _Cached(result, tmp_path),
        "lp": result.linked_project,
        "field_specs": getattr(result.template, "field_specs", {}),
        "src": SYN,
        "root": tmp_path,
    }


def _pos_do_conceito(src: str, conceito: str) -> Position:
    for i, linha in enumerate(src.splitlines()):
        if conceito in linha:
            return Position(line=i, character=linha.index(conceito) + 2)
    raise AssertionError(f"{conceito} não encontrado na fixture")


def _pos_fim_da_linha(src: str, prefixo: str) -> Position:
    """Fim da primeira linha que começa (após indentação) com `prefixo`.

    O completion só sugere conceitos com o cursor no VALOR do campo; apontar
    para o nome do campo devolve outra lista.
    """
    for i, linha in enumerate(src.splitlines()):
        if linha.strip().startswith(prefixo):
            return Position(line=i, character=len(linha))
    raise AssertionError(f"linha iniciada por {prefixo!r} não encontrada")


# ------------------------------------------------- conceito usado só em CHAIN

def test_hover_conta_conceito_de_chain(ctx):
    """Antes: 'Usado em 0 itens'."""
    hover = compute_hover(ctx["src"], _pos_do_conceito(ctx["src"], SO_EM_CHAIN), ctx["cached"])
    assert hover is not None
    assert "Usado em **1** itens" in hover.contents.value


def test_references_acha_ocorrencia_em_chain(ctx):
    """Antes: None — o pesquisador concluía que o conceito não era usado."""
    refs = compute_references(ctx["cached"], SO_EM_CHAIN, ctx["root"], False)
    assert refs and len(refs) == 1


def test_completion_conta_conceito_de_chain(ctx):
    comp = compute_completions(ctx["src"], _pos_fim_da_linha(ctx["src"], "code:"), ctx["cached"])
    detalhes = {i.label: i.detail for i in comp.items if i.detail and "Ontologia" in i.detail}
    assert detalhes.get("percepcao_risco") == "Ontologia (1 usos)"


def test_graph_inclui_conceito_de_chain(ctx):
    """Antes: omitido — o Stage 1 devolvia resultado parcial e retornava cedo."""
    codes = _codes_for_bibref(ctx["lp"], "silva2020", ctx["field_specs"])
    assert "percepcao_risco" in codes


# --------------------------------------------- conceito em CODE e CHAIN soma

def test_hover_soma_code_e_chain(ctx):
    hover = compute_hover(
        ctx["src"], _pos_do_conceito(ctx["src"], EM_CODE_E_CHAIN), ctx["cached"]
    )
    assert "Usado em **2** itens" in hover.contents.value


def test_completion_soma_code_e_chain(ctx):
    comp = compute_completions(ctx["src"], _pos_fim_da_linha(ctx["src"], "code:"), ctx["cached"])
    detalhes = {i.label: i.detail for i in comp.items if i.detail and "Ontologia" in i.detail}
    assert detalhes.get("aceitacao_social") == "Ontologia (2 usos)"


# ----------------------------------------------------------- concordância

def test_todos_os_consumidores_concordam(ctx):
    """
    O teste central da fase: cinco caminhos, um número.

    Se algum consumidor voltar a ler `lp.code_usage` cru, este teste falha.
    """
    cached, lp, fs = ctx["cached"], ctx["lp"], ctx["field_specs"]
    esperado = {c["code"]: c["usageCount"] for c in get_codes(cached)["codes"]}

    for conceito, chave in ((SO_EM_CHAIN, "percepcao_risco"), (EM_CODE_E_CHAIN, "aceitacao_social")):
        n = esperado[chave]

        assert usage_count(lp, conceito, fs) == n
        assert len(build_code_usage(lp, fs).get(chave, [])) == n

        hover = compute_hover(ctx["src"], _pos_do_conceito(ctx["src"], conceito), cached)
        assert f"Usado em **{n}** itens" in hover.contents.value

        refs = compute_references(cached, conceito, ctx["root"], False)
        assert len(refs or []) == n


# ------------------------------------------------------------- regressões

def test_relacao_nao_vira_conceito(ctx):
    """
    `CAUSES` é uma relação, não um conceito.

    Sem `field_specs`, a varredura de chains não distingue os nós dos nomes de
    relação que os ligam — e `causes` entrava no resultado como se fosse um
    conceito codificado.
    """
    codes = _codes_for_bibref(ctx["lp"], "silva2020", ctx["field_specs"])
    assert "causes" not in codes
    assert build_code_usage(ctx["lp"], ctx["field_specs"]).get("causes") is None


def test_hover_de_conceito_sem_uso_nao_quebra(ctx):
    """Zero legítimo continua zero."""
    assert usage_count(ctx["lp"], "ConceitoInexistente", ctx["field_specs"]) == 0


def test_get_codes_inalterado(ctx):
    """Não-regressão do único consumidor que já estava correto."""
    codes = {c["code"]: c["usageCount"] for c in get_codes(ctx["cached"])["codes"]}
    assert codes["aceitacao_social"] == 2
    assert codes["percepcao_risco"] == 1
