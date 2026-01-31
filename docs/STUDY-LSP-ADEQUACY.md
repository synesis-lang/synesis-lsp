# Estudo de Adequacao: LSP Server + Synesis-Explorer

**Data:** 2026-01-29
**Escopo:** Analise do compilador Synesis (Compiler/), da extensao Synesis-Explorer, e do servidor LSP (LSP/) para identificar lacunas, oportunidades de integracao e plano de evolucao.

---

## 1. Estado Atual dos Tres Componentes

### 1.1 Compilador Synesis (`Compiler/synesis/`)

| Modulo | Linhas | Status | Usado pelo LSP? |
|--------|--------|--------|------------------|
| `compiler.py` | 258 | Completo | NAO |
| `lsp_adapter.py` | 663 | Completo | SIM |
| `cli.py` | 255 | Completo | NAO |
| `ast/nodes.py` | 284 | Completo | SIM (via adapter) |
| `ast/results.py` | 514 | Completo | SIM (via adapter) |
| `semantic/validator.py` | 696 | Completo | SIM (via adapter) |
| `semantic/linker.py` | 254 | Completo | NAO |
| `parser/lexer.py` | 125 | Completo | SIM (via adapter) |
| `parser/transformer.py` | ~100 | Completo | SIM (via adapter) |
| `parser/template_loader.py` | ~80 | Completo | SIM (via adapter) |
| `parser/bib_loader.py` | 84 | Completo | SIM (via adapter) |
| `error_handler.py` | 574 | Completo | NAO |
| `exporters/` | ~1500 | Completo | NAO |

**API em memoria (`synesis.load`) - IMPLEMENTADA (v0.2.0, 2026-01-21):**

O compilador v0.2.0 implementa a API in-memory especificada em `synesis_load.qmd`:

```python
# Via 1 - Compilacao baseada em disco (existente desde v0.1.0)
compiler = SynesisCompiler(Path("projeto.synp"))
result = compiler.compile()  # -> CompilationResult

# Via 2 - Compilacao in-memory (NOVO v0.2.0)
import synesis
result = synesis.load(
    project_content=str,          # conteudo .synp
    template_content=str,         # conteudo .synt
    annotation_contents=dict,     # {filename: conteudo .syn}
    ontology_contents=dict,       # {filename: conteudo .syno}
    bibliography_content=str,     # conteudo .bib
) # -> MemoryCompilationResult

# Via 3 - Parsing de fragmento (NOVO v0.2.0)
tree = synesis.compile_string(content, filename)
```

`MemoryCompilationResult` (v0.2.0) estende `CompilationResult` com:
- `to_json_dict()` -> dict Python (sem I/O)
- `to_csv_tables()` -> {table_name: (headers, rows)}
- `to_dataframe(table)` -> pandas.DataFrame
- `to_dataframes()` -> {table_name: DataFrame}
- `get_diagnostics()` -> str formatado

`CompilationResult` (v0.1.0, existente) contem:
- `linked_project: LinkedProject` (grafo semantico completo)
- `validation_result: ValidationResult` (erros/warnings/info)
- `stats: CompilationStats` (contagens)
- `template`, `bibliography` (contexto)

Funcionalidades adicionais implementadas em v0.2.0:
- `load_template_from_string()` em template_loader.py
- `load_bibliography_from_string()` em bib_loader.py
- `build_json_payload()` em json_export.py (construcao JSON in-memory)
- `build_csv_tables()` em csv_export.py (construcao de tabelas in-memory)
- `build_xls_workbook()` em xls_export.py (construcao Workbook in-memory)

### 1.2 Servidor LSP (`LSP/synesis_lsp/`)

| Modulo | Linhas | Status |
|--------|--------|--------|
| `server.py` | 451 | Completo |
| `converters.py` | 161 | Completo |
| `__main__.py` | 11 | Completo |

**Capacidades atuais:**
- Validacao sintatica e semantica em tempo real (via `validate_single_file`)
- Descoberta automatica de contexto (.synp/.synt/.bib)
- Cache com invalidacao por mtime
- Handlers: didOpen, didChange, didClose, didSave, didChangeConfiguration, didChangeWatchedFiles
- Revalidacao automatica ao salvar .synp/.synt/.bib

**Limitacoes atuais:**
- Apenas publica Diagnostics (erros/warnings)
- Nao oferece: completion, hover, goto definition, document symbols, code actions
- Nao usa Linker (nao tem visao cross-file)
- Nao usa error_handler.py (mensagens pedagogicas avancadas)
- Nao expoe CompilationResult/LinkedProject

### 1.3 Synesis-Explorer (`Synesis-Explorer/`)

