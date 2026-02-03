"""
Testes para synesis_lsp/ontology_annotations.py

Cobertura:
- Cruzamento de ontologia com code_usage
- Filtragem por activeFile
- Occurrences com itemName, line, column, context, field
- Detecção de context (code vs chain)
- Paths relativos ao workspace
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from synesis_lsp.ontology_annotations import (
    get_ontology_annotations,
    _build_occurrences,
    _find_code_in_item,
)


def _make_cached(ontology_index=None, code_usage=None):
    """Cria CachedCompilation mock."""
    lp = SimpleNamespace(
        ontology_index=ontology_index or {},
        code_usage=code_usage or {}
    )
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(result=result)


class TestGetOntologyAnnotations:
    """Testa extração de anotações de ontologia."""

    def test_no_cache(self):
        """Deve retornar erro quando não há cache."""
        result = get_ontology_annotations(None)
        assert result["success"] is False
        assert "error" in result

    def test_empty_ontology(self):
        """Deve retornar lista vazia quando não há ontologia."""
        cached = _make_cached(ontology_index={}, code_usage={})
        result = get_ontology_annotations(cached)
        assert result["success"] is True
        assert result["annotations"] == []

    def test_with_annotations(self):
        """Deve retornar annotations com occurrences."""
        # Criar ontology_index
        ontology_index = {
            "smoking": SimpleNamespace(
                location=SimpleNamespace(
                    file="/workspace/ontology/health.syno",
                    line=5
                )
            )
        }

        # Criar code_usage
        item1 = SimpleNamespace(
            name="participant_001",
            location=SimpleNamespace(
                file="/workspace/data/study1.syn",
                line=42,
                column=1
            ),
            extra_fields={
                "CODE": ["smoking"],
                "BIBREF": ["@smith2020"]
            },
            chains=[]
        )

        code_usage = {
            "smoking": [item1]
        }

        cached = _make_cached(ontology_index=ontology_index, code_usage=code_usage)
        workspace_root = Path("/workspace")
        result = get_ontology_annotations(cached, workspace_root=workspace_root)

        assert result["success"] is True
        assert len(result["annotations"]) == 1

        annotation = result["annotations"][0]
        assert annotation["code"] == "smoking"
        assert annotation["ontologyDefined"] is True
        assert "ontologyFile" in annotation
        assert annotation["ontologyLine"] == 5
        assert len(annotation["occurrences"]) > 0

        occ = annotation["occurrences"][0]
        assert occ["itemName"] == "participant_001"
        assert occ["line"] == 42
        assert occ["context"] in ["code", "chain"]
        assert "field" in occ

    def test_filter_by_active_file(self):
        """Deve filtrar occurrences por activeFile."""
        ontology_index = {
            "smoking": SimpleNamespace(location=None)
        }

        item1 = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(file="/workspace/file1.syn", line=10, column=1),
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        item2 = SimpleNamespace(
            name="item2",
            location=SimpleNamespace(file="/workspace/file2.syn", line=20, column=1),
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        code_usage = {"smoking": [item1, item2]}

        cached = _make_cached(ontology_index=ontology_index, code_usage=code_usage)
        workspace_root = Path("/workspace")

        # Filtrar apenas file1.syn
        result = get_ontology_annotations(
            cached,
            workspace_root=workspace_root,
            active_file="file1.syn"
        )

        assert result["success"] is True
        annotation = result["annotations"][0]
        assert len(annotation["occurrences"]) == 1
        assert "file1.syn" in annotation["occurrences"][0]["file"]

    def test_multiple_concepts(self):
        """Deve retornar annotations para múltiplos conceitos."""
        ontology_index = {
            "smoking": SimpleNamespace(location=None),
            "cancer": SimpleNamespace(location=None),
        }

        item1 = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(file="/workspace/file.syn", line=10, column=1),
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        item2 = SimpleNamespace(
            name="item2",
            location=SimpleNamespace(file="/workspace/file.syn", line=20, column=1),
            extra_fields={"CODE": ["cancer"]},
            chains=[]
        )

        code_usage = {
            "smoking": [item1],
            "cancer": [item2]
        }

        cached = _make_cached(ontology_index=ontology_index, code_usage=code_usage)
        result = get_ontology_annotations(cached)

        assert result["success"] is True
        assert len(result["annotations"]) == 2
        codes = [a["code"] for a in result["annotations"]]
        assert "smoking" in codes
        assert "cancer" in codes

    def test_concept_without_occurrences(self):
        """Deve incluir conceitos sem occurrences."""
        ontology_index = {
            "unused_concept": SimpleNamespace(location=None)
        }
        code_usage = {}

        cached = _make_cached(ontology_index=ontology_index, code_usage=code_usage)
        result = get_ontology_annotations(cached)

        assert result["success"] is True
        assert len(result["annotations"]) == 1
        assert result["annotations"][0]["code"] == "unused_concept"
        assert result["annotations"][0]["occurrences"] == []


class TestBuildOccurrences:
    """Testa construção de occurrences."""

    def test_with_extra_fields(self):
        """Deve extrair occurrences de extra_fields."""
        item = SimpleNamespace(
            name="test_item",
            location=SimpleNamespace(file="/workspace/file.syn", line=10, column=5),
            extra_fields={"CODE": ["smoking", "health"]},
            chains=[]
        )

        occurrences = _build_occurrences(
            code="smoking",
            items=[item],
            workspace_root=Path("/workspace"),
            active_file=None
        )

        assert len(occurrences) == 1
        occ = occurrences[0]
        assert occ["itemName"] == "test_item"
        assert occ["line"] == 10
        assert occ["column"] == 5
        assert occ["context"] == "code"
        assert occ["field"] == "CODE"

    def test_with_chains(self):
        """Deve extrair occurrences de chains."""
        chain = ("smoking", "causes", "cancer")
        item = SimpleNamespace(
            name="test_item",
            location=SimpleNamespace(file="/workspace/file.syn", line=15, column=1),
            extra_fields={},
            chains=[chain]
        )

        occurrences = _build_occurrences(
            code="smoking",
            items=[item],
            workspace_root=None,
            active_file=None
        )

        assert len(occurrences) == 1
        occ = occurrences[0]
        assert occ["context"] == "chain"
        assert occ["field"] == "CHAIN"

    def test_item_without_location(self):
        """Deve ignorar items sem location."""
        item = SimpleNamespace(
            name="test_item",
            location=None,
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        occurrences = _build_occurrences(
            code="smoking",
            items=[item],
            workspace_root=None,
            active_file=None
        )

        assert len(occurrences) == 0

    def test_relative_path(self):
        """Deve relativizar paths ao workspace."""
        item = SimpleNamespace(
            name="test_item",
            location=SimpleNamespace(
                file="/workspace/data/file.syn",
                line=10,
                column=1
            ),
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        occurrences = _build_occurrences(
            code="smoking",
            items=[item],
            workspace_root=Path("/workspace"),
            active_file=None
        )

        assert len(occurrences) == 1
        assert not Path(occurrences[0]["file"]).is_absolute()
        assert "data" in occurrences[0]["file"]


class TestFindCodeInItem:
    """Testa busca de code em item individual."""

    def test_code_in_code_field(self):
        """Deve detectar code em campo CODE."""
        item = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(line=10, column=1),
            extra_fields={"CODE": ["smoking"]},
            chains=[]
        )

        occurrences = _find_code_in_item("smoking", item, "file.syn", "item1")

        assert len(occurrences) == 1
        assert occurrences[0]["context"] == "code"
        assert occurrences[0]["field"] == "CODE"

    def test_code_in_chain_field(self):
        """Deve detectar code em campo CHAIN."""
        item = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(line=10, column=1),
            extra_fields={"CHAIN": ["smoking-causes-cancer"]},
            chains=[]
        )

        occurrences = _find_code_in_item("smoking", item, "file.syn", "item1")

        assert len(occurrences) == 1
        assert occurrences[0]["context"] == "chain"
        assert occurrences[0]["field"] == "CHAIN"

    def test_code_in_multiple_fields(self):
        """Deve detectar code em múltiplos campos."""
        item = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(line=10, column=1),
            extra_fields={
                "CODE": ["smoking"],
                "CHAIN": ["smoking-causes-cancer"]
            },
            chains=[]
        )

        occurrences = _find_code_in_item("smoking", item, "file.syn", "item1")

        assert len(occurrences) == 2

    def test_code_not_found(self):
        """Deve retornar lista vazia quando code não encontrado."""
        item = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(line=10, column=1),
            extra_fields={"CODE": ["other_code"]},
            chains=[]
        )

        occurrences = _find_code_in_item("smoking", item, "file.syn", "item1")

        assert len(occurrences) == 0

    def test_item_without_extra_fields(self):
        """Deve lidar com item sem extra_fields."""
        item = SimpleNamespace(
            name="item1",
            location=SimpleNamespace(line=10, column=1),
            chains=[]
        )

        occurrences = _find_code_in_item("smoking", item, "file.syn", "item1")

        assert len(occurrences) == 0
