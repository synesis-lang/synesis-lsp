"""Smoke tests for synesis-lsp server module.

These verify the module is importable, the splash screen produces expected
output, and the entry point is callable — without ever starting the STDIO loop.
"""

from __future__ import annotations

import io
import sys
from importlib.metadata import version


def test_server_module_is_importable():
    import synesis_lsp.server  # noqa: F401 (import is the test)


def test_splash_writes_to_stderr():
    from synesis_lsp.server import _splash

    buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    try:
        _splash()
    finally:
        sys.stderr = old_stderr

    out = buf.getvalue()
    assert "SYNESIS LANGUAGE SERVER" in out
    assert version("synesis-lsp") in out


def test_splash_mentions_registered_capabilities():
    from synesis_lsp.server import _splash

    buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    try:
        _splash()
    finally:
        sys.stderr = old_stderr

    out = buf.getvalue()
    assert "Registered Capabilities:" in out
    assert "Semantic Tokens" in out


def test_main_is_callable():
    from synesis_lsp import server

    assert callable(server.main)
