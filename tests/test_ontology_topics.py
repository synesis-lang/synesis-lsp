"""
Testes para synesis_lsp/ontology_topics.py

Cobertura:
- Parsing de .syno com hierarquia
- Níveis corretos baseados em indentação
- Paths relativos ao workspace
- Hierarquia de children
- Arquivos vazios e inválidos
"""

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

import pytest

from synesis_lsp.ontology_topics import get_ontology_topics, _parse_syno_file


def _make_cached(ontology_index=None):
    """Cria CachedCompilation mock com ontology_index."""
    lp = SimpleNamespace(ontology_index=ontology_index or {})
    result = SimpleNamespace(linked_project=lp)
    return SimpleNamespace(result=result)


class TestGetOntologyTopics:
    """Testa extração de hierarquia de tópicos."""

    def test_no_cache(self):
        """Deve retornar erro quando não há cache."""
        result = get_ontology_topics(None)
        assert result["success"] is False
        assert "error" in result

    def test_empty_ontology(self):
        """Deve retornar lista vazia quando não há ontologia."""
        cached = _make_cached(ontology_index={})
        result = get_ontology_topics(cached)
        assert result["success"] is True
        assert result["topics"] == []

    def test_with_ontology_nodes(self):
        """Deve parsear arquivo .syno quando há conceitos."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"

            # Criar arquivo .syno com hierarquia
            syno_file.write_text(
                "Health\n"
                "    Smoking\n"
                "        Tobacco Use\n"
                "    Diseases\n"
                "        Cancer\n"
            )

            # Criar ontology_index mock
            ontology_index = {
                "Health": SimpleNamespace(
                    location=SimpleNamespace(file=str(syno_file), line=1)
                ),
                "Smoking": SimpleNamespace(
                    location=SimpleNamespace(file=str(syno_file), line=2)
                ),
                "Tobacco Use": SimpleNamespace(
                    location=SimpleNamespace(file=str(syno_file), line=3)
                ),
                "Diseases": SimpleNamespace(
                    location=SimpleNamespace(file=str(syno_file), line=4)
                ),
                "Cancer": SimpleNamespace(
                    location=SimpleNamespace(file=str(syno_file), line=5)
                ),
            }

            cached = _make_cached(ontology_index=ontology_index)
            result = get_ontology_topics(cached, workspace_root=tmppath)

            assert result["success"] is True
            assert len(result["topics"]) > 0

    def test_non_syno_files_ignored(self):
        """Deve ignorar conceitos que não vêm de arquivos .syno."""
        ontology_index = {
            "concept1": SimpleNamespace(
                location=SimpleNamespace(file="/path/file.syn", line=10)
            ),
        }
        cached = _make_cached(ontology_index=ontology_index)
        result = get_ontology_topics(cached)

        assert result["success"] is True
        assert result["topics"] == []

    def test_concepts_without_location(self):
        """Deve ignorar conceitos sem location."""
        ontology_index = {
            "concept1": SimpleNamespace(location=None),
            "concept2": SimpleNamespace(),
        }
        cached = _make_cached(ontology_index=ontology_index)
        result = get_ontology_topics(cached)

        assert result["success"] is True
        assert result["topics"] == []


class TestParseSynoFile:
    """Testa parsing de arquivo .syno individual."""

    def test_simple_hierarchy(self):
        """Deve parsear hierarquia simples."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_text("Root\n    Child1\n    Child2\n")

            concepts = [("Root", 1), ("Child1", 2), ("Child2", 3)]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 1
            root = topics[0]
            assert root["name"] == "Root"
            assert root["level"] == 0
            assert root["line"] == 1
            assert len(root["children"]) == 2
            assert root["children"][0]["name"] == "Child1"
            assert root["children"][1]["name"] == "Child2"

    def test_deep_hierarchy(self):
        """Deve parsear hierarquia com múltiplos níveis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_text(
                "Level0\n"
                "    Level1\n"
                "        Level2\n"
                "            Level3\n"
            )

            concepts = [
                ("Level0", 1),
                ("Level1", 2),
                ("Level2", 3),
                ("Level3", 4),
            ]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 1
            level0 = topics[0]
            assert level0["level"] == 0
            assert len(level0["children"]) == 1

            level1 = level0["children"][0]
            assert level1["level"] == 1
            assert len(level1["children"]) == 1

            level2 = level1["children"][0]
            assert level2["level"] == 2
            assert len(level2["children"]) == 1

            level3 = level2["children"][0]
            assert level3["level"] == 3
            assert len(level3["children"]) == 0

    def test_multiple_roots(self):
        """Deve parsear múltiplos tópicos raiz."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_text("Root1\n    Child1\nRoot2\n    Child2\n")

            concepts = [
                ("Root1", 1),
                ("Child1", 2),
                ("Root2", 3),
                ("Child2", 4),
            ]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 2
            assert topics[0]["name"] == "Root1"
            assert topics[1]["name"] == "Root2"
            assert len(topics[0]["children"]) == 1
            assert len(topics[1]["children"]) == 1

    def test_tab_indentation(self):
        """Deve suportar indentação com tabs."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_text("Root\n\tChild\n")

            concepts = [("Root", 1), ("Child", 2)]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 1
            assert len(topics[0]["children"]) == 1
            assert topics[0]["children"][0]["level"] == 1

    def test_empty_lines_ignored(self):
        """Deve ignorar linhas vazias."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_text("Root\n\n    Child\n\n")

            concepts = [("Root", 1), ("Child", 3)]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 1
            assert len(topics[0]["children"]) == 1

    def test_relative_path(self):
        """Deve retornar path relativo ao workspace."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            subdir = tmppath / "ontology"
            subdir.mkdir()
            syno_file = subdir / "test.syno"
            syno_file.write_text("Root\n")

            concepts = [("Root", 1)]
            topics = _parse_syno_file(syno_file, tmppath, concepts)

            assert len(topics) == 1
            # Path deve ser relativo ao workspace
            assert "ontology" in topics[0]["file"]
            assert not Path(topics[0]["file"]).is_absolute()

    def test_nonexistent_file(self):
        """Deve retornar lista vazia para arquivo inexistente."""
        nonexistent = Path("/nonexistent/file.syno")
        topics = _parse_syno_file(nonexistent, None, [])
        assert topics == []

    def test_unreadable_file(self):
        """Deve retornar lista vazia para arquivo ilegível."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syno_file = tmppath / "test.syno"
            syno_file.write_bytes(b"\xff\xfe\xfd")  # Bytes inválidos

            concepts = [("Root", 1)]
            topics = _parse_syno_file(syno_file, tmppath, concepts)
            assert topics == []
