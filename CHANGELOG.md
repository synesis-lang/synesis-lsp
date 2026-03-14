# Changelog

All notable changes to the Synesis LSP project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.14.23] - 2026-03-13

### Changed
- **Fase 0 — Consolidação de `_normalize_code`**: as 7 cópias locais de `_normalize_code`
  em `definition.py`, `explorer_requests.py`, `graph.py`, `hover.py`,
  `ontology_annotations.py`, `references.py` e `rename.py` foram removidas e substituídas
  por `from synesis.ast.normalize import normalize_code as _normalize_code`. Todos os
  call sites permanecem inalterados (alias drop-in). Elimina risco de divergência entre
  implementações e unifica com o compilador.

- **Fase 7 — Pre-filtro de Ontology Annotations por arquivo ativo**
  (`ontology_annotations.py`): quando `active_file` é fornecido, `_merge_code_usage_with_chains`
  agora aplica pre-filtro por source antes de iterar chains — sources de outros arquivos são
  descartados sem processar seus items. Nova função auxiliar `_source_file(src)` extrai o
  path do source node. Resultado filtrado não é armazenado no cache global (evita poluir
  cache com resultado parcial); se o cache completo do projeto já existe, aplica
  `_filter_annotations_by_file` sobre ele como atalho.

## [0.14.22] - 2026-03-13

### Changed
- **Cancelamento de validação em progresso** (Fase 6, padrão Pyright `_backgroundAnalysisCancellationSource`):
  - `SynesisLanguageServer.__init__` ganha `_validation_tasks: dict[str, asyncio.Task]`
  - Nova coroutine `_validate_document_async(ls, uri)`: faz `await asyncio.sleep(0)` antes
    de chamar `validate_document()` — checkpoint que permite cancelamento antes de compilar
    conteúdo já obsoleto; captura `CancelledError` e faz cleanup do dict em `finally`
  - Nova função `_schedule_validation(ls, uri)`: cancela a task anterior para o URI (se
    existir e não concluída) antes de criar nova via `asyncio.ensure_future()`
  - `_run_deferred_validation`: atualizado para chamar `_schedule_validation` em vez de
    `validate_document` diretamente — une debounce (Fase 1) + cancelamento (Fase 6)
  - `did_close`: cancela task em andamento além do timer de debounce

## [0.14.21] - 2026-03-13

### Changed
- **Revalidação deferida de documentos não-focados** (Fase 5, padrão Pyright `program.ts analyze()`):
  - Nova coroutine `_revalidate_workspace_deferred(ls, workspace_key, focused_uri)`: valida o
    documento focado imediatamente (síncrono), depois cede ao event loop via `await asyncio.sleep(0)`
    entre cada documento restante — servidor permanece responsivo para hover/completion durante
    revalidação de arquivos não focados
  - `did_save` (.synp/.synt e .bib) e `did_change_watched_files`: substituem loops síncronos
    bloqueantes por `asyncio.ensure_future(_revalidate_workspace_deferred(...))` — bloqueio
    passa de ~N×50ms para ~50ms (apenas arquivo focado)
  - `did_open` e `did_change`: atualizam `ls._last_focused_uri` para priorização correta
  - `SynesisLanguageServer.__init__` ganha `_last_focused_uri: Optional[str]`

## [0.14.20] - 2026-03-13

### Changed
- **Cache de providers** (Fase 4): resultados de `compute_document_symbols`,
  `compute_semantic_tokens` e `get_codes` agora são cacheados e retornados em 0ms
  quando o conteúdo não mudou entre requests.
  - `symbols.py`: `_SYMBOLS_CACHE: dict[(uri, hash), list]` — cache hit evita
    chamada a `compile_string()` (~3-69ms); limpo a cada novo resultado para manter
    apenas a entrada mais recente
  - `semantic_tokens.py`: `_TOKENS_CACHE: dict[(uri, hash), SemanticTokens]` — cache
    hit evita scan regex linha-a-linha; mesmo padrão de limpeza
  - `explorer_requests.py`: `_CODES_CACHE: dict[cache_key, dict]` — mesmo padrão de
    `_RELATIONS_CACHE` (key via `_relations_cache_key`, max 4 entradas); elimina
    iteração O(codes × items × fields) em requests repetidos (~99% para Explorer refresh
    sem mudanças)

## [0.14.19] - 2026-03-13

### Changed
- **Fingerprint leve com mtime-max** (Fase 3): `_compute_workspace_fingerprint()` substituiu
  SHA1 incremental + `stat()` por arquivo por verificação de `max(mtime)` + contagem de
  arquivos — elimina construção de string e hash criptográfico por arquivo. `import hashlib`
  removido. Semântica preservada: qualquer mudança em `.synp/.syn/.syno/.synt/.bib` altera
  o fingerprint e invalida o cache do workspace.

## [0.14.18] - 2026-03-13

