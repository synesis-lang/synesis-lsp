# Synesis LSP ↔ extension contract

This directory is the **source of truth** for the JSON shape of the four custom
LSP requests the VS Code extension depends on:

| Request | Producer (this repo) | Consumer (synesis-vscode) |
|---|---|---|
| `synesis/getReferences` | `get_references` (`explorer_requests.py`) | `DataService.getReferences` |
| `synesis/getCodes` | `get_codes` (`explorer_requests.py`) | `DataService.getCodes` |
| `synesis/getRelations` | `get_relations` (`explorer_requests.py`) | `DataService.getRelations` |
| `synesis/getOntologyAnnotations` | `get_ontology_annotations` (`ontology_annotations.py`) | `DataService.getOntologyAnnotations` |

## Why this exists

The dedup bugs of Feb 2026 (CODE/CHAIN duplication) came from logic reimplemented
outside the compiler, on both sides of an *implicit* contract. This makes the
contract explicit and machine-checked (diagnostic D6 of the Golden Standard).

- `schemas/` — versioned JSON Schema (draft 2020-12) for each response.
- `examples/` — canonical payloads generated from real compiler output.

## How it is enforced

- **Producer (this repo):** `tests/test_contract.py` validates the *real* output
  of the four handlers — compiled from the `synesis` fixtures — against these
  schemas, plus the canonical examples.
- **Consumer (synesis-vscode):** `test/unit/contract.test.js` validates its test
  fixtures (`projectBuilder.js`) and a copy of these schemas/examples.

If either side drifts, its CI goes red. The extension keeps a **versioned copy**
under `synesis-vscode/test/contract/`; when a schema changes here, copy it there
in the same change (see the deprecation policy below).

## Versioning & deprecation policy

- The contract is versioned with the LSP package (`synesis-lsp` `0.16.0`).
- A **breaking** change to a response shape (removing/renaming a field, tightening
  a type, changing an enum) requires: a new schema revision here, the mirrored
  copy updated in `synesis-vscode`, both contract tests updated, and a CHANGELOG
  entry in both repos.
- Deprecation: a field being removed is announced in the CHANGELOG for at least
  one minor cycle before removal; removal happens only in a major (except for
  security fixes).
- Additive changes (new optional field) are backward-compatible and only need the
  schema plus a CHANGELOG note.

## Compatibility matrix

| synesis-vscode | requires synesis-lsp | contract |
|---|---|---|
| ≥ 0.6.4 | ≥ 0.16.0 | v1 (this directory) |
