"""
test_server_diagnostics.py - Integration tests for diagnostic publishing

Propósito:
    Validar que validate_document publica diagnostics corretamente,
    incluindo template diagnostics.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_validate_document_publishes():
    """validate_document should call publish_diagnostics - Task 1.4."""
    from synesis_lsp.server import validate_document

    ls = MagicMock()
    ls.validation_enabled = True
    ls.workspace_documents = {}

    source = "ITEM: item1\nEND\n"
    ls.workspace.get_document.return_value = SimpleNamespace(source=source)

    # Mock validate_single_file to return result with no errors
    with patch('synesis_lsp.server.validate_single_file') as mock_validate:
        mock_validate.return_value = SimpleNamespace(
            errors=[],
            warnings=[],
            info=[]
        )

        validate_document(ls, "file:///test.syn")

        # Should call publish_diagnostics
        ls.publish_diagnostics.assert_called_once()
        call_args = ls.publish_diagnostics.call_args
        assert call_args[0][0] == "file:///test.syn"
        assert isinstance(call_args[0][1], list)


def test_validate_document_template_integration():
    """Template diagnostics should be included - Task 1.4."""
    from synesis_lsp.server import validate_document

    ls = MagicMock()
    ls.validation_enabled = True
    ls.workspace_documents = {}

    source = "ITEM: item1\nunknown_field: test\nEND\n"
    ls.workspace.get_document.return_value = SimpleNamespace(source=source)

    # Mock template with field specs
    template = SimpleNamespace(
        field_specs={"note": SimpleNamespace(scope=SimpleNamespace(name="ITEM"))},
        required_fields={},
        bundled_fields={},
        forbidden_fields={}
    )

    with patch('synesis_lsp.server.validate_single_file') as mock_validate, \
         patch('synesis_lsp.server._get_cached_for_uri') as mock_cached:

        mock_validate.return_value = SimpleNamespace(errors=[], warnings=[], info=[])
        mock_cached.return_value = SimpleNamespace(
            result=SimpleNamespace(template=template)
        )

        validate_document(ls, "file:///test.syn")

        # Should publish diagnostics including template errors
        ls.publish_diagnostics.assert_called_once()
        diagnostics = ls.publish_diagnostics.call_args[0][1]

        # Should have at least one diagnostic for unknown_field
        assert len(diagnostics) > 0
        assert any("unknown_field" in d.message for d in diagnostics)


def test_validate_document_disabled():
    """Validation disabled should clear diagnostics - Task 1.4."""
    from synesis_lsp.server import validate_document

    ls = MagicMock()
    ls.validation_enabled = False

    validate_document(ls, "file:///test.syn")

    # Should publish empty list
    ls.publish_diagnostics.assert_called_once_with("file:///test.syn", [])


def test_debug_diagnostics_command():
    """Debug command should return diagnostic system status - Task 1.4."""
    from synesis_lsp.server import debug_diagnostics

    ls = MagicMock()
    ls.validation_enabled = True

    # Test without URI
    result = debug_diagnostics(ls, {})
    assert result["success"] is True
    assert "status" in result
    assert result["status"]["validation_enabled"] is True
    assert "template_diagnostics_module" in result["status"]

    # Test with URI
    template = SimpleNamespace(
        field_specs={"code": SimpleNamespace(), "note": SimpleNamespace()}
    )

    with patch('synesis_lsp.server._get_cached_for_uri') as mock_cached:
        mock_cached.return_value = SimpleNamespace(
            result=SimpleNamespace(template=template)
        )

        result = debug_diagnostics(ls, {"uri": "file:///test.syn"})

        assert result["success"] is True
        assert result["status"]["cached_available"] is True
        assert result["status"]["template_available"] is True
        assert "template_fields" in result["status"]
        assert "code" in result["status"]["template_fields"]
        assert "note" in result["status"]["template_fields"]


def test_debug_diagnostics_no_cache():
    """Debug command handles missing cache gracefully - Task 1.4."""
    from synesis_lsp.server import debug_diagnostics

    ls = MagicMock()
    ls.validation_enabled = True

    with patch('synesis_lsp.server._get_cached_for_uri') as mock_cached:
        mock_cached.return_value = None

        result = debug_diagnostics(ls, {"uri": "file:///test.syn"})

        assert result["success"] is True
        assert result["status"]["cached_available"] is False
