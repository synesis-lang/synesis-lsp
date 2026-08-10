"""test_completion_blocks.py - Blocos SOURCE/ITEM/ONTOLOGY no autocomplete.

O ponto central destes testes: o bloco sugerido depende do TEMPLATE do projeto
aberto. Um arquivo .code-snippets estatico nao teria como saber que `linkedin`
exige slug+nome e `lattes` exige lattes_id+nome+cargo_institucional — por isso
os blocos vivem no LSP, e nao na extensao.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from lsprotocol.types import CompletionItemKind, InsertTextFormat, Position
from synesis.parser.template_loader import load_template_from_string

from synesis_lsp.completion import compute_completions

_TEMPLATE = """TEMPLATE projeto_exemplo
SOURCE FIELDS
    REQUIRED slug, nome
    OPTIONAL headline
END SOURCE FIELDS
ITEM FIELDS
    REQUIRED trecho
    OPTIONAL criterio
    OPTIONAL BUNDLE chain, memo
END ITEM FIELDS
ONTOLOGY FIELDS
    REQUIRED ontology_description
END ONTOLOGY FIELDS
FIELD slug TYPE TEXT
    SCOPE SOURCE
END FIELD
FIELD nome TYPE TEXT
    SCOPE SOURCE
END FIELD
FIELD headline TYPE TEXT
    SCOPE SOURCE
END FIELD
FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD
FIELD criterio TYPE CODE
    SCOPE ITEM
END FIELD
FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD
FIELD memo TYPE MEMO
    SCOPE ITEM
END FIELD
FIELD ontology_description TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""


def _cached(template_src: str = _TEMPLATE):
    template = load_template_from_string(template_src, "exemplo.synt")
    return SimpleNamespace(
        result=SimpleNamespace(
            template=template, bibliography={}, linked_project=None
        )
    )


def _blocks(source: str = "", character: int = 0, cached=None):
    result = compute_completions(
        source, Position(line=0, character=character), cached or _cached()
    )
    return {i.label: i for i in result.items if i.label.endswith("(bloco)")}


def _expand(text: str) -> str:
    """Expande tab-stops como o editor faria."""
    return re.sub(r"\$\{\d+:([^}]*)\}", r"\1", text).replace("$0", "").strip()


# --------------------------------------------------------------------------
# Presenca e forma
# --------------------------------------------------------------------------

def test_offers_the_three_annotation_blocks():
    blocks = _blocks()
    assert set(blocks) == {"SOURCE (bloco)", "ITEM (bloco)", "ONTOLOGY (bloco)"}


def test_blocks_are_snippets_not_plain_text():
    """Sem InsertTextFormat.Snippet os tab-stops apareceriam literalmente."""
    for block in _blocks().values():
        assert block.kind is CompletionItemKind.Snippet
        assert block.insert_text_format is InsertTextFormat.Snippet


def test_source_block_carries_required_fields_of_this_template():
    body = _blocks()["SOURCE (bloco)"].insert_text
    assert "SOURCE @" in body
    assert "slug:" in body
    assert "nome:" in body
    assert "END SOURCE" in body


def test_optional_fields_are_commented_not_active():
    """Opcionais entram COMENTADOS: documentam o que o escopo aceita sem que
    um campo vazio quebre a validacao. Tambem seguem na documentacao do item."""
    block = _blocks()["SOURCE (bloco)"]
    assert "# headline:" in block.insert_text
    assert "\n    headline:" not in block.insert_text  # nao como linha ativa
    assert "headline" in block.documentation


def test_ontology_block_uses_concept_name_not_bibref():
    body = _blocks()["ONTOLOGY (bloco)"].insert_text
    assert "ONTOLOGY ${1:nome_do_conceito}" in body
    assert "@" not in body.splitlines()[0]


def test_bundle_is_reported_in_documentation():
    """Bundle e contrato tudo-ou-nada; o pesquisador precisa saber que existe."""
    doc = _blocks()["ITEM (bloco)"].documentation
    assert "chain+memo" in doc


