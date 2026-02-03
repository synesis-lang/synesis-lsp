# LSP implementation notes (Code/Relation/Graph)

Date: 2026-02-02

## Problem summary
- The Code Explorer treeview expects each code to include `occurrences`.
- The LSP endpoint `synesis/getCodes` currently returns only:
  - `code`, `usageCount`, `ontologyDefined`
- Because `occurrences` are empty, the treeview has no children and click navigation is disabled.
-
- The Relation Explorer expects relations grouped into triplets with navigation.
- The LSP endpoint `synesis/getRelations` currently returns only:
  - `from`, `relation`, `to`
- Missing location data prevents click navigation; missing `type` degrades display.
-
- The Graph Viewer relies on `synesis/getRelationGraph` with a `bibref` filter.
- LSP returns a full graph without `bibref`, but returns an empty graph when `bibref` is provided (even when CHAINs exist).

## Target behavior
- Code Explorer must list codes and expand to occurrences.
- Clicking an occurrence should open the file at the correct line/column.
- This must work when LSP is enabled (LSP-first) with graceful fallback.
-
- Relation Explorer must list relations and expand to triplets.
- Clicking a triplet should open the originating file at the correct line/column.
-
- Graph Viewer must return a non-empty filtered graph when `bibref` has CHAINs.

## Required contract changes (preferred)
### Option A (recommended): extend `synesis/getCodes`
Add occurrences to the LSP response:

```
LspCodeOccurrence = {
  file: string,      // path relative to workspaceRoot
  line: number,      // 1-based
  column: number,    // 1-based
  context: 'code' | 'chain',
  field: string      // field name (e.g. CODE, CHAIN)
}

LspCode = {
  code: string,
  usageCount: number,
  ontologyDefined: boolean,
  occurrences: LspCodeOccurrence[]
}
```

### Option B: new endpoint `synesis/getCodeOccurrences`
- Keep `synesis/getCodes` unchanged for backward compatibility.
- New endpoint returns occurrences keyed by code:

```
{
  success: boolean,
  occurrences: [
    { code: string, occurrences: LspCodeOccurrence[] }
  ]
}
```

## Required contract changes for Relations
### Extend `synesis/getRelations` with location and type
Return the origin location for each relation triplet and the chain type:

```
LspRelation = {
  from: string,
  relation: string,
  to: string,
  type?: string,     // chain type/label, if available
  location?: {
    file: string,    // path relative to workspaceRoot
    line: number,    // 1-based
    column: number   // 1-based
  }
}
```

Notes:
- This enables click navigation in the Relation Explorer.
- `type` should match the chain parser type (e.g. qualified vs simple) if available.

## Required contract changes for Graph Viewer
### Fix `synesis/getRelationGraph` filtering by `bibref`
Observed: with `bibref` provided, the LSP returns `graph LR empty[...]` even when CHAINs exist.
The LSP should:
- Accept `bibref` with or without `@` prefix (normalize internally).
- Match bibrefs case-insensitively if the project format allows it.
- Ensure the filtering logic uses the same normalized bibref as the parsed items.

## Required diagnostics behavior (template field validation)
### Issue observed
- The extension relies on LSP diagnostics for validation.
- LSP does not implement `textDocument/diagnostic` (pull).
- On `textDocument/didOpen` with an invalid field name (e.g. `notes` instead of `note`),
  the server published **zero** diagnostics.

### Required LSP changes
Implement template-aware validation for `.syn` files:
- **Unknown field**: if a field name is not present in the template, emit an error.
- **Required fields**: emit errors for missing required fields (including required bundles).
- **Scope rules**: enforce SOURCE/ITEM/ONTOLOGY field scopes.
- **Helpful message**: include “Did you mean …?” suggestions when a similar field exists.

### Diagnostics transport
- Prefer `textDocument/publishDiagnostics` (push) on `didOpen`, `didChange`, `didSave`.
- Optional: add support for `textDocument/diagnostic` (pull) for VS Code’s new diagnostic API.