| Componente | Arquivos | Status |
|------------|----------|--------|
| Parsers (regex) | 5 | synesisParser, templateParser, ontologyParser, chainParser, bibtexParser |
| Tree Views | 5 | Reference, Code, Relation, Ontology, OntologyAnnotation |
| Webview Panels | 2 | GraphViewer (Mermaid), AbstractViewer |
| Core Services | 4 | templateManager, workspaceScanner, fieldRegistry, projectLoader |
| Utilities | 2 | positionUtils, fuzzyMatcher |

**Capacidades atuais:**
- 5 tree views para navegacao (referencias, codigos, relacoes, ontologia, anotacoes)
- Visualizacao de grafos de relacoes (Mermaid.js)
- Exibicao de abstracts com excerpts destacados
- Syntax highlighting (TextMate grammar)
- File icons e temas (Dark/Light)
- 12 comandos + 2 atalhos de teclado

**Limitacao critica:** Usa parsers regex proprios (JavaScript), duplicando logica do compilador Python. Nao usa LSP.

---

## 2. Analise de Lacunas e Oportunidades

### 2.1 Funcionalidades do Compilador NAO expostas pelo LSP

| Funcionalidade | Modulo | Impacto para o Editor |
|----------------|--------|----------------------|
| **Compilacao completa em memoria** | `compiler.py` | Permitiria ao Explorer usar dados do compilador em vez de parsers regex |
| **LinkedProject** | `linker.py` | Grafos de relacoes, code_usage, hierarchy, topic_index, all_triples |
| **CompilationStats** | `compiler.py` | Contagens de sources, items, codes, chains, triples |
| **Error Handler pedagogico** | `error_handler.py` | Mensagens de erro mais ricas com contexto e sugestoes |
| **Exportacao** | `exporters/` | JSON/CSV/XLS direto do editor |

### 2.2 Funcionalidades do Synesis-Explorer que o LSP deveria fornecer

| Feature Explorer | Implementacao Atual | Como o LSP deveria fornecer |
|-----------------|---------------------|---------------------------|
| Reference tree (SOURCE @bibref) | Regex parsing em JS | `textDocument/documentSymbol` |
| Code tree (codigos extraidos) | Regex parsing em JS | Custom request ou `workspace/symbol` |
| Relation tree (triplets) | chainParser.js regex | Custom request com LinkedProject |
| Ontology topics | ontologyParser.js regex | Custom request com LinkedProject |
| Graph viewer (Mermaid) | chainParser.js + template | Custom request: `synesis/getRelationGraph` |
| Abstract viewer | bibtexParser.js | Custom request: `synesis/getAbstract` |
| Fuzzy matching bibrefs | fuzzyMatcher.js | Ja existe no compilador (bib_loader) |
| Go to definition | NAO implementado | `textDocument/definition` |
| Hover information | NAO implementado | `textDocument/hover` |
| Autocomplete | NAO implementado | `textDocument/completion` |

### 2.3 Duplicacao de Logica (Explorer vs Compilador)

| Logica | Explorer (JS/regex) | Compilador (Python/Lark) |
|--------|---------------------|--------------------------|
| Parse SOURCE/ITEM | synesisParser.js | parser/lexer.py + transformer.py |
| Parse FIELD/TEMPLATE | templateParser.js | parser/template_loader.py |
| Parse ONTOLOGY | ontologyParser.js | parser/transformer.py |
| Parse CHAIN | chainParser.js | ChainNode em nodes.py |
| Parse BibTeX | bibtexParser.js (bibtex-parse-js) | parser/bib_loader.py (bibtexparser) |
| Parse PROJECT | projectLoader.js | compiler.py + lsp_adapter.py |
| Fuzzy match | fuzzyMatcher.js | bib_loader.py |

**7 duplicacoes** que poderiam ser eliminadas se o Explorer consumisse dados do LSP.

---

## APENDICE A: Validacao Empirica da API v0.2.0

Testes realizados em 2026-01-30 com o projeto Davi (61 sources, 10.063 items, 291 ontologias).
Compilador v0.2.1 instalado na maquina.

### A.1 Performance Medida

| Operacao | Tempo Medio | Observacao |
|----------|-------------|------------|
| `SynesisCompiler.compile()` (disco) | **3.68s** | Projeto completo via arquivo |
| `synesis.load()` (in-memory) | **3.28s** | Projeto completo via strings |
| `to_json_dict()` | **259ms** | Serializacao do resultado (21.7 MB JSON) |
| `compile_string()` (arquivo grande, 244KB) | **69ms** | entrevista01.syn: 224 nodes |
| `compile_string()` (fragmento pequeno) | **3ms** | 2 nodes (1 SOURCE + 1 ITEM) |

