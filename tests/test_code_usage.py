"""
test_code_usage.py - Uso de conceitos, incluindo os que só aparecem em CHAIN

`LinkedProject.code_usage` indexa apenas campos CODE. Um conceito usado somente
numa CHAIN não tem entrada, e quem lê esse dicionário cru relata zero — era o
caso de hover, completion, references e graph.

`build_code_usage` é a fonte única: cobre CODE e CHAIN, normaliza as chaves e
soma os ITEMs distintos de um conceito presente nas duas formas.
"""

from __future__ import annotations

import pytest
import synesis

from synesis_lsp.code_usage import build_code_usage, usage_count, usage_items
from synesis_lsp.explorer_requests import get_codes

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

ONTOLOGY Sem_Uso
    definition: Conceito declarado e nao usado
END ONTOLOGY
"""

# Aceitacao_Social: 1 CODE + 1 CHAIN (ITEMs distintos) -> 2
# Percepcao_Risco : só CHAIN                            -> 1
# Sem_Uso         : declarado, nunca usado              -> 0
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
def lp_fs(projeto):
    result, _ = projeto
    return result.linked_project, getattr(result.template, "field_specs", {})


# ------------------------------------------------------------ o defeito

def test_conceito_usado_apenas_em_chain(lp_fs):
    """O teste que prova a correção: `lp.code_usage` cru devolveria 0."""
    lp, fs = lp_fs
    assert usage_count(lp, "Percepcao_Risco", fs) == 1


def test_code_usage_cru_nao_tem_o_conceito_de_chain(lp_fs):
    """Documenta a razão de o módulo existir."""
    lp, _ = lp_fs
    cru = getattr(lp, "code_usage", {}) or {}
    assert "percepcao_risco" not in cru


def test_conceito_em_code_e_chain_soma(lp_fs):
    """1 CODE + 1 CHAIN em ITEMs distintos = 2, não 1."""
    lp, fs = lp_fs
    assert usage_count(lp, "Aceitacao_Social", fs) == 2


def test_conceito_usado_apenas_em_code(lp_fs):
    lp, fs = lp_fs
    usage = build_code_usage(lp, fs)
    assert len(usage.get("aceitacao_social", [])) == 2


def test_conceito_declarado_sem_uso(lp_fs):
    """Zero legítimo — não é o mesmo defeito."""
    lp, fs = lp_fs
    assert usage_count(lp, "Sem_Uso", fs) == 0


# --------------------------------------------------- normalização de chaves

def test_chaves_normalizadas(lp_fs):
    """Sem normalizar, `Aceitacao_Social` e `aceitacao_social` coexistiriam."""
    lp, fs = lp_fs
    usage = build_code_usage(lp, fs)
    assert set(usage) == {"aceitacao_social", "percepcao_risco"}


@pytest.mark.parametrize(
    "grafia", ["Aceitacao_Social", "aceitacao_social", "ACEITACAO_SOCIAL", "  Aceitacao_Social  "]
)
def test_consulta_insensivel_a_caixa_e_espacos(lp_fs, grafia):
    lp, fs = lp_fs
    assert usage_count(lp, grafia, fs) == 2


# ------------------------------------------------------------- paridade

def test_concorda_com_get_codes(projeto, lp_fs):
    """
    `get_codes` era o único consumidor correto. O módulo tem de reproduzi-lo —
    é o que impede a divergência de voltar por um caminho novo.
    """
    result, tmp_path = projeto
    lp, fs = lp_fs

    esperado = {c["code"]: c["usageCount"] for c in get_codes(_Cached(result, tmp_path))["codes"]}
    obtido = {k: len(v) for k, v in build_code_usage(lp, fs).items()}

    for code, count in obtido.items():
        assert esperado.get(code) == count, f"divergência em {code}"


# -------------------------------------------------------------- robustez

def test_sem_field_specs_nao_lanca(lp_fs):
    """Chains ainda são varridas pelos nomes de campo convencionais."""
    lp, _ = lp_fs
    usage = build_code_usage(lp, None)
    assert isinstance(usage, dict)
    assert usage.get("percepcao_risco")


def test_lp_sem_code_usage_cai_nos_sources(lp_fs):
    """Sem o índice do compilador, o uso é reconstruído dos sources."""
    lp, fs = lp_fs

    class _SemUsage:
        sources = lp.sources

    usage = build_code_usage(_SemUsage(), fs)
    assert usage.get("aceitacao_social")
    assert usage.get("percepcao_risco")


def test_conceito_vazio_ou_none(lp_fs):
    lp, fs = lp_fs
    assert usage_count(lp, "", fs) == 0
    assert usage_count(lp, None, fs) == 0
    assert usage_items(lp, "", fs) == []


def test_conceito_inexistente(lp_fs):
    lp, fs = lp_fs
    assert usage_count(lp, "NaoExisteEmLugarNenhum", fs) == 0


def test_usage_items_devolve_os_items(lp_fs):
    lp, fs = lp_fs
    items = usage_items(lp, "Percepcao_Risco", fs)
    assert len(items) == 1
    assert getattr(items[0], "location", None) is not None


def test_itens_nao_duplicam(lp_fs):
    """Um ITEM que cite o conceito em CODE e em CHAIN conta uma vez só."""
    lp, fs = lp_fs
    for items in build_code_usage(lp, fs).values():
        ids = [id(i) for i in items]
        assert len(ids) == len(set(ids))