def test_tabstops_are_sequential_and_unique():
    for label, block in _blocks().items():
        stops = [int(n) for n in re.findall(r"\$\{(\d+):", block.insert_text)]
        assert stops == sorted(stops), f"{label}: fora de ordem {stops}"
        assert len(stops) == len(set(stops)), f"{label}: repetidos {stops}"


# --------------------------------------------------------------------------
# O contrato central: o bloco reflete o template do projeto
# --------------------------------------------------------------------------

def test_block_content_varies_with_the_template():
    """Motivo de estar no LSP e nao num .code-snippets estatico."""
    outro = _TEMPLATE.replace("REQUIRED slug, nome", "REQUIRED lattes_id") \
                     .replace("FIELD slug TYPE TEXT", "FIELD lattes_id TYPE TEXT") \
                     .replace("FIELD nome TYPE TEXT\n    SCOPE SOURCE\nEND FIELD\n", "")

    padrao = _blocks()["SOURCE (bloco)"].insert_text
    variante = _blocks(cached=_cached(outro))["SOURCE (bloco)"].insert_text

    assert "slug:" in padrao and "lattes_id:" not in padrao
    assert "lattes_id:" in variante and "slug:" not in variante


def test_scope_absent_from_template_yields_no_block():
    sem_ontologia = re.sub(
        r"ONTOLOGY FIELDS.*?END ONTOLOGY FIELDS\n", "", _TEMPLATE, flags=re.S
    ).replace(
        "FIELD ontology_description TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n", ""
    )
    blocks = _blocks(cached=_cached(sem_ontologia))
    assert "ONTOLOGY (bloco)" not in blocks
    assert "SOURCE (bloco)" in blocks


def test_expanded_blocks_parse():
    """O que o pesquisador recebe ao expandir tem de ser sintaxe valida."""
    from synesis.parser.lexer import parse_string

    for label, block in _blocks().items():
        parse_string(_expand(block.insert_text) + "\n", "<snippet>")


# --------------------------------------------------------------------------
# Contexto: onde os blocos NAO devem aparecer
# --------------------------------------------------------------------------

def test_no_blocks_inside_a_field_value():
    """Dentro de `campo: ...` um bloco inteiro nunca faz sentido."""
    linha = "    trecho: algum texto"
    assert _blocks(source=linha, character=len(linha)) == {}


def test_no_blocks_right_after_at_sign():
    """Apos @ o usuario quer um bibref, nao um bloco."""
    linha = "SOURCE @"
    assert _blocks(source=linha, character=len(linha)) == {}


def test_no_crash_without_cache():
    result = compute_completions("", Position(line=0, character=0), None)
    assert result.items == []


def test_no_crash_without_template():
    cached = SimpleNamespace(
        result=SimpleNamespace(template=None, bibliography={}, linked_project=None)
    )
    result = compute_completions("", Position(line=0, character=0), cached)
    assert not [i for i in result.items if i.label.endswith("(bloco)")]


# --------------------------------------------------------------------------
# Regressao: o completion existente continua funcionando
# --------------------------------------------------------------------------

def test_field_completions_still_offered():
    result = compute_completions("", Position(line=0, character=0), _cached())
    fields = {i.label for i in result.items if i.kind is CompletionItemKind.Property}
    assert "slug:" in fields
    assert "trecho:" in fields


def test_bibref_completion_still_offered():
    cached = SimpleNamespace(
        result=SimpleNamespace(
            template=load_template_from_string(_TEMPLATE, "e.synt"),
            bibliography={"silva2023": {"author": "Silva", "year": "2023"}},
            linked_project=None,
        )
    )
    linha = "SOURCE @"
    result = compute_completions(
        linha, Position(line=0, character=len(linha)), cached, trigger_char="@"
    )
    assert any(i.label == "@silva2023" for i in result.items)


# --------------------------------------------------------------------------
# Regressao: REQUIRED BUNDLE tambem e obrigatorio
# --------------------------------------------------------------------------