**Implicacoes para o LSP:**
- `synesis.load()` e `SynesisCompiler.compile()` sao custosos (~3s). **Nao chamar em didChange** (a cada tecla). Usar em didSave ou com debounce longo (2-5s).
- `compile_string()` e rapido o suficiente para uso em hover/completion (~3ms para fragmentos).
- `to_json_dict()` demora 259ms. Para custom requests frequentes, servir diretamente do `LinkedProject` em vez de serializar para JSON completo.

### A.2 Estrutura Real do `to_json_dict()`

```
to_json_dict() -> Dict
├── version: "2.0"
├── export_metadata: {timestamp, compiler_version, export_mode, chain_count, item_count, ...}
├── project: {name, template_path, includes, metadata, description}
├── template: {name, metadata, field_specs, required_fields, optional_fields, ...}
├── bibliography: {bibref_id: {year, author, title, ENTRYTYPE, ID, ...}, ...}
├── indices
│   ├── hierarchy: Dict (vazio no projeto Davi)
│   ├── triples: List (vazio no projeto Davi)
│   ├── topics: Dict[field_name -> List[codes]] (75 topicos)
│   └── code_frequency: Dict[code -> count] (281 codigos)
├── ontology: Dict[concept -> {concept, description, fields, parent_chains, location, frequency, source_count}]
└── corpus: List[10063 items]
    └── cada item: {id, source_ref, source_metadata, data: {campo: valor, ...}}
```

**Observacao:** O JSON completo tem 21.7 MB. Para o LSP, e mais eficiente acessar `result.linked_project` diretamente e serializar apenas o subconjunto necessario para cada custom request.

### A.3 Estrutura Real do LinkedProject (Testada)

```python
LinkedProject
├── sources: Dict[str, SourceNode]          # 61 entries, key = bibref sem @
│   └── SourceNode
│       ├── bibref: str                     # "@entrevista01"
│       ├── fields: Dict[str, str]          # {"codigo": "N/A"}
│       ├── items: List[ItemNode]           # 223 items
│       ├── location: SourceLocation        # file, line, column
│       └── to_dict() -> dict
│
├── ontology_index: Dict[str, OntologyNode] # 291 entries, key = concept
│   └── OntologyNode
│       ├── concept: str                    # "dons_do_espirito"
│       ├── description: str
│       ├── fields: Dict[str, str]          # {"descricao": "...", "ordem_3a": "..."}
│       ├── field_names: List[str]
│       ├── parent_chains: List
│       ├── location: SourceLocation
│       └── to_dict() -> dict
│
├── code_usage: Dict[str, List[ItemNode]]   # 281 entries, key = code
│                                           # "proposito" -> 321 items
│
├── hierarchy: Dict[str, str]               # Vazio neste projeto
├── all_triples: List[Tuple[str,str,str]]   # Vazio neste projeto
│
├── topic_index: Dict[str, List[str]]       # 75 topicos
│                                           # "acao_do_espirito_e_sobrenaturalidade" -> ["dons_do_espirito", ...]
│
└── project: ProjectNode
    ├── name: str                           # "gestao_fe"
    ├── template_path: str                  # "Davi.synt"
    ├── includes: List[IncludeNode]         # BIBLIOGRAPHY, ANNOTATIONS, ONTOLOGY
    ├── metadata: Dict[str, str]            # {"version", "author", "dataset"}
    └── description: str
```

### A.4 ItemNode (Testado)

```python
ItemNode
├── bibref: str                 # "@entrevista01"
├── location: SourceLocation    # file:line:column
├── quote: str                  # Citacao textual (pode ser vazio)
├── codes: List[str]            # Codigos atribuidos
├── notes: List[str]            # Notas
├── chains: List[ChainNode]     # Cadeias de relacoes
├── field_names: List[str]      # Nomes de campos na ordem original
├── extra_fields: Dict          # Campos adicionais {nome: valor | [valores]}
│                               # Campos repetidos (bundle) -> lista automatica
└── note_chain_pairs: List      # Pares nota-cadeia
```

**Destaque:** `extra_fields` normaliza campos repetidos em listas automaticamente.
Ex: `ordem_2a` aparece 6x no mesmo ITEM -> `extra_fields["ordem_2a"] = ["proposito", "chamado_vocacao", ...]`

### A.5 TemplateNode e FieldSpec (Testados)

