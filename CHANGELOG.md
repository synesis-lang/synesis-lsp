# Changelog

All notable changes to the Synesis LSP project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Centralizar lista de comandos/keywords no compilador/gramatica e expor ao LSP, evitando duplicacao em `template_diagnostics.py`.

## [0.14.3] - 2026-02-03

### Changed
- Versao agora derivada do `pyproject.toml` via metadata do pacote, evitando duplicacao.

## [0.14.2] - 2026-02-03

### Fixed
- Code explorer now indexes `CHAIN` fields and `ChainNode` occurrences correctly (codes + positions).
- Ontology annotations now detect `CHAIN` occurrences and merge chain usage with code usage.
- Relation graphs now filter by current SOURCE bibref, reducing graph size to relevant chains.
- Hover now recognizes compound bibrefs with hyphens and dots (e.g. `@martinez-gordon2022`).

### Planned

- Code lens (reference counts)
- Call hierarchy support
- Folding ranges

## [0.14.1] - 2026-02-03

### Fixed

- Relations now resolve locations via `relation_index` when available (compiler provenance).
- Explorer requests fall back to `item.source.location` when `item.location` is missing.
- Ontology annotations file filtering now normalizes `file://` URIs.

## [0.14.0] - 2026-02-03

### Added

- Command `synesis/debug/projectInfo` to expose project stats and timing metadata.

### Changed

- `synesis/loadProject` now supports `synpPath` and reuses cached data when the workspace fingerprint is unchanged.
- `synesis/getCodes` now returns ontology codes even when `usageCount` is 0.
- Relation and ontology requests reuse cached results to reduce repeated computation.

### Fixed

- Graph filtering by bibref now includes chain-based relations (`ChainNode`).
- Hover/definition/references/rename normalize ontology codes and bibrefs consistently.
- `synesis/getAbstract` now resolves abstracts from the bibliography referenced by the project.

## [0.13.0] - 2026-02-02

### Added - Phase 3: Advanced LSP Features

**Task 3.1: textDocument/references**
- **New LSP feature**: Implementa Find All References para codes e bibrefs
- **Implementation**: New module `synesis_lsp/references.py`
  - `compute_references()`: Main function finding all references to symbols
  - `_find_code_references()`: Finds all code usages across workspace
  - `_find_bibref_references()`: Finds all bibref usages
  - `_convert_to_lsp_location()`: Converts 1-based compiler coordinates to 0-based LSP
  - Supports `includeDeclaration` parameter to include/exclude definition
- **Integration**: Feature handler added to `server.py` for TEXT_DOCUMENT_REFERENCES
- **Tests**: 11 tests added (`test_references.py` - NEW FILE)
  - Tests for code and bibref references
  - Tests for declaration inclusion/exclusion
  - Tests for bibref normalization

**Task 3.2: textDocument/codeAction**
- **New LSP feature**: Implementa Code Actions (Quick Fixes) para erros comuns
- **Implementation**: New module `synesis_lsp/code_actions.py`
  - `compute_code_actions()`: Generates code actions for diagnostics
  - `_suggest_field_corrections()`: Suggests similar field names using Levenshtein distance
  - `_suggest_required_field()`: Suggests inserting missing required fields
  - `_levenshtein_distance()`: Calculates edit distance for smart suggestions
  - Quick fixes for: unknown fields, required fields missing, typos
- **Smart suggestions**: Uses edit distance algorithm (max 3 changes) to find similar fields
- **Integration**: Feature handler added to `server.py` for TEXT_DOCUMENT_CODE_ACTION
- **Tests**: 24 tests added (`test_code_actions.py` - NEW FILE)
  - Tests for field correction suggestions
  - Tests for Levenshtein distance calculation
  - Tests for field name extraction from diagnostic messages
  - Tests for multiple suggestions and filtering

**Task 3.3: Workspace Diagnostics**
- **New feature**: Valida todos os arquivos Synesis no workspace, não apenas abertos
- **Implementation**: New module `synesis_lsp/workspace_diagnostics.py`
  - `compute_workspace_diagnostics()`: Validates all Synesis files in workspace
  - `_find_synesis_files()`: Recursively discovers .syn, .synp, .synt, .syno files
  - `validate_workspace_file()`: Validates individual file
  - Returns map of URI → Diagnostics for all files
