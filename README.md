# synesis-lsp

**Real-time validation and language intelligence for Synesis projects.**

A Language Server Protocol (LSP) implementation that brings the full power of the Synesis compiler into VS Code and any LSP-compatible editor — diagnostics, hover, completion, semantic tokens, relation graphs, and more.

[![PyPI version](https://img.shields.io/pypi/v/synesis-lsp)](https://pypi.org/project/synesis-lsp/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/synesis-lsp)](https://pypi.org/project/synesis-lsp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/synesis-lang/synesis-lsp/blob/main/LICENSE)

> **Copyright (c) 2011–2026 Christian Maciel de Britto**
> [`https://github.com/synesis-lang`](https://github.com/synesis-lang) · [`ORCID`](https://orcid.org/0000-0003-1431-3924)

---

## What is synesis-lsp?

`synesis-lsp` is a **protocol adapter**, not a second parser. All validation is delegated entirely to the Synesis compiler — the server translates compiler output into LSP diagnostics and editor features. This means the language server and the CLI always agree: if `synesis check` passes, the editor shows no errors.

The result is a live editorial environment where ontological constraints, required fields, and relational rules are enforced as you type — with pedagogical error messages that explain *why* a construct is invalid, not just *that* it is.

---

## Features

- **Real-time validation** — syntax and semantic errors as you type, delegated to the Synesis compiler
- **Pedagogical diagnostics** — clear explanations of template rules, `REQUIRED`/`OPTIONAL`, `BUNDLE`, `ARITY`
- **Semantic tokens** — AST-driven syntax highlighting (not regex)
- **Document symbols** — structured outline of `SOURCE`, `ITEM`, `ONTOLOGY` blocks
- **Hover documentation** — field definitions, ontology entries, and template rules on hover
- **Completion** — context-aware suggestions for codes, bibrefs, relation types, and field names
- **Inlay hints** — inline field type annotations
- **Go-to-definition & Rename** — for bibrefs and ontology codes, across files
- **Relation graph** — Mermaid diagram of the current project's relational structure
- **Fuzzy matching** — suggestions for mistyped bibrefs and codes
- **Full file type support** — `.syn`, `.synp`, `.synt`, `.syno`

---

## Requirements

- Python 3.10+
- `synesis` compiler ≥ 0.5.5

---

## Installation

```bash
pip install synesis
pip install synesis-lsp
```

**From source:**
```bash
git clone https://github.com/synesis-lang/synesis.git
git clone https://github.com/synesis-lang/synesis-lsp.git

pip install -e synesis
pip install -e synesis-lsp
```

---

## Usage

### Standalone server (STDIO)

```bash
python -m synesis_lsp
```

The server communicates via JSON-RPC over STDIO and is compatible with any LSP client.

### VS Code

The **Synesis Explorer** extension manages the LSP server automatically. No manual configuration required — install the extension, open a Synesis project, and the server starts.

### Workspace requirements

For full semantic validation, the workspace should contain:

| File | Role |
|---|---|
| `*.synp` | Project file — **required** for full validation |
| `*.synt` | Template referenced by `.synp` |
| `*.bib` | BibTeX bibliography |
| `*.syn` | Annotation files |
| `*.syno` | Ontology files |

> Without a `.synp`, the LSP provides syntax validation and grammar keywords only — no template or ontology enforcement.

---

## Architecture

```
┌─────────────┐
│   VS Code   │  (or any LSP client)
└──────┬──────┘
       │ JSON-RPC / STDIO
       ▼
┌──────────────────────────────────┐
│   synesis_lsp.server             │
│                                  │
│  Handlers: did_open, did_change  │
│  Providers: tokens · symbols     │
│             hover · completion   │
│             definition · inlay   │
│             signature · rename   │
│  Commands:  loadProject · stats  │
│             explorer · graph     │
└──────┬───────────────────────────┘
       │ delegates all validation to
       ▼
┌──────────────────────────────────┐
│   synesis.lsp_adapter            │
│   validate_single_file()         │
│   Context discovery              │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   synesis.compiler               │
│   Lark LALR(1) parser            │
│   Semantic validator             │
│   ValidationResult               │
└──────────────────────────────────┘
```

**Design principle:** this layer never re-implements parsing or semantics. If a diagnostic is incorrect, the issue is in the compiler — reproduce it with `synesis check file.syn` and report in the [compiler issue tracker](https://github.com/synesis-lang/synesis/issues).

---

## Custom LSP Commands

Cross-file features (hover, definition, completion, rename, graph) depend on the workspace cache loaded via `synesis/loadProject`.

| Command | Description |
|---|---|
| `synesis/loadProject` | Load and cache the full project |
| `synesis/getProjectStats` | Compilation statistics |
| `synesis/getReferences` | All source references in scope |
| `synesis/getCodes` | All ontology codes in scope |
| `synesis/getRelations` | All declared relation types |
| `synesis/getRelationGraph` | Mermaid diagram of project relations |

---

## Compatibility

| Package | Latest | Requires synesis | Python |
|---|---|---|---|
| synesis | 0.6.0 | — | ≥ 3.10 |
| synesis-lsp | 0.16.0 | ≥ 0.5.5 | ≥ 3.10 |
| synesis-coder | 0.4.1 | ≥ 0.5.5 | ≥ 3.10 |
| synesis-graph | 0.2.0 | ≥ 0.5.5 | ≥ 3.10 |

---

## Troubleshooting

**`Error: Package 'synesis' not found`**
```bash
pip install synesis
```

**LSP does not validate after editing**

1. Check logs: *Output → Synesis LSP* in VS Code
2. Reload window: `Ctrl+Shift+P → Reload Window`
3. Ensure `.synp` references the correct template and bibliography
4. Look for log messages: `Projeto Synesis carregado`, `Template carregado`, `Bibliografia carregada`

**Incorrect diagnostics**

The LSP delegates all validation to the compiler. To isolate the issue:
```bash
synesis check your_file.syn
```
If the CLI also reports it, the issue is in the compiler — report it in the [compiler repository](https://github.com/synesis-lang/synesis/issues). If the CLI passes but the LSP flags it, report in the [LSP repository](https://github.com/synesis-lang/synesis-lsp/issues).

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/
pytest --cov=synesis_lsp tests/
```

**Contributing guidelines:**

- This server is a protocol adapter — do not implement parsing or semantics here
- All validation must use `synesis.lsp_adapter.validate_single_file`
- Always convert `SourceLocation` (1-based) to LSP `Range` (0-based)
- If you change error/result contracts, update `INTERFACES.md` and `converters.py`
- Keep the server resilient: exceptions must become diagnostics, never crashes

---

## Project Structure

```
synesis-lsp/
├── synesis_lsp/
│   ├── server.py            # LSP server (pygls)
│   ├── converters.py        # ValidationError → LSP Diagnostic
│   ├── cache.py             # Workspace cache
│   ├── semantic_tokens.py   # Semantic tokens
│   ├── symbols.py           # Document symbols
│   ├── hover.py             # Hover provider
│   ├── definition.py        # Go-to-definition
│   ├── completion.py        # Autocomplete
│   ├── inlay_hints.py       # Inlay hints
│   ├── graph.py             # Relation graph (Mermaid)
│   ├── rename.py            # Rename provider
│   └── explorer_requests.py # Custom explorer commands
├── tests/
├── INTERFACES.md            # Compiler ↔ LSP contracts
├── CHANGELOG.md
├── LICENSE
└── README.md
```

---

## Intellectual Genealogy

`synesis-lsp` is part of the Synesis ecosystem. The compiler and language it serves are the formal culmination of a research and development trajectory spanning more than a decade. See the [compiler README](https://github.com/synesis-lang/synesis#intellectual-genealogy) and the project's [NOTICE file](https://github.com/synesis-lang/synesis/blob/main/NOTICE) for the full intellectual genealogy and copyright notices for predecessor works.

---

## License

MIT — see [LICENSE](https://github.com/synesis-lang/synesis-lsp/blob/main/LICENSE).

> A license change to **AGPL-3.0-only** (with Synesis Data Output Exception) is planned for an upcoming release, aligned with the compiler.

---

## References

- [Synesis compiler](https://github.com/synesis-lang/synesis) — the core engine this server wraps
- [Synesis Explorer](https://github.com/synesis-lang/synesis-explorer) — VS Code extension
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [pygls Documentation](https://pygls.readthedocs.io/)
- [Interfaces and Contracts](https://github.com/synesis-lang/synesis-lsp/blob/main/INTERFACES.md)
- [Changelog](https://github.com/synesis-lang/synesis-lsp/blob/main/CHANGELOG.md)

---

## Author

**Dr. Christian Maciel de Britto**

[GitHub](https://github.com/synesis-lang) · [ORCID](https://orcid.org/0000-0003-1431-3924) · [Lattes](https://lattes.cnpq.br/2334832147379385)