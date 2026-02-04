"""
Testes para synesis_lsp/abstract_viewer.py

Cobertura:
- Extração de campo ABSTRACT de arquivos .syn
- Parsing de ABSTRACT multiline
- ABSTRACT não encontrado
- Arquivo inexistente
- Tipo de arquivo inválido
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from synesis_lsp.abstract_viewer import (
    get_abstract,
    _parse_abstract_from_file,
    _extract_from_linked_project,
)


class TestGetAbstract:
    """Testa extração de campo ABSTRACT."""

    def test_no_file_path(self):
        """Deve retornar erro quando file_path não fornecido."""
        result = get_abstract(None)
        assert result["success"] is False
        assert "error" in result

    def test_file_not_found(self):
        """Deve retornar erro quando arquivo não existe."""
        result = get_abstract("/nonexistent/file.syn")
        assert result["success"] is False
        assert "não encontrado" in result["error"].lower()

    def test_invalid_file_type(self):
        """Deve retornar erro para tipo de arquivo inválido."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            invalid_file = tmppath / "test.txt"
            invalid_file.write_text("Some content")

            result = get_abstract(str(invalid_file))
            assert result["success"] is False
            assert "deve ser .syn ou .synp" in result["error"].lower()

    def test_extract_simple_abstract(self):
        """Deve extrair ABSTRACT simples."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "ABSTRACT: This is a simple abstract.\n"
                "ITEM: item1\n"
                "END\n"
            )

            result = get_abstract(str(syn_file))
            assert result["success"] is True
            assert result["abstract"] == "This is a simple abstract."
            assert result["line"] == 2

    def test_extract_multiline_abstract(self):
        """Deve extrair ABSTRACT multiline."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "ABSTRACT: This is a multiline abstract.\n"
                "    It continues here.\n"
                "    And here.\n"
                "ITEM: item1\n"
                "END\n"
            )

            result = get_abstract(str(syn_file))
            assert result["success"] is True
            assert "multiline" in result["abstract"]
            assert "continues here" in result["abstract"]
            assert "And here" in result["abstract"]

    def test_abstract_not_found(self):
        """Deve retornar erro quando ABSTRACT não encontrado."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "ITEM: item1\n"
                "CODE: code1\n"
                "END\n"
            )

            result = get_abstract(str(syn_file))
            assert result["success"] is False
            assert "não encontrado" in result["error"].lower()

    def test_relative_path_with_workspace(self):
        """Deve resolver path relativo com workspace_root."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            subdir = tmppath / "data"
            subdir.mkdir()
            syn_file = subdir / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "ABSTRACT: Test abstract.\n"
                "END\n"
            )

            result = get_abstract("data/test.syn", workspace_root=tmppath)
            assert result["success"] is True
            assert result["abstract"] == "Test abstract."

    def test_case_insensitive_abstract(self):
        """Deve reconhecer ABSTRACT independente de case."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "abstract: Test abstract.\n"
                "END\n"
            )

            result = get_abstract(str(syn_file))
            assert result["success"] is True
            assert result["abstract"] == "Test abstract."

    def test_extract_from_bibliography(self):
        """Deve extrair ABSTRACT do .bib quando disponível no cache."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text("SOURCE: test\nITEM: x\nEND\n")

            bib_file = tmppath / "refs.bib"
            bib_file.write_text("@misc{test, abstract={Bib abstract.}}")

            source = SimpleNamespace(
                bibref="test",
                location=SimpleNamespace(file=str(syn_file), line=1),
                extra_fields={},
            )
            lp = SimpleNamespace(sources={"test": source})
            bibliography = {
                "test": {
                    "abstract": "Bib abstract.",
                    "location": {"file": str(bib_file), "line": 10},
                }
            }
            cached = SimpleNamespace(
                result=SimpleNamespace(
                    bibliography=bibliography,
                    linked_project=lp,
                )
            )

            result = get_abstract(
                str(syn_file),
                cached_result=cached,
                workspace_root=tmppath,
            )

            assert result["success"] is True
            assert result["abstract"] == "Bib abstract."
            assert "refs.bib" in result["file"]