- **Command**: `synesis/validateWorkspace` triggers workspace-wide validation
- **Integration**: Command handler added to `server.py`
- **Tests**: 18 tests added (`test_workspace_diagnostics.py` - NEW FILE)
  - Tests for file discovery in subdirectories
  - Tests for validation error handling
  - Tests for empty/nonexistent workspaces
  - Tests for individual file validation

### Impact

- **Find All References**: IDE-standard feature now available for Synesis symbols
- **Quick Fixes**: Intelligent corrections reduce typos and speed up development
- **Workspace Validation**: Catch errors across entire project, not just open files
- **Developer Experience**: Synesis LSP now provides modern IDE features on par with mainstream languages

### Test Coverage

- **314 tests total** (261 from Phases 1+2 + 53 from Phase 3)
- **53 new tests** added across Phase 3 tasks (11 + 24 + 18)
- All tests passing ✅

### Files Added

- `synesis_lsp/references.py` - Find All References implementation
- `synesis_lsp/code_actions.py` - Code Actions (Quick Fixes)
- `synesis_lsp/workspace_diagnostics.py` - Workspace-wide validation
- `tests/test_references.py` - 11 tests
- `tests/test_code_actions.py` - 24 tests
- `tests/test_workspace_diagnostics.py` - 18 tests

### Files Modified

- `synesis_lsp/server.py` - Added 3 new feature handlers + 1 command
- `CHANGELOG.md` - Documented Phase 3 implementation

## [0.12.0] - 2026-02-02

### Added - Phase 2: Completeness Endpoints

**Task 2.1: synesis/getOntologyTopics**
- **New endpoint**: `synesis/getOntologyTopics` extracts hierarchical topic structure from `.syno` files
- **Hierarchical parsing**: Respects indentation to build tree of concepts with levels (0, 1, 2...)
- **Implementation**: New module `synesis_lsp/ontology_topics.py`
  - `get_ontology_topics()`: Main function extracting topics from cached LinkedProject
  - `_parse_syno_file()`: Parses individual `.syno` files respecting indentation
  - Supports both space-based (4 spaces = 1 level) and tab-based indentation
  - Returns topics with: name, level, file (relative), line, children (recursive)
- **Integration**: Command handler added to `server.py`
- **Tests**: 13 new tests added (`test_ontology_topics.py` - NEW FILE)
  - Tests for empty ontology, hierarchical parsing, deep nesting, multiple roots
  - Tests for tab indentation, empty lines, relative paths, error handling

**Task 2.2: synesis/getOntologyAnnotations**
- **New endpoint**: `synesis/getOntologyAnnotations` cross-references ontology concepts with annotations
- **Implementation**: New module `synesis_lsp/ontology_annotations.py`
  - `get_ontology_annotations()`: Returns all ontology concepts with their occurrences in `.syn` files
  - `_build_occurrences()`: Builds detailed occurrence list with exact positions
  - `_find_code_in_item()`: Searches for code in item fields (CODE, CHAIN, etc.)
  - Returns annotations with: code, ontologyDefined, ontologyFile, ontologyLine, occurrences
  - Occurrences include: file, itemName, line, column, context ("code"/"chain"), field
- **Active file filtering**: Optional `activeFile` parameter filters occurrences to specific file
- **Integration**: Command handler added to `server.py`
- **Tests**: 15 new tests added (`test_ontology_annotations.py` - NEW FILE)
  - Tests for empty ontology, multiple concepts, active file filtering
  - Tests for occurrence extraction from fields and chains
  - Tests for relative paths and error handling

**Task 2.3: synesis/getAbstract**
- **New endpoint**: `synesis/getAbstract` extracts ABSTRACT field from `.syn` files
- **Implementation**: New module `synesis_lsp/abstract_viewer.py`
  - `get_abstract()`: Main function supporting both LinkedProject extraction and direct file parsing
  - `_extract_from_linked_project()`: Fast path using cached compilation result
  - `_parse_abstract_from_file()`: Fallback parsing directly from file
  - Handles multiline ABSTRACT fields with indentation continuation
  - Returns: abstract (text), file (relative), line (start line of ABSTRACT field)
