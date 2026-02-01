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

__version__ = "1.0.3"
__all__ = ["server", "converters", "handlers"]