## Extension changes (consumer side)
### DataService (LspDataProvider.getCodes)
- Map LSP occurrences to the normalized shape expected by the explorers.
- Normalize paths and indexes:
  - `file` is relative -> convert to absolute with `path.resolve(workspaceRoot, file)`
  - `line` and `column` are 1-based -> convert to 0-based for VS Code

### CodeExplorer
- No functional change required if occurrences are present.
- Optional: if LSP returns no occurrences, consider a soft fallback that
  merges LSP code list with local regex occurrences (see fallback below).

### RelationExplorer
- No functional change required if `location` is present.
- If `location` is missing, the UI can still show triplets but click navigation
  will remain disabled.

## Fallback strategy (if LSP cannot be changed)
Implement a hybrid path in `DataService.getCodes()`:
1) Get codes from LSP to preserve `usageCount` and `ontologyDefined`.
2) Get occurrences from local regex provider.
3) Merge by `code`:
   - occurrences from regex
   - usageCount from LSP if present, otherwise occurrences length
   - ontologyDefined from LSP if present, otherwise false

This keeps LSP-first while restoring treeview functionality.

## Validation checklist
- LSP `getCodes` returns occurrences with correct shape and relative paths.
- Code Explorer:
  - shows children under each code
  - click opens correct file and position
- Verify line/column are correct (1-based from LSP, 0-based in VS Code).
- Test with codes in both `CODE` and `CHAIN` fields.
-
- LSP `getRelations` returns triplets with `location`.
- Relation Explorer:
  - shows children under each relation header
  - click opens correct file and position
-
- LSP `getRelationGraph`:
  - returns full graph without `bibref`
  - returns a non-empty graph when `bibref` has CHAINs

## Tests to add/update
- Unit tests for `LspDataProvider.getCodes` mapping:
  - relative -> absolute path
  - 1-based -> 0-based conversion
- Explorer tests:
  - occurrences render with basename
  - click command includes correct args

## Notes from current LSP run
- `synesis/loadProject` now detects `.synp` when `workspaceRoot` is a file or folder.
- `synesis/getCodes` returns `code`, `usageCount`, `ontologyDefined`, and `occurrences`
  with location and field/context data.
- `synesis/getRelations` returns `from`, `relation`, `to` plus `location` and `type`.
- `synesis/getRelationGraph` works both without `bibref` and with valid `bibref`
  filters (non-empty graphs for CHAINs).

## Latest verification (local synesis-lsp on 2026-02-02)
### What is working
- **Template field validation**: diagnostics are now emitted for invalid fields
  (e.g. `notes` -> “Campo desconhecido … você quis dizer: note?”).
- **loadProject discovery**: `.synp` is detected from file or folder workspace roots.
- **getCodes (Option A)**: returns non-empty codes with `occurrences` (location + context).
- **getRelations**: includes `location` and `type` for click navigation.
- **getRelationGraph + bibref filter**: returns non-empty graphs for valid bibrefs.
- **Tests**: `pytest` → `196 passed` (0.94s).

### Still failing / regressed
- Nenhum problema observado nesta verificação.

## Priority fix checklist (LSP)
1) **Fix project discovery** for `loadProject` (root `.synp` should be detected).
2) **Fix `getCodes`** to return non-empty codes and include occurrences/locations.
3) **Add `location` to `getRelations`** (1-based line/column, path relative to root).
4) **Fix `getRelationGraph` bibref filter** (normalize `@`, case, and matching).

## Minimal test matrix
- `loadProject` on:
  - `test/fixtures/lsp-project` (must succeed)
  - `test/fixtures/bibliometrics` (must succeed)
- `getCodes` on `bibliometrics`:
  - non-empty codes
  - includes occurrences with location and field/context
- `getRelations` on `bibliometrics`:
  - non-empty relations
  - each relation includes location
- `getRelationGraph`:
  - no bibref -> large graph
  - `@ashworth2019` -> non-empty graph

---

Option A foi implementada no LSP. Se quiser, posso ajustar a extensão para o
fallback híbrido ou revisar a parte de UI.