```python
TemplateNode
├── name: str                   # "gestao_fe"
├── field_specs: Dict[str, FieldSpec]  # Todos os campos definidos
├── required_fields: Dict[Scope, List[str]]
├── optional_fields: Dict[Scope, List[str]]
├── forbidden_fields: Dict[Scope, List[str]]
├── bundled_fields: Dict[Scope, List[Tuple[str,str]]]
│                               # ITEM: [("ordem_2a", "justificativa_interna")]
├── metadata: Dict
└── location: SourceLocation

FieldSpec
├── name: str                   # "ordem_1a"
├── type: FieldType             # FieldType.MEMO, TEXT, ENUMERATED, ORDERED, SCALE
├── scope: Scope                # Scope.SOURCE, ITEM, ONTOLOGY
├── description: str            # "Codificacao de 1a ordem (descritiva)"
├── format: str | None
├── values: List | None         # Para ENUMERATED
├── relations: List | None      # Para CHAIN
├── arity: int | None           # Para CHAIN
└── location: SourceLocation
```

### A.6 ValidationError - Atributos Especificos por Tipo (Testados)

| Tipo | Atributos Extras | Exemplo |
|------|------------------|---------|
| `UnregisteredSource` | `bibref`, `suggestions` | bibref="ref01", suggestions=[] |
| `UnknownFieldName` | `field_name`, `block_type` | field_name="codigo", block_type="SOURCE" |
| `MissingRequiredField` | `field_name`, `block_type` | field_name="codigo", block_type="SOURCE" |
| `MissingBundleField` | `bundle_fields`, `present_fields` | bundle_fields=("ordem_2a","justificativa_interna") |
| `UndefinedCode` | `code`, `context` | code="proposito", context="ITEM" |
| `SourceWithoutItems` | `bibref` | bibref="ref_inexistente" |

Todos os tipos possuem: `location: SourceLocation` (file, line, column) e `severity: ErrorSeverity`.

### A.7 SynesisSyntaxError (Testado)

```python
SynesisSyntaxError  # Lancada por compile_string() e synesis.load()
├── message: str              # Mensagem formatada com contexto
├── location: SourceLocation  # file, line, column
├── expected: List[str]       # Tokens esperados ["NEWLINE", "COLON", ...]
```

**Nota para o LSP:** `synesis.load()` lanca `SynesisSyntaxError` para erros sintaticos (interrompe compilacao). Erros semanticos ficam em `result.validation_result`. O LSP deve fazer `try/except` ao chamar `load()` e converter `SynesisSyntaxError` em `Diagnostic` usando `e.location` e `e.message`.

### A.8 Bibliografia (Testada)

Entradas bibliograficas sao **dicts Python** (nao dataclasses):
```python
bibliography["entrevista01"] = {
    "year": "2025",
    "author": "Entrevistado anonimo",
    "title": "Entrevista sobre gestao baseada em fe",
    "ENTRYTYPE": "misc",
    "ID": "entrevista01",
    "_original_key": "entrevista01"
}
```

**Implicacao para hover:** Para `textDocument/hover` sobre `@bibref`, basta acessar `result.bibliography[bibref]` e formatar os campos `author`, `year`, `title`.

### A.9 validate_single_file (LSP Adapter Atual)

```python
validate_single_file(source: str, file_uri: str, context: Optional[ValidationContext] = None) -> ValidationResult
```

**Nota:** A assinatura recebe `source` (conteudo do arquivo) e `file_uri`. Diferente de `synesis.load()`, retorna apenas `ValidationResult` (sem `LinkedProject`). Para features avancadas (hover, goto, completion), o LSP precisara de `LinkedProject` via `synesis.load()` ou `SynesisCompiler.compile()`.

### A.10 to_csv_tables() (Testado)

```python
tables = result.to_csv_tables()
# -> Dict[str, Tuple[List[str], List[Dict]]]
# tables["sources"]    -> (6 colunas, 61 linhas)
# tables["items"]      -> (7 colunas, 30157 linhas)  # Expandido: cada bundle vira 1 linha
# tables["ontologies"] -> (8 colunas, 291 linhas)
```

**Nota:** `items` no CSV tem 30.157 linhas (vs 10.063 no LinkedProject) porque cada par do bundle (ordem_2a, justificativa_interna) vira uma linha separada. Util para exportacao mas nao para o LSP.

---

## 3. API `synesis.load` e Impacto no LSP

### 3.1 Situacao: API implementada no compilador v0.2.0

A API `synesis.load()` foi implementada no compilador v0.2.0 (2026-01-21), conforme spec `synesis_load.qmd`. Esta API e a **peca central** que conecta o compilador ao LSP e ao Explorer. O bloqueio P0 no compilador esta resolvido; o proximo passo e consumir esta API no LSP server.

**O que a API implementada oferece ao LSP:**