- **Flexible parsing**:
  - Case-insensitive field name recognition
  - Supports both same-line (`ABSTRACT: text`) and multiline formats
  - Handles empty lines within ABSTRACT
- **Integration**: Command handler added to `server.py`
- **Tests**: 19 new tests added (`test_abstract_viewer.py` - NEW FILE)
  - Tests for simple and multiline abstracts
  - Tests for case insensitivity, relative paths, missing abstract
  - Tests for LinkedProject extraction and direct file parsing

### Impact

- **Ontology Topics Explorer**: Now operates 100% via LSP (no regex fallback)
- **Ontology Annotations Explorer**: Now operates 100% via LSP with precise positioning
- **Abstract Viewer**: Now operates 100% via LSP (eliminates SynesisParser dependency)
- **VSCode Extension**: Eliminates all remaining regex-based local parsing
- **Data Quality**: All endpoints return relative paths and 1-based line numbers (LSP standard)

### Test Coverage

- **261 tests total** (43 from Phase 1 + 47 from Phase 2 + 171 existing)
- **47 new tests** added across Phase 2 tasks (13 + 15 + 19)
- All tests passing ✅

### Files Added

- `synesis_lsp/ontology_topics.py` - Topic hierarchy extraction
- `synesis_lsp/ontology_annotations.py` - Ontology-annotation cross-referencing
- `synesis_lsp/abstract_viewer.py` - ABSTRACT field extraction
- `tests/test_ontology_topics.py` - 13 tests
- `tests/test_ontology_annotations.py` - 15 tests
- `tests/test_abstract_viewer.py` - 19 tests

### Files Modified

- `synesis_lsp/server.py` - Added 3 new command handlers
- `CHANGELOG.md` - Documented Phase 2 implementation

## [0.11.0] - 2026-02-02

### Fixed - Phase 1: Critical LSP Fixes

**Task 1.3: getRelationGraph Bibref Filter**
- **Bibref extraction**: Enhanced `_item_bibref()` with additional fallback strategies
  - Now checks: `bibref`, `source_bibref`, `bibref_id`, `ref`, `source.bibref`, `parent.bibref`
  - Fixes empty graph results when items lack direct bibref attributes
- **Code extraction**: Added `_iter_codes_from_item_all()` without ontology filter
  - Fallback now extracts ALL codes from sources, not just ontology-defined codes
  - Fixes missing codes in bibref-filtered graphs
- **Debugging**: Added comprehensive logging to `get_relation_graph()`
  - Logs bibref filtering steps, code counts, and triple filtering
- **Tests**: 4 new tests added (`test_graph.py`)
  - `test_filter_by_bibref_with_source_reference`
  - `test_filter_by_bibref_without_at`
  - `test_filter_by_bibref_sources_fallback`
  - `test_filter_by_nonexistent_bibref`

**Task 1.2: getRelations Location and Type**
- **Type detection**: Enhanced `_extract_chain_type()` to distinguish "qualified" vs "simple"
  - Qualified: chains with explicit type attribute or "::" separator
  - Simple: plain triples without type prefix
  - Added `_chain_to_string()` helper for format-based detection
- **Location extraction**: Improved `_index_chain()` with priority-based location lookup
  - Priority: `tuple[3]` → `chain.location` → `dict["location"]` → `item.location`
  - Ensures all relations have location and type fields
- **Tests**: 5 new tests added (`test_explorer_requests.py`)
  - `test_get_relations_qualified_type`
  - `test_get_relations_simple_type`
  - `test_get_relations_location_from_tuple`
  - `test_get_relations_dict_location`
  - `test_get_relations_fallback_to_item_location`

**Task 1.4: Template Diagnostics Logging**
- **Enhanced logging**: Added detailed logging to `validate_document()`
  - Template discovery steps logged (cache → auto-discovery)
  - Template diagnostics generation logged with counts
  - Publishing success/failure logged with error details
