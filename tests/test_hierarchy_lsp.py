"""Rastreio da hierarquia no LSP (etapa A2d do plano ROLE/EXPORT).

Usa o projeto de teste (case-studies/Exemplo_Tipos_Relacionais), que tem um
conceito com dois pais (`phishing`), as tres especies e um ITEM que cita dois
descendentes. Pulado sem case-studies ou com compilador sem papeis.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2] / "case-studies" / "Exemplo_Tipos_Relacionais"
SYNP = ROOT / "fraudes.synp"


def _compiler_has_roles() -> bool:
    import synesis.semantic as semantic

    return (Path(semantic.__file__).parent / "hierarchy.py").exists()


pytestmark = pytest.mark.skipif(
    not SYNP.exists() or not _compiler_has_roles(), reason="projeto de teste ou compilador sem papeis"
)


@pytest.fixture(scope="module")
def cached():
    from synesis.compiler import SynesisCompiler

    return SimpleNamespace(result=SynesisCompiler(SYNP).compile())


def test_references_include_hierarchy_fields(cached):
    from synesis_lsp.references import compute_references

    locations = compute_references(cached, "phishing", ROOT, include_declaration=False)
    syno = [loc for loc in locations if loc.uri.endswith("ontologia.syno")]
    lines = (ROOT / "ontologia.syno").read_text(encoding="utf-8").splitlines()
    cited = {lines[loc.range.start.line].strip() for loc in syno}
    assert "tipo_de: phishing" in cited
    assert "parte_de: phishing" in cited


def test_type_hierarchy_two_parents_and_children(cached):
    from synesis_lsp.hierarchy import subtypes, supertypes, type_hierarchy_item

    item = type_hierarchy_item(cached, "phishing", ROOT)[0]
    assert item.name == "phishing"
    parents = {(i.name, i.detail) for i in supertypes(cached, item, ROOT)}
    assert parents == {("fraude_online", "KIND"), ("engenharia_social", "KIND")}
    children = {(i.name, i.detail) for i in subtypes(cached, item, ROOT)}
    assert ("mensagem_de_phishing", "PART") in children
    assert ("smishing", "KIND") in children and len(children) == 6


def test_hover_counts_subtree_items_without_duplicates(cached):
    from synesis_lsp.hierarchy import hierarchy_hover_lines

    lines = hierarchy_hover_lines(cached, "phishing")
    assert any(l.startswith("**Parents:**") and "fraude_online" in l for l in lines)
    assert "**ITEMs:** 2 own, 4 in the subtree (8 descendant(s))" in lines


def test_hover_marks_ungrounded(cached):
    from synesis_lsp.hierarchy import hierarchy_hover_lines

    lines = hierarchy_hover_lines(cached, "spear_phishing")
    assert any(l.startswith("**Ungrounded:**") for l in lines)


def test_top_concept_has_no_parents(cached):
    from synesis_lsp.hierarchy import hierarchy_hover_lines

    lines = hierarchy_hover_lines(cached, "fraude_online")
    assert "**Parents:** none (top concept)" in lines


def test_completion_roles_and_export_properties():
    from lsprotocol.types import Position

    from synesis_lsp.completion import _role_or_export_completions

    roles = _role_or_export_completions(["FIELD x TYPE CODE", "    ROLE "], Position(line=1, character=9))
    assert "HIERARCHY KIND" in [i.label for i in roles]
    synp = ["PROJECT p", "EXPORT SKOS", "    "]
    props = [i.label for i in _role_or_export_completions(synp, Position(line=2, character=4))]
    assert {"OUTPUT", "NAMESPACE", "LANGUAGE", "MAP RELATIONS"} <= set(props)
    assert _role_or_export_completions(["    tipo_de: "], Position(line=0, character=13)) is None


def test_explorer_tree_is_the_hierarchy(cached):
    from synesis_lsp.ontology_topics import get_ontology_topics

    out = get_ontology_topics(cached, workspace_root=ROOT)
    assert out["mode"] == "hierarchy"
    tops = {t["name"]: t for t in out["topics"]}
    assert "fraude_online" in tops and "phishing" not in tops

    def find(nodes, name):
        for n in nodes:
            if n["name"] == name:
                yield n
            yield from find(n["children"], name)

    # conceito com dois pais aparece nos dois ramos
    assert len(list(find(out["topics"], "phishing"))) == 2
    phishing = next(find(out["topics"], "phishing"))
    assert (phishing["items"], phishing["itemsSubtree"], phishing["ungrounded"]) == (2, 4, False)
    assert next(find(out["topics"], "spear_phishing"))["ungrounded"] is True


def test_subtree_evidence_has_no_repeated_item(cached):
    from synesis_lsp.hierarchy import subtree_evidence

    items = subtree_evidence(cached, "phishing", ROOT)
    assert len(items) == 4
    assert len({(i["uri"], i["line"]) for i in items}) == 4


def test_hover_of_alias_points_to_target_and_target_lists_alias(cached):
    """Etapa U: `voice_phishing` usa `vishing` no projeto de teste."""
    from synesis_lsp.hierarchy import hierarchy_hover_lines

    alias = hierarchy_hover_lines(cached, "voice_phishing")
    assert alias and "use → `vishing`" in alias[0]
    target = "\n".join(hierarchy_hover_lines(cached, "vishing"))
    assert "Aliases (USE):** `voice_phishing`" in target


def test_role_completion_offers_use():
    from lsprotocol.types import Position

    from synesis_lsp.completion import _role_or_export_completions

    roles = _role_or_export_completions(["FIELD x TYPE CODE", "    ROLE "], Position(line=1, character=9))
    assert "USE" in [i.label for i in roles]
