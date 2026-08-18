"""
test_contract.py - Teste de contrato LSP↔extensão (lado produtor)

Verifica que a saída real dos 4 custom requests casa com os JSON Schemas
versionados em contracts/schemas/. O consumidor (synesis-vscode) valida suas
fixtures contra os MESMOS schemas — este é o par que impede que produtor e
consumidor divirjam sem que o CI perceba (diagnóstico D6 do Golden Standard).

Os schemas são a fonte de verdade do formato; os handlers e as fixtures da
extensão devem ambos obedecê-los.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"

ENDPOINTS = [
    "getReferences",
    "getCodes",
    "getRelations",
    "getOntologyAnnotations",
    "getExcerpts",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(endpoint: str) -> Draft202012Validator:
    """Validador que resolve os $ref para common.schema.json localmente.

    Usa `referencing` (jsonschema >= 4.18); o antigo `RefResolver` foi
    deprecado e sera removido numa versao futura.
    """
    schema = _load(SCHEMAS / f"{endpoint}.schema.json")
    common = _load(SCHEMAS / "common.schema.json")
    common_resource = Resource.from_contents(common)
    registry = Registry().with_resources([
        ("common.schema.json", common_resource),
        (common["$id"], common_resource),
        (schema["$id"], Resource.from_contents(schema)),
    ])
    return Draft202012Validator(schema, registry=registry)


# ---------------------------------------------------------------------------
# Os schemas em si são válidos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ENDPOINTS + ["common"])
def test_schema_is_valid_draft202012(name):
    schema = _load(SCHEMAS / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Exemplos canônicos obedecem ao schema
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_success_example_matches_schema(endpoint):
    example = _load(EXAMPLES / f"{endpoint}.success.json")
    _validator(endpoint).validate(example)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_error_example_matches_schema(endpoint):
    """A resposta de erro (success:false) é válida para todo endpoint."""
    error = _load(EXAMPLES / "error.json")
    _validator(endpoint).validate(error)


# ---------------------------------------------------------------------------
# Saída REAL dos handlers casa com o schema (o coração do teste de contrato)
# ---------------------------------------------------------------------------

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "synesis" / "tests" / "fixtures"
BASIC = FIXTURES_ROOT / "Basic" / "project.synp"
CHAINS = FIXTURES_ROOT / "T02-Chain-Relations" / "t02.synp"


def _compile_cached(synp: Path):
    from synesis.compiler import SynesisCompiler

    synp = synp.resolve()
    result = SynesisCompiler(synp).compile()

    class Cached:
        def __init__(self):
            self.result = result
            self.workspace_root = synp.parent
            self.timestamp = 0.0

    return Cached(), synp.parent


@pytest.mark.skipif(not BASIC.exists(), reason="fixtures do compilador não disponíveis neste checkout")
def test_real_output_matches_schema():
    from synesis_lsp.explorer_requests import get_codes, get_references, get_relations
    from synesis_lsp.ontology_annotations import get_ontology_annotations

    cached, ws = _compile_cached(BASIC)

    _validator("getReferences").validate(get_references(cached))
    _validator("getCodes").validate(get_codes(cached))
    _validator("getRelations").validate(get_relations(cached))
    _validator("getOntologyAnnotations").validate(get_ontology_annotations(cached, ws))


@pytest.mark.skipif(not BASIC.exists(), reason="fixtures do compilador não disponíveis neste checkout")
def test_real_excerpts_output_matches_schema():
    """getExcerpts com um bibref real — inclui a chave `source`."""
    from synesis_lsp.explorer_requests import get_excerpts, get_references

    cached, _ws = _compile_cached(BASIC)
    refs = get_references(cached)["references"]
    assert refs, "esperado ao menos um SOURCE na fixture Basic"

    payload = get_excerpts(cached, refs[0]["bibref"])
    assert "source" in payload, "a chave source deve estar sempre presente"
    _validator("getExcerpts").validate(payload)


@pytest.mark.skipif(not CHAINS.exists(), reason="fixture T02 não disponível neste checkout")
def test_real_relations_with_locations_match_schema():
    """T02 tem chains → relations com location e type presentes."""
    from synesis_lsp.explorer_requests import get_relations

    cached, _ws = _compile_cached(CHAINS)
    payload = get_relations(cached)

    assert payload["relations"], "esperado ao menos um triple no T02"
    assert any("location" in r for r in payload["relations"])
    _validator("getRelations").validate(payload)


@pytest.mark.skipif(not BASIC.exists(), reason="fixtures do compilador não disponíveis neste checkout")
def test_error_response_when_not_compiled():
    """Sem projeto compilado, todo endpoint retorna a forma de erro do contrato."""
    from synesis_lsp.explorer_requests import get_codes, get_references, get_relations
    from synesis_lsp.ontology_annotations import get_ontology_annotations

    _validator("getReferences").validate(get_references(None))
    _validator("getCodes").validate(get_codes(None))
    _validator("getRelations").validate(get_relations(None))
    _validator("getOntologyAnnotations").validate(get_ontology_annotations(None))
