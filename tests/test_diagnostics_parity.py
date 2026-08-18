"""
test_diagnostics_parity.py - Erros cross-file chegam ao editor

`validate_single_file` vê um arquivo por vez: erros que dependem da relação
entre blocos — ITEM sem SOURCE, conceito de ontologia duplicado — só existem no
linker, que roda na compilação do projeto. Como o resultado per-file era
publicado sozinho, esses diagnósticos nunca apareciam na tela, embora o
compilador os reportasse.

`_merge_project_diagnostics` acrescenta essas classes ao que o per-file produziu,
deduplicando e preservando a severidade de origem.
"""

from __future__ import annotations

import pytest
import synesis

import synesis_lsp.server as server
from synesis.lsp_adapter import validate_single_file
from synesis_lsp.converters import build_diagnostics
from synesis_lsp.server import _CROSS_FILE_CODES, _merge_project_diagnostics

TEMPLATE = """\
TEMPLATE t

SOURCE FIELDS
    OPTIONAL description
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation
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

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

BIB = (
    "@article{silva2020, title={E}, author={S, M}, year={2020}}\n"
    "@article{souza2019, title={O}, author={S, J}, year={2019}}\n"
)

BASE_SYN = """\
SOURCE @silva2020
    description: Fonte
END SOURCE

ITEM @silva2020
    citation: "trecho"