- **Debug command**: Added `synesis/debug/diagnostics` command
  - Returns diagnostic system status
  - Shows cache availability, template availability, and field specs
  - Useful for troubleshooting validation issues
- **Tests**: 5 new tests added (`test_server_diagnostics.py` - NEW FILE)
  - `test_validate_document_publishes`
  - `test_validate_document_template_integration`
  - `test_validate_document_disabled`
  - `test_debug_diagnostics_command`
  - `test_debug_diagnostics_no_cache`

**Task 1.1: getCodes Exact Occurrences**
- **Exact positioning**: Added field-level and token-level position tracking
  - New `_find_code_in_field_value()`: finds exact token positions within field values
  - New `_extract_field_location()`: extracts field start line/column
  - New `_stringify_value()`: converts field values to searchable strings
- **Enhanced `_build_code_occurrences()`**:
  - Now calculates exact line/column for each code within field values
  - Handles multiline field values (splits by '\n', tracks line offsets)
  - Extracts chain.location when available (not just item.location)
  - Graceful fallback to item.location when field location unavailable
- **Tests**: 4 new tests added (`test_explorer_requests.py`)
  - `test_get_codes_exact_positions`
  - `test_get_codes_multiline_field`
  - `test_get_codes_fallback_to_item_location`
  - `test_get_codes_with_chain_location`

### Impact

- **Graph Viewer**: Now works correctly with bibref filter (no more empty graphs)
- **Relation Explorer**: All relations now have location and type fields
- **Code Explorer**: Codes now show exact positions, not just item-level positions
- **Diagnostics**: Template validation now visible with enhanced logging
- **Extension**: Reduced/eliminated fallback to regex parsing in VSCode extension

### Test Coverage

- **43 tests total** (18 graph + 20 explorer + 5 diagnostics)
- **18 new tests** added across Phase 1 tasks
- All tests passing ✅

## [0.10.4] - 2026-02-02

### Fixed

- **Project loading**: `synesis/loadProject` agora detecta `.synp` quando o
  `workspaceRoot` aponta para arquivo ou pasta.
- **Explorer codes**: `synesis/getCodes` inclui `occurrences` e faz fallback
  via `sources/items` quando `code_usage` não está disponível.
- **Relations**: `synesis/getRelations` agora inclui `location` e `type` com
  parsing mais robusto de CHAINs.
- **Relation graph**: filtro por `bibref` em `synesis/getRelationGraph` foi
  corrigido com normalização e fallback via `sources/items`.
- **Paths**: caminhos relativos normalizados para formato POSIX nas respostas.

## [0.10.3] - 2026-02-01

### Fixed

- **LSP features**: corrigida a resolucao do workspace cache para handlers de
  hover/definition/inlay/signature/rename em Windows quando o rootUri chega
  como `file:///` (fallback para `workspaceFolders`).

## [0.10.2a3] - 2026-02-01

### Changed

- **Empacotamento**: bump de versão para release de teste no TestPyPI.

## [0.10.2a1] - 2026-01-31

### Changed

- **Empacotamento**: bump de versão para release de teste no TestPyPI.

## [0.10.1] - 2026-01-31

### Fixed

- **Semantic Tokens**: legenda agora usa strings e instância fresca para evitar crash no initialize.

## [0.10.0] - 2026-01-30

### Added

- **Relation Graph** (`synesis_lsp/graph.py`) (Step 10a - P3)
  - `synesis/getRelationGraph` gera código Mermaid.js a partir de `all_triples`
  - Filtragem opcional por `bibref` (mostra apenas relações dos códigos usados)
  - Sanitização de IDs para compatibilidade com Mermaid.js
  - Deduplicação de triples no grafo

- **Signature Help** (`synesis_lsp/signature_help.py`) (Step 10b - P3)
  - `textDocument/signatureHelp` com trigger character `:`
  - Detecta padrão `campo:` e exibe definição do FieldSpec
  - Mostra tipo, escopo e descrição do campo do template
  - Inclui `ParameterInformation` com tipo esperado do valor