| Funcionalidade spec | Uso no LSP |
|---------------------|------------|
| `synesis.load()` -> `MemoryCompilationResult` | Compilacao completa do workspace, servida via custom requests |
| `result.linked_project` -> `LinkedProject` | Dados para Explorer (references, codes, relations, ontology) |
| `result.to_json_dict()` | Serializacao para custom requests (elimina problema da secao 6.2) |
| `result.stats` -> `CompilationStats` | `synesis/getProjectStats` request |
| `result.get_diagnostics()` | Diagnosticos formatados com contexto |
| `synesis.compile_string()` | Parsing rapido de fragmentos para hover/completion |

### 3.2 Duas vias de uso pelo LSP

**Via 1 - Compilacao baseada em disco (workspace):**
O LSP ja conhece o caminho do `.synp` via `_find_workspace_root()`. Pode usar:
```python
compiler = SynesisCompiler(Path(synp_path))
result = compiler.compile()  # CompilationResult com LinkedProject
```
Adequado para: custom requests do Explorer (dados do projeto completo).

**Via 2 - Compilacao in-memory (v0.2.0, DISPONIVEL):**
`synesis.load()` permite compilar sem I/O:
```python
result = synesis.load(
    project_content=doc.source,   # texto do editor
    template_content=template_str,
    annotation_contents={"file.syn": source_str},
    bibliography_content=bib_str,
)
```
Adequado para: validacao em tempo real com texto nao-salvo (dirty buffers).

**Impacto no LSP:** A Via 2 resolve uma limitacao atual: o `validate_single_file` valida apenas o arquivo do editor, mas usa contexto de disco. Com `synesis.load()`, o LSP poderia compilar o projeto inteiro usando o texto nao-salvo dos buffers abertos, dando diagnostics cross-file em tempo real.

### 3.3 Dados disponibilizados pelo LinkedProject

```
LinkedProject
├── sources: Dict[str, SourceNode]         -> Reference Explorer
├── ontology_index: Dict[str, OntologyNode] -> Ontology Explorer
├── code_usage: Dict[str, List[ItemNode]]  -> Code Explorer
├── hierarchy: Dict[str, str]              -> Ontology hierarchy
├── all_triples: List[Tuple[str,str,str]]  -> Relation Explorer + Graph
├── topic_index: Dict[str, List[str]]      -> Ontology Topics
└── project: ProjectNode                   -> Project metadata
```

---

## 4. Plano de Evolucao do LSP Server

### Fase 1: Compilacao em Memoria (Fundacao)

**Objetivo:** Expor compilacao do projeto via LSP para que o Explorer consuma dados compilados em vez de parsers regex.

**Compilador: PRONTO (v0.2.0, 2026-01-21)**
- `synesis.load()` implementado em `synesis/__init__.py`
- `MemoryCompilationResult` com `to_json_dict()`, `to_csv_tables()`, `to_dataframe()`, etc.
- `synesis.compile_string()` para parsing de fragmentos
- `load_template_from_string()` e `load_bibliography_from_string()` para carga in-memory
- `build_json_payload()`, `build_csv_tables()`, `build_xls_workbook()` para exportacao in-memory

**Mudancas no LSP server (PROXIMO PASSO):**
1. Adicionar cache de `CompilationResult` por workspace (via `SynesisCompiler.compile()`)
2. Criar custom requests:
   - `synesis/loadProject` -> `result.to_json_dict()` (serializacao ja resolvida pela spec)
   - `synesis/getProjectStats` -> CompilationStats
3. Invalidar cache quando .synp/.synt/.bib/.syn/.syno mudam
4. Futuramente usar `synesis.load()` para compilar com dirty buffers

**Mudancas no Explorer:**
1. Substituir parsers regex por chamadas LSP custom requests
2. Manter parsers regex como fallback (quando LSP nao esta disponivel)

**Nota:** A spec v0.2.0 resolve a decisao 6.2 (serializacao): `to_json_dict()` ja produz dicts Python prontos para JSON-RPC.

### Fase 2: Document Symbols + Workspace Symbols

**Objetivo:** Permitir navegacao estrutural nos editores.

**LSP features:**
- `textDocument/documentSymbol` -> SOURCE, ITEM, ONTOLOGY blocks com hierarquia
- `workspace/symbol` -> Busca por bibref, codigo, conceito no workspace

**Dados necessarios:** Ja disponiveis no AST (SourceNode, ItemNode, OntologyNode com SourceLocation)

### Fase 3: Hover + Go to Definition

**Objetivo:** Informacoes contextuais ao passar o mouse e navegacao semantica.

