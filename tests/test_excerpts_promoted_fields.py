"""Campos promovidos pelo transformer devem voltar a extra_fields.

O transformer (synesis/parser/transformer.py) roteia campos do ITEM por NOME
literal, não pelo tipo declarado no template:

    quote/quotation        → item.quote
    note/notes/memo/memos  → item.notes
    code/codes             → item.codes
    chain/chains           → item.chains
    (resto)                → item.extra_fields

`get_excerpts` serializava apenas extra_fields (+ codes/chains), então um campo
`FIELD memo TYPE MEMO` declarado no template nunca chegava ao cliente — sumia da
tela sem erro. Medido no face85 (case-studies/ufmg/face85), onde todos os ITEMs
têm `memo` e nenhum o exibia.
"""

from synesis_lsp.explorer_requests import _reinsert_promoted_fields


class FakeItem:
    """ItemNode mínimo com os atributos que a função lê."""

    def __init__(self, field_names=None, quote=None, notes=None):
        self.field_names = field_names or []
        self.quote = quote
        self.notes = notes or []


def test_memo_volta_para_extra_fields():
    item = FakeItem(field_names=["text", "zone", "memo"], notes=["a memo do item"])
    extra = {"text": "trecho", "zone": "Result"}

    _reinsert_promoted_fields(item, extra)

    assert extra["memo"] == "a memo do item"


def test_preserva_o_nome_original_do_campo():
    """`memo` num projeto, `note` noutro — o rótulo deve casar com o template."""
    item = FakeItem(field_names=["note"], notes=["conteudo"])
    extra = {}

    _reinsert_promoted_fields(item, extra)

    assert "note" in extra
    assert "memo" not in extra


def test_quote_promovido_volta():
    item = FakeItem(field_names=["quote", "zone"], quote="trecho citado")
    extra = {"zone": "Result"}

    _reinsert_promoted_fields(item, extra)

    assert extra["quote"] == "trecho citado"


def test_multiplas_notes_viram_lista():
    item = FakeItem(field_names=["memo"], notes=["n1", "n2", "n3"])
    extra = {}

    _reinsert_promoted_fields(item, extra)

    assert extra["memo"] == ["n1", "n2", "n3"]


def test_nota_unica_nao_vira_lista():
    item = FakeItem(field_names=["memo"], notes=["so uma"])
    extra = {}

    _reinsert_promoted_fields(item, extra)

    assert extra["memo"] == "so uma"


def test_nao_sobrescreve_valor_existente():
    item = FakeItem(field_names=["memo"], notes=["da promocao"])
    extra = {"memo": "ja estava em extra_fields"}

    _reinsert_promoted_fields(item, extra)

    assert extra["memo"] == "ja estava em extra_fields"


def test_fallback_quando_field_names_vazio():
    """Sem field_names o dado existe mas não teria nome — perder é pior."""
    item = FakeItem(field_names=[], notes=["recuperada"], quote="q")
    extra = {}

    _reinsert_promoted_fields(item, extra)

    assert extra["memo"] == "recuperada"
    assert extra["quote"] == "q"


def test_fallback_nao_duplica_quando_o_nome_ja_foi_usado():
    item = FakeItem(field_names=["note"], notes=["unica"])
    extra = {}

    _reinsert_promoted_fields(item, extra)

    assert extra == {"note": "unica"}, "nao deve criar tambem a chave 'memo'"


def test_item_sem_quote_nem_notes_nao_cria_chaves():
    item = FakeItem(field_names=["memo", "quote"])
    extra = {"zone": "X"}

    _reinsert_promoted_fields(item, extra)

    assert extra == {"zone": "X"}


def test_campo_nao_promovido_e_ignorado():
    """zone/confidence já estão em extra_fields; a função não deve tocá-los."""
    item = FakeItem(field_names=["zone", "confidence"], notes=["memo orfa"])
    extra = {"zone": "Result", "confidence": "High"}

    _reinsert_promoted_fields(item, extra)

    # notes existe mas nenhum nome promovido foi declarado → fallback nomeia 'memo'
    assert extra["zone"] == "Result"
    assert extra["confidence"] == "High"
    assert extra["memo"] == "memo orfa"