### Changed
- **Dirty flags por documento — cache de validação** (Fase 2, padrão Pyright `WriteableData`):
  - `cache.py`: novo dataclass `FileState` com `content_hash`, `validated_content_hash`,
    `context_version` e `last_diagnostics`
  - `SynesisLanguageServer.__init__` ganha `_file_states: dict[str, FileState]` e
    `_context_versions: dict[str, int]`
  - `validate_document`: antes de compilar, verifica se `content_hash` e `context_version`
    não mudaram desde a última validação; se não mudaram, republica os diagnósticos cacheados
    sem chamar `validate_single_file` (0ms vs 3-69ms)
  - `did_save` e `did_change_watched_files`: fazem bump de `_context_versions[workspace_key]`
    ao invalidar caches, forçando revalidação de todos os docs do workspace
  - `did_close`: remove `FileState` do dict para evitar memory leak
  - **Ganho principal:** ao salvar `.syn` sem mudar `.synt`, os outros docs abertos no
    workspace não são recompilados (context_version não mudou + content não mudou)

## [0.14.17] - 2026-03-13

### Changed
- **Debounce de 300ms no `did_change`** (`server.py`): validação por keystroke substituída
  por timer de debounce — padrão Pyright `scheduleReanalysis`. Ao digitar 10 caracteres
  rapidamente, apenas 1 validação é disparada (~300ms após a última tecla), eliminando
  ~80% do CPU desperdiçado durante digitação ativa.
  - `SynesisLanguageServer.__init__` ganha `_pending_validations: dict[str, TimerHandle]`
    e `_validation_debounce_s: float = 0.3`
  - `did_change` cancela o timer anterior para o URI e agenda novo via `loop.call_later()`
  - `did_close` cancela timer pendente para evitar validação após fechar documento
  - `did_open` e `did_save` mantêm validação **imediata** (ação explícita do usuário)
  - Extrai helper `_run_deferred_validation(ls, uri)` como função de módulo (thread-safe)

## [0.14.16] - 2026-03-06

### Fixed
- **GUIDELINES reconhecido como comando válido em `.synt`**: `_allowed_commands()` em `template_diagnostics.py` agora inclui `"GUIDELINES"` e `"END GUIDELINES"` na lista de comandos válidos para arquivos de template
  - Bug: o LSP gerava falso warning `Comando invalido 'GUIDELINES'` ao abrir templates `.synt` com blocos `GUIDELINES...END GUIDELINES`
  - Causa: a lista `_allowed_commands("synt")` não havia sido atualizada quando o suporte a `GUIDELINES` foi adicionado ao compilador (`synesis 0.3.0`)

## [0.14.15] - 2026-02-28

### Fixed
- **Graph Viewer mostra apenas relações do SOURCE atual**: `_triples_for_bibref()` em `graph.py` agora prioriza extração direta dos chains dos ITEMs do SOURCE (escopo restrito), ao invés de filtrar `all_triples` do projeto inteiro por presença de código
  - Bug: `Ctrl+Alt+G` gerava grafo ilegível incluindo relações de outros SOURCEs que compartilhavam os mesmos códigos
  - Mecanismo: Stage 1 anterior coletava códigos do SOURCE e varria `all_triples` globais, trazendo triples de outras fontes
  - Solução: Stage 1 agora itera `source.items → item.chains` e extrai triples diretamente; filtro por `all_triples` ficou como fallback (Stage 2)
- Graph Viewer (`Ctrl+Alt+G`) agora exibe apenas as relações CHAIN definidas nos ITEMs do SOURCE onde o cursor está posicionado

## [0.14.14] - 2026-02-05

### Fixed
- **CODE occurrence duplication in OntologyAnnotationExplorer**: Adicionada função `_dedupe_occurrences()` em `ontology_annotations.py` para eliminar duplicatas
  - Bug: campos CODE apareciam duplicados (2x) no Ontology Annotations Explorer
  - Mecanismo: `_build_occurrences` não tinha deduplicação final, permitindo que a mesma occurrence fosse adicionada múltiplas vezes
  - Solução: Implementada mesma função `_dedupe_occurrences()` de `explorer_requests.py` (Phase 1 only - exact dedup)
  - Normalização de field names para lowercase evita duplicatas "CODE" vs "code"
- Ontology Annotations Explorer agora mostra cada occurrence CODE apenas 1x (comportamento idêntico ao Code Explorer)

### Architecture
- **Consistência**: `ontology_annotations.py` e `explorer_requests.py` agora usam mesma lógica de deduplicação
- **Fix at source**: Correção no LSP (server-side) ao invés de compensação no cliente
- **Exact-match only**: Apenas Phase 1 deduplication (file/line/column/context/field) sem proximity heuristics

## [0.14.13] - 2026-02-05

### Fixed
- **CHAIN last-occurrence-only bug**: Removida Phase 2 "semantic deduplication" de `_dedupe_occurrences()` que colapsava occurrences próximas (≤5 linhas)
  - Bug: quando um código (ex: CCS_Support) aparecia em múltiplas CHAINs consecutivas no mesmo ITEM, apenas a última occurrence era retornada
  - Mecanismo: Phase 2 agrupava por (file, field, context) e mantinha apenas linha mais alta, colapsando todas as 4 chains em uma só
  - Solução: Phase 1 (exact dedup por file/line/column/context/field) é suficiente - cenários de near-duplicate já prevenidos por: (1) item dedup por `id()`, (2) `found_any=True` defense, (3) linker's `existing_keys` check
