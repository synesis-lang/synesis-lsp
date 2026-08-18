"""
test_excerpts_source_fields.py - Campos do bloco SOURCE em getExcerpts

`get_excerpts` devolvia apenas ITEMs. Um template com campos de escopo SOURCE
(`description`, `method`, `epistemic_model`) produzia um abstractViewer onde
NENHUM deles aparecia: o cabeçalho era montado 100% do BibTeX, e os campos do
.syn não tinham por onde chegar à tela. Sem erro, sem aviso — o pesquisador
concluía que o campo "não funciona".

A chave `source` é NOVA no payload; `items` não muda de forma. Extensão antiga
ignora o campo desconhecido e continua operando.
"""

from __future__ import annotations

import synesis

from synesis_lsp.explorer_requests import get_excerpts


class _Cached:
    """Dobra do CachedResult que os handlers do server recebem."""

    def __init__(self, result, workspace_root=None):
        self.result = result
        self.workspace_root = workspace_root


def compile_project(tmp_path, syn: str, synt: str) -> _Cached:
    (tmp_path / "p.synt").write_text(synt, encoding="utf-8")
    (tmp_path / "p.syn").write_text(syn, encoding="utf-8")
    (tmp_path / "p.synp").write_text(
        'PROJECT p\n'
        '    TEMPLATE "p.synt"\n'
        '    INCLUDE ANNOTATIONS "p.syn"\n'
        'END PROJECT\n',
        encoding="utf-8",
    )
    result = synesis.SynesisCompiler(tmp_path / "p.synp").compile()
    return _Cached(result, tmp_path)


TEMPLATE = """\
TEMPLATE p

SOURCE FIELDS
    OPTIONAL description
    OPTIONAL method
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD description TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD method TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""

SYN = """\
SOURCE @a2019
    description: Um estudo sobre percepcao
    method: Entrevistas semiestruturadas
END SOURCE

ITEM @a2019
    citation: "trecho citado"
END ITEM
"""


def test_devolve_campos_do_source(tmp_path):
    """O teste que prova a correção do defeito #1."""
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    out = get_excerpts(cached, "a2019")

    assert out["success"] is True
    assert out["source"]["description"] == "Um estudo sobre percepcao"
    assert out["source"]["method"] == "Entrevistas semiestruturadas"


def test_items_continuam_intactos(tmp_path):
    """A chave nova não pode alterar o que já era devolvido."""
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    out = get_excerpts(cached, "a2019")

    assert len(out["items"]) == 1
    item = out["items"][0]
    assert set(item) == {"extra_fields", "codes", "chains", "line", "file"}


def test_bibref_com_arroba(tmp_path):
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    assert get_excerpts(cached, "@a2019")["source"]["method"]


def test_bibref_insensivel_a_caixa(tmp_path):
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    assert get_excerpts(cached, "A2019")["source"]["description"]


def test_source_sem_campos_extras(tmp_path):
    """`source` presente e vazio — nunca None, para o cliente não precisar checar tipo."""
    syn = "SOURCE @a2019\nEND SOURCE\n\nITEM @a2019\n    citation: \"x\"\nEND ITEM\n"
    cached = compile_project(tmp_path, syn, TEMPLATE)
    out = get_excerpts(cached, "a2019")

    assert out["source"] == {}
    assert out["source"] is not None


def test_bibref_inexistente_nao_levanta(tmp_path):
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    out = get_excerpts(cached, "naoexiste")

    assert out["success"] is True
    assert out["items"] == []
    assert out["source"] == {}


def test_source_sempre_presente_no_payload(tmp_path):
    """Contrato: a chave existe em toda resposta bem-sucedida."""
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    assert "source" in get_excerpts(cached, "a2019")


def test_valores_sao_json_safe(tmp_path):
    import json

    cached = compile_project(tmp_path, SYN, TEMPLATE)
    out = get_excerpts(cached, "a2019")

    json.dumps(out)  # não deve levantar


def test_bibref_vazio_continua_erro(tmp_path):
    """Não-regressão do contrato de erro."""
    cached = compile_project(tmp_path, SYN, TEMPLATE)
    out = get_excerpts(cached, "")

    assert out["success"] is False
