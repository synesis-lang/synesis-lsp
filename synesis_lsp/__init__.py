"""
synesis_lsp - Language Server Protocol para Synesis v1.1

Propósito:
    Servidor LSP que fornece validação em tempo real para arquivos Synesis
    no VSCode e outros editores compatíveis com LSP.

Componentes principais:
    - server: Servidor principal usando pygls
    - converters: Conversão ValidationError → LSP Diagnostic
    - handlers: Event handlers para ciclo de vida de documentos

Dependências críticas:
    - pygls: Framework LSP
    - synesis: Compilador e lsp_adapter

Exemplo de uso:
    python -m synesis_lsp

Notas de implementação:
    - Comunica via STDIO com o cliente VSCode
    - Debounce de 300ms para validação
    - Usa synesis.lsp_adapter para validação

Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP
"""
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path
import re


def _read_version_from_pyproject() -> str:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'(?m)^version = "([^"]+)"\s*$', text)
    return match.group(1) if match else "0.0.0"


try:
    __version__ = _pkg_version("synesis-lsp")
except PackageNotFoundError:
    __version__ = _read_version_from_pyproject()

__all__ = ["server", "converters", "handlers"]
