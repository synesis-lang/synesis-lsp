# Changelog

All notable changes to the Synesis LSP project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [1.0.0] - 2026-01-30

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

## [1.0.3] - 2026-02-01

### Fixed

- **LSP features**: corrigida a resolucao do workspace cache para handlers de
  hover/definition/inlay/signature/rename em Windows quando o rootUri chega
  como `file:///` (fallback para `workspaceFolders`).

## [1.0.2a3] - 2026-02-01

### Changed

- **Empacotamento**: bump de versão para release de teste no TestPyPI.

## [1.0.2a1] - 2026-01-31

### Changed

- **Empacotamento**: bump de versão para release de teste no TestPyPI.

## [1.0.1] - 2026-01-31

### Fixed

- **Semantic Tokens**: legenda agora usa strings e instância fresca para evitar crash no initialize.

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

## [Unreleased]

### Planned

- Code actions (quick fixes)
- Workspace diagnostics (diagnosticProvider)
- Code lens (reference counts)