**LSP features:**
- `textDocument/hover`:
  - Sobre `@bibref` -> titulo, ano, autores da bibliografia
  - Sobre codigo -> definicao da ontologia + contagem de uso
  - Sobre campo -> tipo, escopo, restricoes do template
  - Sobre relacao em chain -> descricao da relacao

- `textDocument/definition`:
  - `@bibref` -> SOURCE block onde e definido
  - Codigo -> ONTOLOGY block correspondente
  - Campo -> FIELD definition no template

**Dados necessarios:** LinkedProject (code_usage, ontology_index, bibliography)

### Fase 4: Autocomplete

**Objetivo:** Sugestoes inteligentes durante digitacao.

**LSP features:**
- `textDocument/completion`:
  - Apos `@` -> bibrefs da bibliografia
  - Em campo CODE -> codigos definidos na ontologia
  - Em campo CHAIN -> codigos + relacoes do template
  - Nomes de campos -> campos do template para o scope atual
  - Palavras-chave -> SOURCE, ITEM, ONTOLOGY, END, etc.

**Dados necessarios:** template (field_specs), bibliography, ontology_index

### Fase 5: Code Actions + Diagnostics Avancados

**Objetivo:** Correcoes automaticas e mensagens pedagogicas avancadas.

**LSP features:**
- `textDocument/codeAction`:
  - Bibref nao encontrado -> "Voce quis dizer @xxx?" (fuzzy match)
  - Campo desconhecido -> "Campos disponiveis: ..." (template)
  - Codigo indefinido -> "Definir ontologia para este codigo?"

- Integrar `error_handler.py` para mensagens pedagogicas com contexto

**Dados necessarios:** error_handler.py + fuzzy matching do bib_loader

### Fase 6: Custom Requests para Explorer

**Objetivo:** Eliminar parsers regex do Explorer, usando dados do compilador.

**Custom LSP requests:**

```
synesis/getReferences
  -> Lista de {bibref, itemCount, occurrences: [{file, line, col}]}

synesis/getCodes
  -> Lista de {code, occurrences: [{file, line, col, fieldName, context}]}

synesis/getRelations
  -> Lista de {from, relation, to, file, line, col}

synesis/getRelationGraph
  -> {bibref, mermaidCode: string} (para o GraphViewer)

synesis/getOntologyTopics
  -> Lista de {field, values: [{value, index, concepts: [{name, file, line}]}]}

synesis/getAbstract
  -> {bibref, abstract, excerpts: [{text, start, end, color}]}

synesis/getProjectStats
  -> {sources, items, codes, chains, triples, ontologies}
```

---

## 5. Impacto na Extensao Synesis-Explorer

### 5.1 Arquitetura Atual (sem LSP)

```
Synesis-Explorer (JS)
├── parsers/ (5 regex parsers)     <- DUPLICACAO
├── core/ (template, workspace)    <- DUPLICACAO PARCIAL
├── explorers/ (5 tree views)      <- UI (manter)
└── viewers/ (2 webviews)          <- UI (manter)
```

### 5.2 Arquitetura Proposta (com LSP)

```
Synesis-Explorer (JS)
├── lsp-client/                    <- NOVO: cliente LSP
│   ├── client.ts                  <- Conexao com synesis-lsp
│   └── requests.ts               <- Custom request handlers
├── explorers/ (5 tree views)      <- MANTER: consome dados do LSP
├── viewers/ (2 webviews)          <- MANTER: consome dados do LSP
├── parsers/ (5 regex parsers)     <- FALLBACK: quando LSP indisponivel
└── core/ (fieldRegistry)          <- SIMPLIFICAR: dados vem do LSP
```

### 5.3 Beneficios da Integracao

| Aspecto | Antes (regex) | Depois (LSP) |
|---------|---------------|--------------|
| Consistencia | Pode divergir do compilador | 100% identico ao compilador |
| Validacao | Nenhuma | Tempo real com diagnostics |
| Manutenibilidade | 2 parsers para manter | 1 fonte de verdade |
| Novos campos/tipos | Atualizar 2 codebases | Atualizar so o compilador |
| Performance | Re-parse a cada refresh | Cache inteligente no LSP |
| Cross-file analysis | Limitado (workspace scan) | Completo (LinkedProject) |

### 5.4 Estrategia de Migracao

**Passo 1:** Manter Explorer como esta. Adicionar LSP client como provedor alternativo.

**Passo 2:** Para cada tree view, adicionar flag `useLsp: boolean`:
- Se LSP disponivel: buscar dados via custom request
- Se LSP indisponivel: fallback para parser regex atual

**Passo 3:** Quando todos os tree views migrarem, remover parsers regex.

