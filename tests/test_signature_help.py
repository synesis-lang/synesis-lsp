"""
Testes para synesis_lsp/signature_help.py

Cobertura:
- Campo reconhecido → SignatureHelp com tipo/escopo/descrição
- Cursor antes do : → None
- Campo desconhecido → None
- Sem cache / sem template → None
- Linha sem padrão de campo → None
"""

from types import SimpleNamespace
from enum import Enum

import pytest
from lsprotocol.types import Position

from synesis_lsp.signature_help import compute_signature_help


class MockFieldType(Enum):
    TEXT = "TEXT"
    CODE = "CODE"
    NUMBER = "NUMBER"


class MockScope(Enum):
    SOURCE = "SOURCE"
    ITEM = "ITEM"


def _make_cached(field_specs=None):
    template = None
    if field_specs is not None:
        template = SimpleNamespace(field_specs=field_specs)
    result = SimpleNamespace(template=template)
    return SimpleNamespace(result=result)


FIELDS = {
    "tema": SimpleNamespace(
        type=MockFieldType.TEXT,
        scope=MockScope.ITEM,
        description="Tema principal do item",
    ),
    "ordem_2a": SimpleNamespace(
        type=MockFieldType.CODE,
        scope=MockScope.ITEM,
        description="Códigos de segunda ordem",
    ),
    "nota": SimpleNamespace(
        type=MockFieldType.TEXT,
        scope=MockScope.ITEM,
        description="",
    ),
}


class TestSignatureHelp:
    """Testa SignatureHelp para campos."""

    def test_field_after_colon(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: educação\n"
        pos = Position(line=0, character=8)  # após "tema: "
        result = compute_signature_help(source, pos, cached)

        assert result is not None
        assert len(result.signatures) == 1
        sig = result.signatures[0]
        assert "tema" in sig.label
        assert "TEXT" in sig.label
        assert "Tema principal" in sig.documentation

    def test_code_field(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  ordem_2a: proposito\n"
        pos = Position(line=0, character=12)
        result = compute_signature_help(source, pos, cached)

        assert result is not None
        sig = result.signatures[0]
        assert "CODE" in sig.label
        assert "ordem_2a" in sig.label

    def test_cursor_before_colon(self):
        """Cursor sobre o nome do campo (antes do :) → None."""
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: valor\n"
        pos = Position(line=0, character=3)  # sobre "tema"
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_cursor_on_colon(self):
        """Cursor sobre o : → None."""
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: valor\n"
        pos = Position(line=0, character=6)  # sobre ":"
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_unknown_field(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  desconhecido: valor\n"
        pos = Position(line=0, character=16)
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_no_cache(self):
        source = "  tema: valor\n"
        pos = Position(line=0, character=8)
        result = compute_signature_help(source, pos, None)
        assert result is None

    def test_no_template(self):
        cached = _make_cached(field_specs=None)
        source = "  tema: valor\n"
        pos = Position(line=0, character=8)
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_not_field_line(self):
        """Linha sem padrão campo: → None."""
        cached = _make_cached(field_specs=FIELDS)
        source = "SOURCE @entrevista01\n"
        pos = Position(line=0, character=10)
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_field_empty_description(self):
        """Campo sem descrição ainda retorna SignatureHelp."""
        cached = _make_cached(field_specs=FIELDS)
        source = "  nota: observação\n"
        pos = Position(line=0, character=8)
        result = compute_signature_help(source, pos, cached)

        assert result is not None
        sig = result.signatures[0]
        assert "nota" in sig.label

    def test_has_parameters(self):
        """SignatureHelp deve ter um parâmetro (o valor)."""
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: valor\n"
        pos = Position(line=0, character=8)
        result = compute_signature_help(source, pos, cached)

        assert result is not None
        assert len(result.signatures[0].parameters) == 1
        param = result.signatures[0].parameters[0]
        assert "TEXT" in param.label

    def test_line_out_of_range(self):
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: valor\n"
        pos = Position(line=5, character=0)
        result = compute_signature_help(source, pos, cached)
        assert result is None

    def test_scope_in_documentation(self):
        """Documentação deve incluir escopo."""
        cached = _make_cached(field_specs=FIELDS)
        source = "  tema: valor\n"
        pos = Position(line=0, character=8)
        result = compute_signature_help(source, pos, cached)

        assert "ITEM" in result.signatures[0].documentation
