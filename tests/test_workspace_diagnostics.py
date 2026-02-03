"""
Testes para synesis_lsp/workspace_diagnostics.py

Cobertura:
- Validação de workspace completo
- Descoberta de arquivos Synesis
- Validação de arquivos individuais
- Tratamento de erros
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from synesis_lsp.workspace_diagnostics import (
    compute_workspace_diagnostics,
    _find_synesis_files,
    validate_workspace_file,
)


class TestComputeWorkspaceDiagnostics:
    """Testa validação de workspace completo."""

    def test_empty_workspace(self):
        """Deve retornar dict vazio para workspace vazio."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            def validate_func(uri, file_path):
                return []

            result = compute_workspace_diagnostics(tmppath, validate_func)
            assert result == {}

    def test_with_synesis_files(self):
        """Deve validar todos os arquivos Synesis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Criar arquivos
            (tmppath / "file1.syn").write_text("SOURCE: test\nEND")
            (tmppath / "file2.syn").write_text("SOURCE: test\nEND")
            (tmppath / "file3.txt").write_text("Not a Synesis file")

            def validate_func(uri, file_path):
                return []

            result = compute_workspace_diagnostics(tmppath, validate_func)

            # Deve validar apenas .syn files
            assert len(result) == 2

    def test_with_diagnostics(self):
        """Deve retornar diagnósticos para arquivos com erros."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file1.syn").write_text("SOURCE: test\nEND")

            def validate_func(uri, file_path):
                # Simular erro
                return [
                    Diagnostic(
                        range=Range(
                            start=Position(line=0, character=0),
                            end=Position(line=0, character=1)
                        ),
                        severity=DiagnosticSeverity.Error,
                        message="Test error"
                    )
                ]

            result = compute_workspace_diagnostics(tmppath, validate_func)

            assert len(result) == 1
            uri = list(result.keys())[0]
            assert len(result[uri]) == 1
            assert result[uri][0].message == "Test error"

    def test_nonexistent_workspace(self):
        """Deve lidar com workspace inexistente."""
        nonexistent = Path("/nonexistent/workspace")

        def validate_func(uri, file_path):
            return []

        result = compute_workspace_diagnostics(nonexistent, validate_func)
        assert result == {}

    def test_subdirectories(self):
        """Deve encontrar arquivos em subdiretórios."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Criar estrutura de diretórios
            subdir = tmppath / "data"
            subdir.mkdir()
            (subdir / "file1.syn").write_text("SOURCE: test\nEND")

            nested = subdir / "nested"
            nested.mkdir()
            (nested / "file2.syn").write_text("SOURCE: test\nEND")

            def validate_func(uri, file_path):
                return []

            result = compute_workspace_diagnostics(tmppath, validate_func)

            assert len(result) == 2

    def test_validation_error_handling(self):
        """Deve continuar validação mesmo se um arquivo falhar."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file1.syn").write_text("SOURCE: test\nEND")
            (tmppath / "file2.syn").write_text("SOURCE: test\nEND")

            call_count = [0]

            def validate_func(uri, file_path):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Validation error")
                return []

            result = compute_workspace_diagnostics(tmppath, validate_func)

            # Deve processar todos os arquivos (mesmo com erro no primeiro)
            assert len(result) >= 1


class TestFindSynesisFiles:
    """Testa descoberta de arquivos Synesis."""

    def test_find_syn_files(self):
        """Deve encontrar arquivos .syn."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file1.syn").write_text("test")
            (tmppath / "file2.syn").write_text("test")

            files = _find_synesis_files(tmppath)
            assert len(files) == 2

    def test_find_all_extensions(self):
        """Deve encontrar todos os tipos de arquivos Synesis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "data.syn").write_text("test")
            (tmppath / "project.synp").write_text("test")
            (tmppath / "template.synt").write_text("test")
            (tmppath / "ontology.syno").write_text("test")

            files = _find_synesis_files(tmppath)
            assert len(files) == 4

    def test_ignore_non_synesis_files(self):
        """Deve ignorar arquivos não-Synesis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file.syn").write_text("test")
            (tmppath / "file.txt").write_text("test")
            (tmppath / "file.md").write_text("test")

            files = _find_synesis_files(tmppath)
            assert len(files) == 1

    def test_recursive_search(self):
        """Deve buscar recursivamente em subdiretórios."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            (tmppath / "root.syn").write_text("test")

            subdir = tmppath / "sub"
            subdir.mkdir()
            (subdir / "sub.syn").write_text("test")

            nested = subdir / "nested"
            nested.mkdir()
            (nested / "nested.syn").write_text("test")

            files = _find_synesis_files(tmppath)
            assert len(files) == 3

    def test_empty_directory(self):
        """Deve retornar lista vazia para diretório vazio."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            files = _find_synesis_files(tmppath)
            assert len(files) == 0


class TestValidateWorkspaceFile:
    """Testa validação de arquivo individual."""

    def test_valid_file(self):
        """Deve validar arquivo correto."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            test_file = tmppath / "test.syn"
            test_file.write_text("SOURCE: test\nEND")

            def validate_single_file_func(source, uri):
                # Simular ValidationResult vazio (sem erros)
                return SimpleNamespace(errors=[], warnings=[], info=[])

            diagnostics = validate_workspace_file(
                test_file.as_uri(),
                test_file,
                validate_single_file_func
            )

            assert len(diagnostics) == 0

    def test_file_with_errors(self):
        """Deve retornar diagnósticos para arquivo com erros."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            test_file = tmppath / "test.syn"
            test_file.write_text("INVALID SYNTAX")

            def validate_single_file_func(source, uri):
                # Simular ValidationResult com erro
                error = SimpleNamespace(
                    location=SimpleNamespace(file=str(test_file), line=1, column=1),
                    severity=SimpleNamespace(value="ERROR"),
                    message="Syntax error"
                )
                error.to_diagnostic = lambda: "Syntax error"
                return SimpleNamespace(errors=[error], warnings=[], info=[])

            diagnostics = validate_workspace_file(
                test_file.as_uri(),
                test_file,
                validate_single_file_func
            )

            assert len(diagnostics) > 0

    def test_file_read_error(self):
        """Deve lidar com erro ao ler arquivo."""
        from tempfile import gettempdir
        nonexistent = Path(gettempdir()) / "nonexistent_test_file_12345.syn"

        def validate_single_file_func(source, uri):
            return SimpleNamespace(errors=[], warnings=[], info=[])

        diagnostics = validate_workspace_file(
            nonexistent.as_uri(),
            nonexistent,
            validate_single_file_func
        )

        # Deve retornar lista vazia em caso de erro
        assert diagnostics == []

    def test_validation_exception(self):
        """Deve lidar com exceção na validação."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            test_file = tmppath / "test.syn"
            test_file.write_text("SOURCE: test\nEND")

            def validate_single_file_func(source, uri):
                raise Exception("Validation failed")

            diagnostics = validate_workspace_file(
                test_file.as_uri(),
                test_file,
                validate_single_file_func
            )

            # Deve retornar lista vazia em caso de exceção
            assert diagnostics == []