**Passo 4:** Mover Explorer para dentro do repositorio LSP ou criar monorepo.

---

## 6. Decisoes de Design Pendentes

### 6.1 Onde implementar a API publica?

**RESOLVIDO pela spec `synesis_load.qmd`:** A API publica sera `synesis.load()` em `synesis/__init__.py`, conforme spec v0.2.0. O LSP server usara essa funcao (ou `SynesisCompiler.compile()` para compilacao baseada em disco).

O `lsp_adapter.py` continua como interface especifica para validacao de arquivo unico. A compilacao completa usa diretamente a API publica do compilador.

### 6.2 Serializacao do LinkedProject para LSP

**RESOLVIDO pela spec `synesis_load.qmd`:** O `MemoryCompilationResult.to_json_dict()` produz dicts Python nativos, prontos para envio via JSON-RPC do LSP. Nao e necessario criar `to_dict()` em cada dataclass - o metodo de exportacao ja existe na spec.

### 6.3 Granularidade do Cache

| Estrategia | Descricao | Quando invalidar |
|------------|-----------|-------------------|
| A) Cache por workspace | Um CompilationResult por workspace | Qualquer .syn/.synt/.synp/.syno/.bib muda |
| B) Cache por arquivo | ValidationResult por arquivo + CompilationResult compartilhado | Arquivo individual muda: revalida so ele |
| C) Hibrido | ValidationResult por arquivo, LinkedProject por workspace | Arquivo muda: revalida; contexto muda: recompila |

**Recomendacao:** Opcao C - a validacao por arquivo ja funciona (estado atual). Adicionar CompilationResult por workspace para os custom requests do Explorer.

**Dados empiricos (Apendice A.1):** Com ~3.3s para compilacao completa, o cache por workspace e essencial. Recompilar apenas em didSave ou com debounce longo. Para didChange, usar `compile_string()` (~3ms) para parsing incremental do arquivo ativo.

---


## 7. Prioridade de Implementacao

Com a inclusão das funcionalidades premium (Semantic Tokens, Inlay Hints e Refatoração), o cronograma de evolução ganha uma nova camada de refinamento visual e eficiência de edição.

| Prioridade | Feature | Esforco | Valor | Dependencia |
| --- | --- | --- | --- | --- |
| **P0** | `synesis/loadProject` custom request no LSP | Medio | Fundacao / Fim da duplicacao | Compilador v0.2.0 |
| **P1** | `textDocument/semanticTokens` | Medio | **Precisao Visual Absoluta** | `compile_string` v0.2.0 |
| **P1** | `textDocument/hover` & `documentSymbol` | Medio | Navegacao e Info contextual | `LinkedProject` |
| **P1** | Custom requests (References, Codes, Relations) | Alto | Migracao do Explorer para LSP | `synesis/loadProject` |
| **P2** | `textDocument/inlayHint` | Medio | **Produtividade (Dicas em linha)** | `LinkedProject` + Bibliography |
| **P2** | `textDocument/definition` & `completion` | Alto | Autocomplete inteligente | Template + Bib |
| **P2** | Integrar `error_handler.py` | Baixo | Mensagens Pedagogicas | Nenhuma |
| **P3** | `textDocument/rename` | Alto | **Refatoracao Segura (Global)** | `LinkedProject` (Write-back logic) |
| **P3** | `textDocument/signatureHelp` | Medio | Auxilio no preenchimento de campos | Template (Field Specs) |
| **P3** | `synesis/getRelationGraph` | Medio | Visualizacao de Grafos via LSP | `LinkedProject` |

---

### Observações sobre as novas prioridades:

* **Por que Semantic Tokens em P1?** No modelo atual, o Explorer usa Regex para colorir o código. Implementar Semantic Tokens via LSP cedo no projeto resolve a inconsistência visual imediatamente após a centralização dos dados.
* **Inlay Hints como P2**: Esta funcionalidade reduz drasticamente a carga cognitiva do usuário ao exibir metadados da bibliografia (Autor, Ano) automaticamente, sendo um diferencial competitivo para a Synesis.
* **Refatoração (Rename) em P3**: Embora de alto valor, exige lógica de escrita e manipulação de múltiplos arquivos (Write-back), sendo mais seguro implementá-la após a estabilização das APIs de leitura.

---

## 8. Resumo

O ecossistema Synesis tem tres componentes com maturidades distintas:

1. **Compilador** (v0.2.0) - Pipeline completo com 18 tipos de erro, linker semantico, 3 formatos de exportacao e **API in-memory implementada**
2. **LSP Server** (v0.1.0) - Adaptador funcional mas limitado a diagnostics
3. **Synesis-Explorer** (v0.3.0) - Extensao rica mas com 7 duplicacoes de logica do compilador

