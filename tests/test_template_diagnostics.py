"""
test_template_diagnostics.py - Testes para fallback de diagnósticos por template
"""

from dataclasses import dataclass
from types import SimpleNamespace

from synesis_lsp.template_diagnostics import build_template_diagnostics


@dataclass(frozen=True)
class DummyScope:
    name: str


def _make_template(field_specs=None, required=None, bundled=None, forbidden=None):
    return SimpleNamespace(
        field_specs=field_specs or {},
        required_fields=required or {},
        bundled_fields=bundled or {},
        forbidden_fields=forbidden or {},
    )


def test_unknown_field():
    template = _make_template(
        field_specs={
            "note": SimpleNamespace(
                name="note",
                scope=DummyScope("ITEM"),
                type=SimpleNamespace(name="TEXT"),
            )
        }
    )
    source = "ITEM\n  notes: \"x\"\nEND\n"
    diagnostics = build_template_diagnostics(
        source, "file:///test.syn", template, set()
    )
    assert any("Campo desconhecido" in d.message for d in diagnostics)


def test_missing_required_field():
    template = _make_template(
        field_specs={
            "note": SimpleNamespace(
                name="note",
                scope=DummyScope("ITEM"),
                type=SimpleNamespace(name="TEXT"),
            )
        },
        required={DummyScope("ITEM"): ["note"]},
    )
    source = "ITEM\n  codigo: \"x\"\nEND\n"
    diagnostics = build_template_diagnostics(
        source, "file:///test.syn", template, set()
    )
    assert any("Campo obrigatorio ausente" in d.message for d in diagnostics)


def test_scope_mismatch():
    template = _make_template(
        field_specs={
            "ont": SimpleNamespace(
                name="ont",
                scope=DummyScope("ONTOLOGY"),
                type=SimpleNamespace(name="TEXT"),
            )
        }
    )
    source = "ITEM\n  ont: \"x\"\nEND\n"
    diagnostics = build_template_diagnostics(
        source, "file:///test.syn", template, set()
    )
    assert any("nao e permitido" in d.message for d in diagnostics)