- **Rename** (`synesis_lsp/rename.py`) (Step 10c - P3)
  - `textDocument/rename` renomeia bibrefs e códigos em todo o workspace
  - `textDocument/prepareRename` verifica se símbolo é renomeável
  - Para bibrefs: busca `@bibref` em todos os arquivos .syn referenciados
  - Para códigos: busca em arquivos .syno (definição) e .syn (uso via code_usage)
  - Produz `WorkspaceEdit` com `TextEdit` por arquivo
  - Lê arquivos do disco para encontrar ocorrências textuais com word boundary

## [0.9.0] - 2026-01-30

### Changed

- **Integração error_handler** (`synesis_lsp/converters.py`) (Step 9 - P2)
  - `enrich_error_message(exc, source, filename)` usa `create_pedagogical_error` do compilador
  - Enriquece exceções Lark encapsuladas (__cause__) com contexto, sugestões e exemplos
  - `_humanize_expected(tokens)` converte nomes de tokens Lark para texto legível em português
  - `build_diagnostic` agora adiciona tokens esperados humanizados para SyntaxError
  - Fallback gracioso: se error_handler não disponível, usa mensagem original
  - `_validate_document` e `loadProject` agora usam mensagens enriquecidas em seus exception handlers

## [0.8.0] - 2026-01-30

### Added

- **Go-to-Definition** (`synesis_lsp/definition.py`) (Step 8 - P2)
  - `textDocument/definition` resolve @bibref → SourceNode.location e código → OntologyNode.location
  - Combina paths relativos do compilador com workspace_root para URI completo
  - Conversão automática de posições 1-based (compilador) para 0-based (LSP)
  - Reutiliza `_get_word_at_position` do hover.py

- **Autocomplete** (`synesis_lsp/completion.py`) (Step 8 - P2)
  - `textDocument/completion` com trigger character "@"
  - Bibrefs após @: label=@bibref, detail=autor (ano), insert_text sem @
  - Códigos da ontologia: label=conceito, detail com contagem de usos
  - Campos do template: label=nome:, detail=tipo (escopo), documentation=descrição
  - Degradação graciosa: retorna lista vazia se cache vazio

## [0.7.0] - 2026-01-30

### Added

- **Inlay Hints** (`synesis_lsp/inlay_hints.py`) (Step 7 - P2)
  - `textDocument/inlayHint` exibe (Autor, Ano) inline após cada @bibref
  - Usa regex para localizar @bibrefs e busca na bibliography do CompilationResult em cache
  - Suporte a range filtering para limitar hints à área visível do editor
  - Formatação: sobrenome do primeiro autor + ano (ex: "Silva, 2023")
  - Degradação graciosa: retorna [] se cache vazio ou bibliography ausente

## [0.6.0] - 2026-01-30

### Added

- **Explorer Requests** (`synesis_lsp/explorer_requests.py`) (Step 6 - P1)
  - `synesis/getReferences` → lista de SOURCEs com bibref, itemCount, fields, location
  - `synesis/getCodes` → lista de codigos com usageCount e ontologyDefined
  - `synesis/getRelations` → lista de triples (from, relation, to)
  - Substitui parsers regex do Explorer com dados reais do compilador
  - Degradacao graciosa: retorna success=False se cache vazio

## [0.5.0] - 2026-01-30

### Added

- **Hover** (`synesis_lsp/hover.py`) (Step 5 - P1)
  - `textDocument/hover` com informacao contextual baseada no workspace_cache
  - @bibref → titulo, autor, ano, tipo (via bibliography do CompilationResult)
  - campo: → tipo, escopo, descricao (via template.field_specs)
  - codigo → conceito, descricao, campos, contagem de uso (via linked_project.ontology_index)
  - Degradacao graciosa: retorna None se cache vazio
  - Helper `_get_word_at_position` para extracao de palavra sob cursor
  - Helper `_is_field_name` para detecao de nomes de campo

## [0.4.0] - 2026-01-30

### Added