_TEMPLATE_REQUIRED_BUNDLE = """TEMPLATE com_bundle
SOURCE FIELDS
    REQUIRED slug
END SOURCE FIELDS
ITEM FIELDS
    REQUIRED text
    REQUIRED BUNDLE note, chain
END ITEM FIELDS
FIELD slug TYPE TEXT
    SCOPE SOURCE
END FIELD
FIELD text TYPE QUOTATION
    SCOPE ITEM
END FIELD
FIELD note TYPE MEMO
    SCOPE ITEM
END FIELD
FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD
"""


def test_required_bundle_fields_are_in_the_block():
    """`REQUIRED BUNDLE a, b` vive em `bundled_fields`, estrutura separada de
    `required_fields`. Ler so a segunda produzia blocos incompletos — bug real
    observado com social_acceptance.synt, onde `note` e `chain` sumiam."""
    blocks = _blocks(cached=_cached(_TEMPLATE_REQUIRED_BUNDLE))
    body = blocks["ITEM (bloco)"].insert_text
    assert "text:" in body
    assert "note:" in body, "campo de REQUIRED BUNDLE ausente"
    assert "chain:" in body, "campo de REQUIRED BUNDLE ausente"


def test_required_bundle_counted_in_detail():
    detail = _blocks(cached=_cached(_TEMPLATE_REQUIRED_BUNDLE))["ITEM (bloco)"].detail
    assert "3 campo" in detail


def test_block_with_required_bundle_parses():
    from synesis.parser.lexer import parse_string

    body = _blocks(cached=_cached(_TEMPLATE_REQUIRED_BUNDLE))["ITEM (bloco)"].insert_text
    parse_string(_expand(body) + "\n", "<snippet>")


# --------------------------------------------------------------------------
# Caixa: a gramatica aceita item/Item/ITEM — o snippet segue o que foi digitado
# --------------------------------------------------------------------------

def test_block_keyword_follows_typed_case():
    """A keyword inserida e sempre COMPLETA; so a caixa acompanha o prefixo
    digitado (`ite` -> `item`, `It` -> `Item`)."""
    for typed, expected in [
        ("ITEM", "ITEM"), ("item", "item"), ("Item", "Item"),
        ("ite", "item"), ("It", "Item"), ("I", "ITEM"),
    ]:
        block = _blocks(source=typed, character=len(typed))["ITEM (bloco)"]
        first, last = block.insert_text.splitlines()[0], block.insert_text.splitlines()[-2]
        assert first.startswith(expected), f"{typed!r} -> {first!r}"
        assert last == f"END {expected}", f"{typed!r} -> {last!r}"


def test_block_defaults_to_uppercase_without_input():
    """Sem nada digitado, segue a convencao dos templates do ecossistema."""
    body = _blocks()["SOURCE (bloco)"].insert_text
    assert body.startswith("SOURCE ")
    assert "END SOURCE" in body


def test_lowercase_block_still_parses():
    from synesis.parser.lexer import parse_string

    block = _blocks(source="item", character=4)["ITEM (bloco)"]
    parse_string(_expand(block.insert_text) + "\n", "<snippet>")


# --------------------------------------------------------------------------
# Opcionais entram comentados
# --------------------------------------------------------------------------

def test_optional_section_has_a_hint_line():
    """Uma linha explica o que fazer com as linhas comentadas."""
    assert "descomente" in _blocks()["SOURCE (bloco)"].insert_text


def test_scope_without_optionals_has_no_comment_section():
    body = _blocks()["ONTOLOGY (bloco)"].insert_text
    assert "descomente" not in body


def test_block_with_commented_optionals_parses():
    from synesis.parser.lexer import parse_string

    parse_string(_expand(_blocks()["SOURCE (bloco)"].insert_text) + "\n", "<snippet>")


def test_commented_optionals_have_no_tabstops():
    """Tab nao deve parar em linha comentada — o pesquisador so preenche o que
    descomentar."""
    body = _blocks()["SOURCE (bloco)"].insert_text
    for line in body.splitlines():
        if line.strip().startswith("#"):
            assert "${" not in line, f"tab-stop em linha comentada: {line!r}"