END ITEM
"""


class _Cached:
    def __init__(self, result, workspace_root):
        self.result = result
        self.workspace_root = workspace_root


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """Monta o projeto e injeta o cache que `_merge_project_diagnostics` consulta."""
    (tmp_path / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "t.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "t.synp").write_text(
        'PROJECT t\n'
        '    TEMPLATE "t.synt"\n'
        '    INCLUDE BIBLIOGRAPHY "t.bib"\n'
        '    INCLUDE ANNOTATIONS "t.syn"\n'
        'END PROJECT\n',
        encoding="utf-8",
    )

    def _publicar(extra: str = "") -> list:
        syn = tmp_path / "t.syn"
        syn.write_text(BASE_SYN + extra, encoding="utf-8")
        result = synesis.SynesisCompiler(tmp_path / "t.synp").compile()
        monkeypatch.setattr(
            server, "_get_cached_for_uri", lambda ls, uri: _Cached(result, tmp_path)
        )
        uri = syn.resolve().as_uri()
        per_file = build_diagnostics(
            validate_single_file(syn.read_text(encoding="utf-8"), uri, context=None)
        )
        return _merge_project_diagnostics(None, uri, per_file)

    return _publicar


def codes(diagnostics) -> list[str]:
    return [getattr(d, "code", None) for d in diagnostics]


# ------------------------------------------------ classes antes invisíveis

def test_item_sem_source_aparece(projeto):
    """O teste que prova a correção: antes, nenhum diagnóstico era publicado."""
    diags = projeto('\nITEM @orfao999\n    citation: "x"\nEND ITEM\n')
    assert "SYNESIS_E002" in codes(diags)


def test_source_sem_items_aparece(projeto):
    """Bibref VÁLIDO no .bib — senão UnregisteredSource (erro) mascara o caso."""
    diags = projeto("\nSOURCE @souza2019\n    description: sem items\nEND SOURCE\n")
    assert "SYNESIS_E003" in codes(diags)


def test_severidade_de_origem_preservada(projeto):
    """SourceWithoutItems é WARNING no compilador — não pode virar erro."""
    from lsprotocol.types import DiagnosticSeverity

    diags = projeto("\nSOURCE @souza2019\n    description: sem items\nEND SOURCE\n")
    alvo = next(d for d in diags if d.code == "SYNESIS_E003")
    assert alvo.severity == DiagnosticSeverity.Warning


def test_orphan_item_e_erro(projeto):
    from lsprotocol.types import DiagnosticSeverity

    diags = projeto('\nITEM @orfao999\n    citation: "x"\nEND ITEM\n')
    alvo = next(d for d in diags if d.code == "SYNESIS_E002")
    assert alvo.severity == DiagnosticSeverity.Error


def test_conceito_de_ontologia_duplicado_aparece(tmp_path, monkeypatch):
    """
    O diagnóstico pertence ao .syno, não ao .syn — o merge tem de encontrá-lo
    pelo URI do arquivo aberto, qualquer que seja ele.
    """
    (tmp_path / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "t.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "t.syn").write_text(BASE_SYN, encoding="utf-8")
    (tmp_path / "o.syno").write_text(
        "ONTOLOGY Dup\n    definition: primeira\nEND ONTOLOGY\n\n"
        "ONTOLOGY Dup\n    definition: segunda\nEND ONTOLOGY\n",
        encoding="utf-8",
    )
    (tmp_path / "t.synp").write_text(
        'PROJECT t\n'
        '    TEMPLATE "t.synt"\n'
        '    INCLUDE BIBLIOGRAPHY "t.bib"\n'
        '    INCLUDE ANNOTATIONS "t.syn"\n'
        '    INCLUDE ONTOLOGY "o.syno"\n'
        'END PROJECT\n',
        encoding="utf-8",
    )

    result = synesis.SynesisCompiler(tmp_path / "t.synp").compile()
    monkeypatch.setattr(
        server, "_get_cached_for_uri", lambda ls, uri: _Cached(result, tmp_path)
    )

    syno = tmp_path / "o.syno"
    uri = syno.resolve().as_uri()
    per_file = build_diagnostics(
        validate_single_file(syno.read_text(encoding="utf-8"), uri, context=None)
    )

    assert "SYNESIS_E068" not in codes(per_file), "per-file não detecta — é o defeito"
    assert "SYNESIS_E068" in codes(_merge_project_diagnostics(None, uri, per_file))


# ------------------------------------------------------ deduplicação (V1)

def test_erro_dos_dois_caminhos_nao_duplica(projeto):
    """
    `UnregisteredSource` é detectado pelo per-file E pelo projeto. Sem
    deduplicação, o usuário veria a mesma mensagem duas vezes.
    """
    diags = projeto(
        '\nSOURCE @foradobib\n    description: y\nEND SOURCE\n'
        '\nITEM @foradobib\n    citation: "x"\nEND ITEM\n'
    )
    mensagens = [d.message for d in diags]
    assert len(mensagens) == len(set(mensagens))


def test_unregistered_source_continua_aparecendo(projeto):
    """Não-regressão: o que já funcionava não pode sumir."""
    diags = projeto(
        '\nSOURCE @foradobib\n    description: y\nEND SOURCE\n'
        '\nITEM @foradobib\n    citation: "x"\nEND ITEM\n'
    )
    assert "SYNESIS_E001" in codes(diags)


# --------------------------------------------------------------- allowlist

def test_apenas_classes_cross_file_sao_mescladas(projeto):
    """
    Allowlist estreita: mesclar tudo traria diagnósticos obsoletos, já que o
    projeto compilado é mais antigo que o buffer em edição.
    """
    diags = projeto('\nITEM @orfao999\n    citation: "x"\nEND ITEM\n')
    per_file_codes = {"SYNESIS_E001"}
    for code in codes(diags):
        assert code in _CROSS_FILE_CODES or code in per_file_codes or code is None


def test_allowlist_documenta_as_quatro_classes():
    assert _CROSS_FILE_CODES == {
        "SYNESIS_E002",  # OrphanItem
        "SYNESIS_E003",  # SourceWithoutItems
        "SYNESIS_E068",  # DuplicateOntologyConcept
        "SYNESIS_E005",  # OntologyWithoutTemplateFields
    }


# ---------------------------------------------------------------- robustez

def test_projeto_sem_erros_nao_publica_nada(projeto):
    assert projeto() == []


def test_sem_cache_devolve_o_per_file(monkeypatch):
    """Arquivo isolado, sem projeto compilado: o caminho principal sobrevive."""
    monkeypatch.setattr(server, "_get_cached_for_uri", lambda ls, uri: None)
    original = ["diagnostico-per-file"]
    assert _merge_project_diagnostics(None, "file:///x.syn", original) == original


def test_falha_no_cache_nao_impede_publicacao(monkeypatch):
    """Um erro na mesclagem não pode derrubar os diagnósticos per-file."""
    def _explode(ls, uri):
        raise RuntimeError("cache indisponível")

    monkeypatch.setattr(server, "_get_cached_for_uri", _explode)
    original = ["diagnostico-per-file"]
    assert _merge_project_diagnostics(None, "file:///x.syn", original) == original