- **Document Symbols** (`synesis_lsp/symbols.py`) (Step 4 - P1)
  - Outline view via `textDocument/documentSymbol` usando `compile_string()`
  - SOURCE → Class com children ITEM → Method (hierarquia por bibref)
  - ONTOLOGY → Struct
  - PROJECT → Namespace (quando disponivel)
  - Fallback regex para arquivos com erros de sintaxe
  - Conversao automatica de posicoes 1-based (compilador) para 0-based (LSP)
  - Handler `textDocument/documentSymbol` registrado no servidor

## [0.3.0] - 2026-01-30

### Added

- **WorkspaceCache** (`synesis_lsp/cache.py`)
  - Cache de `CompilationResult` por workspace com `CachedCompilation` dataclass
  - Operacoes: `get`, `put`, `invalidate`, `has`
  - Invalidacao automatica em `didSave` e `didChangeWatchedFiles` para todos os tipos Synesis

- **Custom Request: `synesis/loadProject`** (Step 1 - P0)
  - Compila projeto completo via `SynesisCompiler` e armazena em cache
  - Retorna estatisticas do projeto (source_count, item_count, etc.)
  - Tratamento de `SynesisSyntaxError` com localizacao
  - Funcao helper `_resolve_workspace_root` para resolver workspace via params, documentos abertos ou workspace folders

- **Custom Request: `synesis/getProjectStats`** (Step 2 - P0)
  - Retorna estatisticas do projeto a partir do cache (sem recompilar)
  - Requer `synesis/loadProject` previo

- **Semantic Tokens** (`synesis_lsp/semantic_tokens.py`) (Step 3 - P1)
  - Colorizacao semantica via analise do texto-fonte linha a linha
  - Tokens: Keyword (SOURCE/ITEM/ONTOLOGY/END), Variable (@bibref), Property (campo:), String (valores entre aspas), EnumMember (codigos/valores simples), Namespace (PROJECT/TEMPLATE/INCLUDE)
  - Encoding delta LSP conforme especificacao
  - Handler `textDocument/semanticTokens/full` registrado no servidor

### Changed

- `did_save` agora invalida `workspace_cache` para `.synp`, `.synt`, `.bib`, `.syn`, `.syno`
- `did_change_watched_files` estendido para processar `.syn` e `.syno`

## [0.1.0] - 2026-01-03

### Added

- **LSP Server** (`synesis_lsp/`)
  - Servidor LSP com pygls para validacao em tempo real
  - Handlers: `didOpen`, `didChange`, `didClose`, `didSave`
  - Invalidacao automatica de cache ao salvar `.synp`, `.synt`, `.bib`
  - Monitoramento de arquivos de contexto via `workspace/didChangeWatchedFiles`
  - Configuracao `synesis.validation.enabled` para habilitar/desabilitar validacao
  - Tratamento robusto de excecoes (servidor nunca crasha)

- **Converters** (`synesis_lsp/converters.py`)
  - Conversao `SourceLocation` (1-based) para LSP `Range` (0-based)
  - Mapeamento `ErrorSeverity` para `DiagnosticSeverity`
  - Builder de `Diagnostic` com fallback para erros mal-formados

- **VSCode Extension** (`vscode-extension/`)
  - Cliente LSP em TypeScript com `vscode-languageclient`
  - Syntax highlighting via TextMate grammar (`.syn`, `.synp`, `.synt`, `.syno`)
  - Configuracao de Python path e trace level
  - Auto-indentacao e bracket matching
  - Empacotamento como `.vsix`

- **Compiler Adapter** (em `synesis/lsp_adapter.py` no compilador)
  - Funcao `validate_single_file()` para validacao in-memory
  - Descoberta automatica de contexto (`.synp`, `.synt`, `.bib`)
  - Cache de `ValidationContext` com validacao por mtime
  - 13 testes unitarios passando

### Architecture

- Decisao arquitetural documentada em ADR-002 (`docs/ADR-002.md`)
- LSP opera como Protocol Adapter puro (sem logica de validacao propria)
- Fonte unica de verdade: compilador Synesis
- Fluxo unidirecional: Editor -> LSP -> Compilador -> Diagnosticos