class TestParseAbstractFromFile:
    """Testa parsing direto de arquivo."""

    def test_simple_parsing(self):
        """Deve parsear ABSTRACT simples."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text("ABSTRACT: Simple text.\n")

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is True
            assert result["abstract"] == "Simple text."

    def test_multiline_parsing(self):
        """Deve parsear ABSTRACT multiline com indentação."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "ABSTRACT: First line.\n"
                "    Second line.\n"
                "    Third line.\n"
                "CODE: code1\n"
            )

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is True
            lines = result["abstract"].split("\n")
            assert len(lines) == 3
            assert "First line" in lines[0]
            assert "Second line" in lines[1]
            assert "Third line" in lines[2]

    def test_empty_lines_in_abstract(self):
        """Deve lidar com linhas vazias dentro do ABSTRACT."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "ABSTRACT: First paragraph.\n"
                "\n"
                "    Second paragraph.\n"
                "CODE: code1\n"
            )

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is True
            # Deve continuar até encontrar campo não indentado

    def test_abstract_at_end_of_file(self):
        """Deve extrair ABSTRACT no final do arquivo."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_text(
                "SOURCE: test\n"
                "ABSTRACT: Last field.\n"
                "    Continues.\n"
            )

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is True
            assert "Last field" in result["abstract"]
            assert "Continues" in result["abstract"]

    def test_relative_path_in_result(self):
        """Deve retornar path relativo ao workspace."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            subdir = tmppath / "documents"
            subdir.mkdir()
            syn_file = subdir / "test.syn"
            syn_file.write_text("ABSTRACT: Test.\n")

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is True
            assert "documents" in result["file"]
            assert not Path(result["file"]).is_absolute()

    def test_unreadable_file(self):
        """Deve retornar erro para arquivo ilegível."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            syn_file = tmppath / "test.syn"
            syn_file.write_bytes(b"\xff\xfe\xfd")  # Bytes inválidos

            result = _parse_abstract_from_file(syn_file, tmppath)
            assert result["success"] is False
            assert "error" in result


class TestExtractFromLinkedProject:
    """Testa extração via LinkedProject."""

    def test_extract_from_source(self):
        """Deve extrair ABSTRACT de source no LinkedProject."""
        test_file = Path("/workspace/test.syn")

        source = SimpleNamespace(
            file=str(test_file),
            extra_fields={"ABSTRACT": ["This is the abstract.", "Multiline."]},
            location=SimpleNamespace(line=5)
        )

        lp = SimpleNamespace(sources={"test": source})

        result = _extract_from_linked_project(lp, test_file)

        assert result is not None
        assert result["success"] is True
        assert "This is the abstract" in result["abstract"]
        assert "Multiline" in result["abstract"]
        assert result["line"] == 5

    def test_source_without_abstract(self):
        """Deve retornar None quando source não tem ABSTRACT."""
        test_file = Path("/workspace/test.syn")

        source = SimpleNamespace(
            file=str(test_file),
            extra_fields={"CODE": ["code1"]},
            location=SimpleNamespace(line=5)
        )

        lp = SimpleNamespace(sources={"test": source})

        result = _extract_from_linked_project(lp, test_file)

        assert result is None

    def test_file_not_in_sources(self):
        """Deve retornar None quando arquivo não está nos sources."""
        test_file = Path("/workspace/test.syn")
        other_file = Path("/workspace/other.syn")

        source = SimpleNamespace(
            file=str(other_file),
            extra_fields={"ABSTRACT": ["Text"]},
            location=SimpleNamespace(line=5)
        )

        lp = SimpleNamespace(sources={"other": source})

        result = _extract_from_linked_project(lp, test_file)

        assert result is None

    def test_abstract_as_string(self):
        """Deve lidar com ABSTRACT como string simples."""
        test_file = Path("/workspace/test.syn")

        source = SimpleNamespace(
            file=str(test_file),
            extra_fields={"ABSTRACT": "Simple string abstract."},
            location=SimpleNamespace(line=3)
        )

        lp = SimpleNamespace(sources={"test": source})

        result = _extract_from_linked_project(lp, test_file)

        assert result is not None
        assert result["abstract"] == "Simple string abstract."

    def test_empty_sources(self):
        """Deve retornar None quando sources vazio."""
        test_file = Path("/workspace/test.syn")
        lp = SimpleNamespace(sources={})

        result = _extract_from_linked_project(lp, test_file)

        assert result is None
