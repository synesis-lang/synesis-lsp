"""
Testes para synesis_lsp/completion.py

Cobertura:
- Bibrefs após @ (trigger_char e _is_after_at)
- Códigos da ontologia
- Campos do template
- Sem cache → lista vazia
- Combinações parciais (só bib, só ontologia, etc.)
"""

from types import SimpleNamespace
from enum import Enum

import pytest
from lsprotocol.types import CompletionItemKind, Position

from synesis_lsp.completion import compute_completions, _is_after_at


class MockFieldType(Enum):
    TEXT = "TEXT"
    CODE = "CODE"


class MockScope(Enum):
    SOURCE = "SOURCE"
    ITEM = "ITEM"


def _make_cached(bibliography=None, ontology_index=None, code_usage=None, field_specs=None):
    lp = None
    if ontology_index is not None:
        lp = SimpleNamespace(
            ontology_index=ontology_index,
            code_usage=code_usage or {},
        )

    template = None
    if field_specs is not None:
        template = SimpleNamespace(field_specs=field_specs)

    result = SimpleNamespace(
        bibliography=bibliography,
        linked_project=lp,
        template=template,
    )
    return SimpleNamespace(result=result)


BIB = {
    "entrevista01": {
        "author": "Silva, João",
        "year": "2023",
        "title": "Entrevista sobre educação",
    },
    "entrevista02": {
        "author": "Oliveira, Ana",
        "year": "2024",
        "title": "Segunda entrevista",
    },
}

ONTOLOGY = {
    "proposito": SimpleNamespace(concept="proposito"),
    "dons": SimpleNamespace(concept="dons"),
}

CODE_USAGE = {
    "proposito": ["item1", "item2", "item3"],
    "dons": [],
}

FIELDS = {
    "tema": SimpleNamespace(
        type=MockFieldType.TEXT,
        scope=MockScope.ITEM,
        description="Tema principal",
    ),
    "codigo": SimpleNamespace(
        type=MockFieldType.CODE,
        scope=MockScope.ITEM,
        description="Código de referência",
    ),
}


class TestAfterAt:
    """Testa completamento de bibrefs após @."""

    def test_trigger_char_at(self):
        cached = _make_cached(bibliography=BIB)
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        bibrefs = [i for i in result.items if i.kind == CompletionItemKind.Reference]
        assert len(bibrefs) == 2
        labels = {i.label for i in bibrefs}
        assert "@entrevista01" in labels
        assert "@entrevista02" in labels

    def test_bibref_detail(self):
        cached = _make_cached(bibliography=BIB)
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        e01 = next(i for i in result.items if i.label == "@entrevista01")
        assert "Silva" in e01.detail
        assert "2023" in e01.detail

    def test_bibref_insert_text(self):
        cached = _make_cached(bibliography=BIB)
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        e01 = next(i for i in result.items if i.label == "@entrevista01")
        assert e01.insert_text == "entrevista01"  # sem @

    def test_is_after_at_in_text(self):
        """Sem trigger_char, mas cursor está após @ no texto."""
        cached = _make_cached(bibliography=BIB)
        source = "SOURCE @ent\n"
        pos = Position(line=0, character=11)  # após "@ent"
        result = compute_completions(source, pos, cached)
        bibrefs = [i for i in result.items if i.kind == CompletionItemKind.Reference]
        assert len(bibrefs) == 2

    def test_no_bibliography(self):
        cached = _make_cached(bibliography=None)
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        bibrefs = [i for i in result.items if i.kind == CompletionItemKind.Reference]
        assert len(bibrefs) == 0


class TestCodes:
    """Testa completamento de códigos."""

    def test_codes_from_ontology(self):
        cached = _make_cached(ontology_index=ONTOLOGY, code_usage=CODE_USAGE)
        source = "  prop\n"
        pos = Position(line=0, character=5)
        result = compute_completions(source, pos, cached)
        codes = [i for i in result.items if i.kind == CompletionItemKind.EnumMember]
        assert len(codes) == 2
        labels = {i.label for i in codes}
        assert "proposito" in labels
        assert "dons" in labels

    def test_code_usage_count(self):
        cached = _make_cached(ontology_index=ONTOLOGY, code_usage=CODE_USAGE)
        source = "  x\n"
        pos = Position(line=0, character=1)
        result = compute_completions(source, pos, cached)
        prop = next(i for i in result.items if i.label == "proposito")
        assert "3 usos" in prop.detail

    def test_code_zero_usage(self):
        cached = _make_cached(ontology_index=ONTOLOGY, code_usage=CODE_USAGE)
        source = "  x\n"
        pos = Position(line=0, character=1)
        result = compute_completions(source, pos, cached)
        dons = next(i for i in result.items if i.label == "dons")
        assert "0 usos" in dons.detail


class TestFields:
    """Testa completamento de campos do template."""

    def test_fields_from_template(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  te\n"
        pos = Position(line=0, character=3)
        result = compute_completions(source, pos, cached)
        fields = [i for i in result.items if i.kind == CompletionItemKind.Property]
        assert len(fields) == 2
        labels = {i.label for i in fields}
        assert "tema:" in labels
        assert "codigo:" in labels

    def test_field_detail(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  x\n"
        pos = Position(line=0, character=1)
        result = compute_completions(source, pos, cached)
        tema = next(i for i in result.items if i.label == "tema:")
        assert "TEXT" in tema.detail
        assert "ITEM" in tema.detail

    def test_field_documentation(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  x\n"
        pos = Position(line=0, character=1)
        result = compute_completions(source, pos, cached)
        tema = next(i for i in result.items if i.label == "tema:")
        assert tema.documentation == "Tema principal"


class TestNoCache:
    """Testa sem cache."""

    def test_no_cache_returns_empty(self):
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, None)
        assert result.items == []
        assert result.is_incomplete is False


class TestCombined:
    """Testa combinações de fontes."""

    def test_all_sources_combined(self):
        cached = _make_cached(
            bibliography=BIB,
            ontology_index=ONTOLOGY,
            code_usage=CODE_USAGE,
            field_specs=FIELDS,
        )
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        refs = [i for i in result.items if i.kind == CompletionItemKind.Reference]
        codes = [i for i in result.items if i.kind == CompletionItemKind.EnumMember]
        fields = [i for i in result.items if i.kind == CompletionItemKind.Property]
        assert len(refs) == 2
        assert len(codes) == 2
        assert len(fields) == 2

    def test_not_incomplete(self):
        cached = _make_cached(bibliography=BIB)
        source = "SOURCE @\n"
        pos = Position(line=0, character=8)
        result = compute_completions(source, pos, cached, trigger_char="@")
        assert result.is_incomplete is False


class TestIsAfterAt:
    """Testa helper _is_after_at."""

    def test_after_at(self):
        assert _is_after_at("@abc", 4) is True

    def test_at_start(self):
        assert _is_after_at("@", 1) is True

    def test_no_at(self):
        assert _is_after_at("abc", 3) is False

    def test_space_between(self):
        assert _is_after_at("@ abc", 3) is False

    def test_zero_pos(self):
        assert _is_after_at("@abc", 0) is False