A **oportunidade central** e usar o LSP como ponte unica entre o compilador e o editor, eliminando a duplicacao de parsers e habilitando features avancadas (hover, completion, go-to-definition) que beneficiam tanto o LSP client atual (`vscode-extension/`) quanto o Explorer.

A **API do compilador v0.2.0** (implementada 2026-01-21) disponibiliza:
- `synesis.load()` -> `MemoryCompilationResult` com `to_json_dict()` (resolve serializacao)
- `synesis.compile_string()` -> parsing de fragmentos (util para hover/completion)
- `MemoryCompilationResult` -> acesso a `LinkedProject`, `stats`, `diagnostics`
- Funcoes auxiliares in-memory: `load_template_from_string()`, `load_bibliography_from_string()`
- Exportadores in-memory: `build_json_payload()`, `build_csv_tables()`, `build_xls_workbook()`

**Status:** O bloqueio P0 no compilador foi **resolvido**. O **proximo passo** e consumir a API v0.2.0 no LSP server, criando custom requests (`synesis/loadProject`, `synesis/getProjectStats`) e adicionando cache de `CompilationResult` por workspace.

**Sequencia critica (atualizada):**
```
synesis.load (compilador) ✅ PRONTO -> synesis/loadProject (LSP) ⬜ PROXIMO -> Explorer consome LSP -> parsers regex eliminados
```
---

## 9. Fronteiras de Produtividade: O Próximo Nível (Pós-Fase 6)

Para que a Synesis ofereça o estado da arte em experiência de desenvolvedor (DX), as seguintes funcionalidades devem ser integradas ao roteiro de longo prazo:

### 9.1 Semantic Tokens (Colorização Semântica)

Diferente do realce sintático baseado em Expressões Regulares (TextMate), os **Semantic Tokens** utilizam a árvore sintática real do compilador para colorir o código.

**Status (implementável agora):**
* Pode ser implementado já com `compile_string()` (v0.2.0) sem depender de `LinkedProject`.

* **Precisão Semântica**: O editor pode diferenciar visualmente um `@bibref` que existe na bibliografia de um que não existe, aplicando cores de "erro" ou "alerta" antes mesmo da validação completa.
* **Contexto de Campo**: Campos obrigatórios definidos no `*.synt` podem ter uma cor distinta de campos opcionais, guiando o olhar do pesquisador durante o preenchimento.
* **Diferenciação de Escopo**: Nodos de ONTOLOGY, SOURCE e ITEM podem receber hierarquias de cores baseadas na profundidade da árvore semântica.

### 9.2 Inlay Hints (Dicas em Linha)

Esta funcionalidade injeta informações contextuais diretamente no editor de texto, sem alterar o conteúdo do arquivo.

**Status (depende de cache/LinkedProject):**
* Requer bibliografia e contexto cross-file (via `synesis/loadProject` + cache).

* **Metadados de Referência**: Ao digitar um `@bibref`, o LSP pode exibir o (Ano, Autor) de forma fantasmagórica ao lado do código, facilitando a conferência imediata.
* **Dicas de Parâmetros**: Em blocos de `CHAIN`, o LSP pode exibir o nome da relação esperada para cada item da cadeia, baseando-se nas regras do template.

### 9.3 Refatoração Global (Rename Symbol)

A centralização no `LinkedProject` permite que o LSP manipule o workspace de forma segura.

**Status (depende de write-back):**
* Exige `WorkspaceEdit` com escrita em múltiplos arquivos e validação pós-rename.

* **Renomeação de Códigos**: Alterar um nome de código em um bloco `ONTOLOGY` e propagar a mudança automaticamente para todas as ocorrências em arquivos `*.syn`.
* **Integridade Referencial**: Garantir que a alteração de um identificador no projeto `*.synp` não quebre as conexões com os templates e ontologias.

### 9.4 Signature Help e Smart Selection

**Status:**
* **Signature Help (implementável agora):** pode usar `FieldSpec` do template (`*.synt`) sem precisar de `LinkedProject`.
* **Smart Selection (depende de endpoint LSP):** requer `textDocument/selectionRange` e mapeamento AST -> ranges.

* **Signature Help**: Conforme o usuário preenche um campo, um pequeno popup mostra a definição original do template, incluindo `ARITY` e `TYPE` esperados.
* **Smart Selection**: Permite que o usuário expanda a seleção de texto logicamente (ex: selecionar um campo, depois o item inteiro, depois o bloco SOURCE) com base na estrutura gramatical do compilador.