- Code Explorer agora mostra TODAS as occurrences de códigos em campos CHAIN, não apenas a última

### Architecture
- **Lição aprendida**: Heurísticas baseadas em proximidade para deduplicação são perigosas - removem dados legítimos silenciosamente
- **Princípio**: Sempre preferir exact-match deduplication ao invés de proximity-based heuristics

## [0.14.12] - 2026-02-05

### Fixed
- **CODE occurrence duplication (root cause)**: `get_codes()` agora deduplica items por identidade de objeto (`id(item)`) após normalização de códigos, eliminando duplicação quando chaves diferentes (ex: "A201" e "a201") mapeiam para o mesmo ItemNode
- **Defensive fix in `_append_precise_occurrences`**: Marca `found_any=True` mesmo quando occurrence já existe em `seen`, prevenindo execução indevida do fallback que adiciona localização do bloco ITEM
- **Field name normalization**: `_dedupe_occurrences()` agora normaliza field names para lowercase em ambas as fases de deduplicação (exact + semantic), capturando duplicatas com diferença de case ("code" vs "CODE")
- Code Explorer e Ontology Annotations Explorer agora mostram apenas occurrences nas linhas exatas dos campos CODE/CHAIN, não no início do bloco ITEM

### Architecture
- Implementação de 3 camadas de defesa (defense in depth): (1) dedup items por `id()`, (2) `found_any` defensivo, (3) field name normalization
- Pattern de deduplicação por `id(item)` alinhado com `ontology_annotations.py:_add_item_to_usage` (já implementado)
- Remoção de banda-aid client-side (VSCode extension) que compensava incorretamente o problema na fonte

## [0.14.11] - 2026-02-05

### Fixed
- `_dedupe_occurrences()` agora usa deduplicação semântica para remover duplicatas com linhas próximas (≤5 linhas), mantendo a localização mais específica (linha maior = mais dentro do bloco)
- Code Explorer não mostra mais duplicatas de códigos CODE com linha do ITEM + linha do campo (ex: linha 115 ITEM + linha 117 CODE)
- Correção definitiva para problema de múltiplas fases de compilação (transformer + linker) gerando localizações ligeiramente diferentes do mesmo código

## [0.14.10] - 2026-02-04

### Fixed
- `_dedupe_occurrences()` agora inclui `column` na chave de deduplicação (correção definitiva para duplicatas CODE/CHAIN)
- Tree views do Explorer não mostram mais ocorrências duplicadas (localização ITEM + CODE)
- Correção complementar ao synesis v0.2.9 para garantir deduplicação em camada LSP

## [0.14.9] - 2026-02-04

### Fixed
- Minor fixes

## [0.14.8] - 2026-02-04

### Fixed
- `synesis/getCodes` agora respeita campos CODE/CHAIN definidos no template ao calcular ocorrências e contagens.
- Hover agora exibe ajuda para campos em SOURCE/ITEM/ONTOLOGY e resume blocos conforme o template.
- `synesis/getCodes` remove duplicatas de ocorrências e mantém a localização mais precisa por linha.
- `synesis/getRelationGraph` voltou a filtrar por bibref usando `code_usage` com fallback por fontes.
- `synesis/getOntologyTopics` agora aceita hierarquias simples sem bloco `ONTOLOGY`.
- Rename de códigos em `.syn` passa a funcionar mesmo sem template carregado (fallback).

### Changed
- Completion passa a disparar também em `:` e `>` e sugere ontologia automaticamente.

### Planned
- Centralizar lista de comandos/keywords no compilador/gramatica e expor ao LSP, evitando duplicacao em `template_diagnostics.py`.

## [0.14.7] - 2026-02-04

### Fixed
- `synesis/getCodes` gerando campos duplicados (correção complementar)
- `_dedupe_occurrences()` agora inclui `column` na chave de deduplicação para remover duplicatas exatas
- Tree views do Explorer agora mostram apenas 1 ocorrência por CODE/CHAIN (não mais localização ITEM + localização CODE) 

## [0.14.6] - 2026-02-04

### Fixed
- `synesis/getCodes` e `synesis/getOntologyAnnotations` agora alinham `code_locations` com o campo real do template quando a chave vem como `code`/`codes`, garantindo linha/coluna exatas para campos CODE com nomes customizados.

## [0.14.5] - 2026-02-04

### Fixed
- `synesis/getCodes` agora utiliza localizações precisas de CODE/CHAIN mesmo quando o template não reconhece o nome do campo, reduzindo fallback por item.

## [0.14.4] - 2026-02-04

### Changed
- `synesis/getCodes` agora usa localizações exatas fornecidas pelo compilador para CODE/CHAIN (inclui multiline), evitando fallback regex.

### Fixed
- Ontology annotations agora retornam posições exatas de CODE/CHAIN usando `code_locations` e `node_locations` do compilador.

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
