# Synesis LSP

> **Real-time validation and language features for Synesis v1.1 files.**

A Language Server Protocol (LSP) implementation that provides diagnostics and editor features for Synesis projects in VSCode and other compatible editors.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Overview

Synesis LSP is a protocol adapter: it does not re-implement parsing or semantics. All validation is delegated to the Synesis compiler, and the server focuses on translating compiler output into LSP diagnostics and features.

## Features

- Real-time syntax and semantic validation (template rules, REQUIRED/OPTIONAL, BUNDLE, ARITY)
- Pedagogical diagnostics with clear explanations
- Automatic discovery of templates and bibliography
- Fuzzy matching for missing bibrefs
- Full support for `.syn`, `.synp`, `.synt`, `.syno`
- Semantic tokens for syntax highlighting
- Document symbols (SOURCE/ITEM/ONTOLOGY)
- Hover, completion, and inlay hints
- Go-to-definition and rename (bibrefs and codes)
- Relation graph generation (Mermaid)

## Requirements

- Python 3.10+
- Synesis compiler installed

## Installation

### From PyPI

```bash
pip install synesis
pip install synesis-lsp
```

### From Source

```bash
git clone https://github.com/synesis-lang/synesis.git
git clone https://github.com/synesis-lang/synesis-lsp.git

pip install -e synesis
pip install -e synesis-lsp
```

## Usage

### Standalone Server

```bash
python -m synesis_lsp
```

The server communicates via STDIO.

### VSCode

The Synesis Explorer extension manages the LSP server automatically.

### Synesis Workspace Requirements

For full semantic validation, the workspace should contain:
- A project file `*.synp` (required)
- A template `*.synt` referenced by the `.synp`
- Bibliography `*.bib`, annotations `*.syn`, and ontologies `*.syno` as needed

Notes:
- Multiple `.synt` files may exist, but the **only** valid one is the template referenced by `.synp`.
- Without a `.synp`, the LSP provides only syntax validation and grammar keywords.

## Project Structure

```
synesis-lsp/
├── synesis_lsp/           # Python package (server)
│   ├── __init__.py
│   ├── __main__.py        # Entry point (python -m synesis_lsp)
│   ├── server.py          # LSP server (pygls)
│   ├── converters.py      # ValidationError → LSP Diagnostic
│   ├── cache.py           # Workspace cache
│   ├── semantic_tokens.py # Semantic tokens
│   ├── symbols.py         # Document symbols
│   ├── hover.py           # Hover provider
│   ├── definition.py      # Go-to-definition
│   ├── completion.py      # Autocomplete
│   ├── inlay_hints.py     # Inlay hints
│   ├── explorer_requests.py # Custom explorer requests
│   ├── graph.py           # Relation graph (Mermaid)
│   ├── signature_help.py  # Signature help
│   └── rename.py          # Rename provider
├── tests/                 # Test suite
├── pyproject.toml         # Package configuration
├── INTERFACES.md          # Compiler ↔ LSP contracts
├── CHANGELOG.md           # Release history
├── LICENSE                # MIT License
└── README.md              # This file
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
pytest --cov=synesis_lsp tests/
```

## Development Notes

- This LSP is a protocol adapter; do not implement parsing/semantics here.
- All validation must use `synesis.lsp_adapter.validate_single_file`.
- Always convert `SourceLocation` (1-based) to LSP `Range` (0-based).
- If you change error/result contracts, update `INTERFACES.md` and `converters.py`.
- Keep the server resilient: exceptions must become diagnostics, never crashes.

## Architecture

```
┌─────────────┐
│   VSCode    │  (Editor)
└──────┬──────┘
       │ LSP Protocol (JSON-RPC via STDIO)
       ▼
┌─────────────────────────────────┐
│   synesis_lsp.server.py         │  (Python Server)
├─────────────────────────────────┤
│ • Handlers: did_open, did_change│
│ • Converters: Error → Diagnostic│
│ • Providers: tokens, symbols,   │
│   hover, completion, definition,│
│   inlay, signature, rename      │
│ • Commands: loadProject, stats, │
│   explorer, relation graph      │
└──────┬──────────────────────────┘
       │ imports
       ▼
┌─────────────────────────────────┐
│   synesis.lsp_adapter           │  (Compiler Adapter)
├─────────────────────────────────┤
│ • validate_single_file()        │
│ • Context discovery             │
└──────┬──────────────────────────┘
       │ uses
       ▼
┌─────────────────────────────────┐
│   synesis.compiler              │  (Compiler)
├─────────────────────────────────┤
│ • Lark Parser (LALR)            │
│ • SemanticValidator             │
│ • ValidationResult              │
└─────────────────────────────────┘
```

## Advanced Features

- Custom commands: `synesis/loadProject`, `synesis/getProjectStats`,
  `synesis/getReferences`, `synesis/getCodes`, `synesis/getRelations`,
  `synesis/getRelationGraph`
- Cross-file features (hover, definition, completion, rename, graph) depend
  on the workspace cache loaded via `synesis/loadProject`

## Troubleshooting

### Error: "Package 'synesis' not found"

```bash
pip install synesis
```

### LSP does not validate after editing

1. Check logs: **Output → Synesis LSP** in VSCode
2. Reload window: `Ctrl+Shift+P` → "Reload Window"
3. Ensure the `.synp` references the correct template and bibliography
4. Look for log messages like: `Projeto Synesis carregado`, `Template carregado`, `Bibliografia carregada`

### Incorrect diagnostics

The LSP uses the compiler output. If a diagnostic is wrong:
1. Test with CLI: `synesis check arquivo.syn`
2. If CLI also reports it, the bug is in the compiler
3. Report in the compiler issue tracker

## License

MIT License - Synesis Project

## Contributing

Contributions are welcome. Please follow the code conventions and add tests for new features.

## References

- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [pygls Documentation](https://pygls.readthedocs.io/)
- [Interfaces and Contracts](INTERFACES.md)
- [Changelog](CHANGELOG.md)
