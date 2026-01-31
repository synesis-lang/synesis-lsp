# Plano de Implementacao: Synesis LSP Server v0.2.0

**Escopo:** Apenas o servidor LSP (`synesis_lsp/`). Sem mudancas no compilador ou extensao VSCode.
**Base:** [STUDY-LSP-ADEQUACY.md](docs/STUDY-LSP-ADEQUACY.md) + Validacao Empirica (Apendice A)
**Compilador:** v0.2.1 instalado, API `synesis.load()` e `compile_string()` disponiveis.

---

## Dados Empiricos de Referencia

| Operacao | Tempo | Uso recomendado no LSP |
|----------|-------|------------------------|
| `SynesisCompiler.compile()` | ~3.7s | didSave (com cache) |
| `synesis.load()` | ~3.3s | didSave (dirty buffers futuramente) |
| `compile_string()` (fragmento) | ~3ms | didChange, hover, semanticTokens |
| `compile_string()` (arquivo grande) | ~69ms | documentSymbol |
| `to_json_dict()` | ~259ms | Evitar; usar LinkedProject direto |

---

## Arquitetura Final

```
synesis_lsp/
    __init__.py              (bump para v0.2.0)
    __main__.py              (inalterado)
    server.py                (modificado: todos os handlers)
    converters.py            (modificado: error_handler)
    cache.py                 (NOVO: WorkspaceCache)
    semantic_tokens.py       (NOVO: compile_string -> tokens)
    symbols.py               (NOVO: compile_string -> DocumentSymbol)
    hover.py                 (NOVO: LinkedProject -> Hover)
    definition.py            (NOVO: LinkedProject -> Location)
    completion.py            (NOVO: template + bib -> CompletionList)
    inlay_hints.py           (NOVO: bibliography -> InlayHint)
    explorer_requests.py     (NOVO: LinkedProject -> custom request dicts)
    graph.py                 (NOVO: all_triples -> Mermaid)
tests/
    test_cache.py            (NOVO)
    test_semantic_tokens.py  (NOVO)
    test_symbols.py          (NOVO)
    test_hover.py            (NOVO)
    test_definition.py       (NOVO)
    test_completion.py       (NOVO)
    test_inlay_hints.py      (NOVO)
    test_explorer_requests.py (NOVO)
    test_server_commands.py  (NOVO)
```

## Grafo de Dependencias entre Steps

```
Step 1 (Cache + loadProject) ──> Step 2 (getProjectStats)
    │
    ├──> Step 5 (hover)
    ├──> Step 6 (explorer requests)
    ├──> Step 7 (inlay hints)
    ├──> Step 8 (definition + completion)
    └──> Step 10a (relation graph)

Step 3 (semantic tokens) ── independente (usa compile_string)
Step 4 (document symbols) ── independente (usa compile_string)
Step 9 (error_handler)    ── independente (modifica converters.py)
```

Steps 3, 4 e 9 podem ser implementados em paralelo com Step 1.
Steps 5-8 e 10 dependem do Step 1 (cache).

---

## Step 1: WorkspaceCache + `synesis/loadProject` (P0)

### Objetivo
Criar o cache de `CompilationResult` por workspace e o custom request `synesis/loadProject` que sera a fundacao para todas as features cross-file.

### Arquivos

**Criar:** `synesis_lsp/cache.py`
```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

@dataclass
class CachedCompilation:
    """Resultado de compilacao em cache com timestamp."""
    result: object  # CompilationResult do synesis
    timestamp: float = field(default_factory=time.time)
    workspace_root: Path = Path(".")

class WorkspaceCache:
    """Cache de CompilationResult por workspace."""

    def __init__(self):
        self._cache: dict[str, CachedCompilation] = {}

    def get(self, workspace_key: str) -> Optional[CachedCompilation]:
        return self._cache.get(workspace_key)

    def put(self, workspace_key: str, result, workspace_root: Path):
        self._cache[workspace_key] = CachedCompilation(
            result=result, workspace_root=workspace_root
        )
        logger.info(f"Cache atualizado para workspace: {workspace_key}")

    def invalidate(self, workspace_key: str):
        if self._cache.pop(workspace_key, None):
            logger.info(f"Cache invalidado para workspace: {workspace_key}")

    def has(self, workspace_key: str) -> bool:
        return workspace_key in self._cache
```

**Modificar:** `synesis_lsp/server.py`

1. Adicionar `workspace_cache = WorkspaceCache()` ao `SynesisLanguageServer.__init__`
2. Criar funcao helper `_resolve_workspace_root(ls, params)` para extrair workspace root de params ou documentos abertos
3. Adicionar handler:

```python
from synesis.compiler import SynesisCompiler
from synesis.parser.lexer import SynesisSyntaxError

@server.command("synesis/loadProject")
def load_project(ls: SynesisLanguageServer, params) -> dict:
    """Compila projeto completo e retorna JSON dict."""
    try:
        workspace_root = _resolve_workspace_root(ls, params)
        if not workspace_root:
            return {"success": False, "error": "Workspace nao encontrado"}

        # Buscar .synp
        synp_files = list(Path(workspace_root).glob("**/*.synp"))
        if not synp_files:
            return {"success": False, "error": "Nenhum arquivo .synp encontrado"}

        # Compilar (usa disco, ~3.7s)
        compiler = SynesisCompiler(synp_files[0])
        result = compiler.compile()

        # Cachear
        ws_key = str(workspace_root)
        ls.workspace_cache.put(ws_key, result, Path(workspace_root))

        # Retornar stats (nao o JSON completo de 21MB)
        return {
            "success": True,
            "stats": {
                "source_count": result.stats.source_count,
                "item_count": result.stats.item_count,
                "ontology_count": result.stats.ontology_count,
                "code_count": result.stats.code_count,
                "chain_count": result.stats.chain_count,
                "triple_count": result.stats.triple_count,
            },
            "has_errors": result.has_errors(),
            "has_warnings": result.has_warnings(),
        }
    except SynesisSyntaxError as e:
        return {
            "success": False,
            "error": e.message,
            "location": {"file": str(e.location.file), "line": e.location.line, "column": e.location.column},
        }
    except Exception as e:
        logger.error(f"loadProject falhou: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
```

4. No `did_save`, apos invalidar cache do `lsp_adapter`, tambem invalidar `workspace_cache`:
```python
ls.workspace_cache.invalidate(workspace_key)
```

5. No `did_change_watched_files`, mesma invalidacao.

### Testes

`tests/test_cache.py`:
- `test_put_get`: Armazena e recupera resultado
- `test_invalidate`: Invalida e verifica que `get` retorna None
- `test_has`: Verifica presenca
- `test_multiple_workspaces`: Cache isolado por workspace

### Prompt para execucao

```
Implemente o Step 1 do plano LSP_Implementation.md:

1. Crie `synesis_lsp/cache.py` com a classe `WorkspaceCache` (get/put/invalidate/has)
   e `CachedCompilation` dataclass conforme o plano.

2. Modifique `synesis_lsp/server.py`:
   - Importe WorkspaceCache e adicione `self.workspace_cache = WorkspaceCache()`
     ao __init__ de SynesisLanguageServer
   - Crie funcao helper `_resolve_workspace_root(ls, params)` que tenta extrair
     workspace_root de params (se dict com "workspaceRoot") ou do primeiro documento
     aberto usando _find_workspace_root
   - Adicione @server.command("synesis/loadProject") handler que:
     a) Resolve workspace root
     b) Busca *.synp via glob
     c) Compila com SynesisCompiler(Path).compile()
     d) Cacheia resultado em ls.workspace_cache
     e) Retorna dict com success, stats, has_errors, has_warnings
     f) Trata SynesisSyntaxError com try/except
   - No did_save e did_change_watched_files, apos _invalidate_cache(),
     adicione ls.workspace_cache.invalidate(workspace_key)

3. Crie `tests/test_cache.py` com testes unitarios para WorkspaceCache.

Siga os padroes existentes em server.py: docstrings em portugues,
logging com logger.info/error, try/except robusto.
Nao modifique o compilador nem a extensao VSCode.
```

---

## Step 2: `synesis/getProjectStats` (P0)

### Objetivo
Custom request leve que retorna estatisticas do projeto a partir do cache.

### Arquivos

**Modificar:** `synesis_lsp/server.py`

```python
@server.command("synesis/getProjectStats")
def get_project_stats(ls: SynesisLanguageServer, params) -> dict:
    """Retorna estatisticas do projeto compilado."""
    workspace_root = _resolve_workspace_root(ls, params)
    if not workspace_root:
        return {"success": False, "error": "Workspace nao encontrado"}

    cached = ls.workspace_cache.get(str(workspace_root))
    if not cached:
        return {"success": False, "error": "Projeto nao carregado. Chame synesis/loadProject primeiro."}

    stats = cached.result.stats
    return {
        "success": True,
        "stats": {
            "source_count": stats.source_count,
            "item_count": stats.item_count,
            "ontology_count": stats.ontology_count,
            "code_count": stats.code_count,
            "chain_count": stats.chain_count,
            "triple_count": stats.triple_count,
        }
    }
```

### Testes

`tests/test_server_commands.py`:
- `test_get_stats_without_cache`: Retorna success=False
- `test_get_stats_with_cache`: Mock de CompilationResult com stats conhecidos

### Prompt para execucao

```
Implemente o Step 2 do plano LSP_Implementation.md:

Adicione o handler @server.command("synesis/getProjectStats") em synesis_lsp/server.py.
Ele deve ler do workspace_cache (criado no Step 1) e retornar CompilationStats como dict.
Se cache vazio, retorna {"success": False, "error": "..."}.
Crie tests/test_server_commands.py com testes usando mock de CompilationResult.
```

---

## Step 3: `textDocument/semanticTokens` (P1)

### Objetivo
Colorização semântica usando AST real do compilador via `compile_string()` (~3ms).

### Arquivos

**Criar:** `synesis_lsp/semantic_tokens.py`

Mapeamento de tokens Synesis para LSP:

| Elemento Synesis | SemanticTokenType | Modifier |
|------------------|-------------------|----------|
| SOURCE, ITEM, END, ONTOLOGY | Keyword | declaration |
| @bibref | Variable | reference |
| nome_do_campo: | Property | |
| valor de campo | String | |
| codigo (em ordem_2a) | EnumMember | |
| TEMPLATE, PROJECT | Namespace | |

Funcao principal:
```python
def compute_semantic_tokens(source: str, uri: str) -> SemanticTokens:
    try:
        nodes = synesis.compile_string(source, uri)
    except Exception:
        return SemanticTokens(data=[])
    # Extrair tokens de cada node, encodar em delta format
```

**Modificar:** `synesis_lsp/server.py`
- Registrar `SemanticTokensOptions(legend=LEGEND, full=True)` nas capabilities
- Handler `@server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL)`

### Nota sobre implementacao

O delta encoding do LSP semantic tokens requer: `[deltaLine, deltaStartChar, length, tokenType, tokenModifiers]` para cada token, relativo ao token anterior. A funcao `_encode_deltas(tokens)` deve ordenar tokens por (line, col) e computar deltas.

A extracao de tokens precisa analisar o texto-fonte linha a linha, usando as posicoes dos nodes (`node.location`) para identificar keywords (SOURCE, ITEM, END) e usando regex para detectar `@bibref`, `campo:` e valores.

### Testes

`tests/test_semantic_tokens.py`:
- `test_empty_source`: Retorna tokens vazios
- `test_source_block`: Verifica tokens para SOURCE @bibref ... END SOURCE
- `test_syntax_error`: Retorna tokens vazios (sem crash)

### Prompt para execucao

```
Implemente o Step 3 do plano LSP_Implementation.md:

1. Crie synesis_lsp/semantic_tokens.py com:
   - TOKEN_TYPES: lista de SemanticTokenTypes (Keyword, Variable, Property, String,
     EnumMember, Namespace)
   - TOKEN_MODIFIERS: lista de SemanticTokenModifiers (Declaration)
   - LEGEND: SemanticTokensLegend com os tipos e modifiers
   - compute_semantic_tokens(source, uri) -> SemanticTokens:
     a) Chama synesis.compile_string(source, uri) para obter AST nodes
     b) Para cada SourceNode: extrai tokens de keywords (SOURCE, END SOURCE),
        bibref (@xxx), nomes de campos, valores
     c) Para cada ItemNode: extrai keywords (ITEM, END ITEM), bibref, campos
     d) Para cada OntologyNode: extrai keywords (ONTOLOGY, END ONTOLOGY), concept
     e) Encodar tokens em formato delta LSP [deltaLine, deltaStartChar, length, type, mod]
     f) Em caso de SynesisSyntaxError, retorna SemanticTokens(data=[])
   - _encode_deltas(tokens): ordena por (line, col) e computa deltas

2. Modifique synesis_lsp/server.py:
   - Importe SemanticTokensOptions, TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, SemanticTokensParams
   - Registre SemanticTokensOptions no servidor (via server = SynesisLanguageServer
     com capabilities)
   - Adicione handler @server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL)

3. Crie tests/test_semantic_tokens.py.

Nota: compile_string retorna lista de SourceNode/ItemNode/OntologyNode.
SourceNode tem: bibref, fields, items, location.
ItemNode tem: bibref, location, codes, field_names, extra_fields.
OntologyNode tem: concept, fields, location.
Todos tem location com .line e .column (1-based).

O fonte precisa ser analisado linha por linha para extrair posicoes exatas dos
keywords, pois os nodes so indicam a posicao inicial do bloco.
```

---

## Step 4: `textDocument/documentSymbol` (P1)

### Objetivo
Outline do documento mostrando SOURCE, ITEM, ONTOLOGY com hierarquia.

### Arquivos

**Criar:** `synesis_lsp/symbols.py`

```python
from lsprotocol.types import DocumentSymbol, SymbolKind, Range, Position
import synesis
from synesis.ast.nodes import SourceNode, ItemNode, OntologyNode, ProjectNode

def compute_document_symbols(source: str, uri: str) -> list[DocumentSymbol]:
    try:
        nodes = synesis.compile_string(source, uri)
    except Exception:
        return []

    symbols = []
    for node in nodes:
        if isinstance(node, SourceNode):
            children = [
                DocumentSymbol(
                    name=f"ITEM #{i+1}",
                    kind=SymbolKind.Method,
                    range=_make_range(item.location),
                    selection_range=_make_range(item.location),
                )
                for i, item in enumerate(node.items)
            ]
            symbols.append(DocumentSymbol(
                name=f"SOURCE {node.bibref}",
                kind=SymbolKind.Class,
                range=_make_range(node.location),
                selection_range=_make_range(node.location),
                children=children,
            ))
        elif isinstance(node, OntologyNode):
            symbols.append(DocumentSymbol(
                name=f"ONTOLOGY {node.concept}",
                kind=SymbolKind.Struct,
                range=_make_range(node.location),
                selection_range=_make_range(node.location),
            ))
    return symbols
```

**Modificar:** `synesis_lsp/server.py`
- Handler `@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)`

### Nota sobre Range

O `location` dos nodes indica apenas o inicio do bloco. Para o `range` completo (inicio ate END), seria necessario calcular o fim escaneando o fonte. Uma abordagem pragmatica: usar `_make_range(location)` com uma range curta (apenas a linha de declaracao), pois o LSP usa `selection_range` para navegacao.

### Testes

`tests/test_symbols.py`:
- `test_syn_file`: 1 SOURCE com 2 ITEMs -> 1 symbol com 2 children
- `test_syno_file`: 3 ONTOLOGYs -> 3 symbols Struct
- `test_empty`: Retorna lista vazia
- `test_syntax_error`: Retorna lista vazia

### Prompt para execucao

```
Implemente o Step 4 do plano LSP_Implementation.md:

1. Crie synesis_lsp/symbols.py com compute_document_symbols(source, uri) que:
   a) Chama synesis.compile_string(source, uri)
   b) Para SourceNode: cria DocumentSymbol(kind=Class) com children ITEM (kind=Method)
   c) Para OntologyNode: cria DocumentSymbol(kind=Struct)
   d) Para ProjectNode: cria DocumentSymbol(kind=Namespace) (se houver)
   e) Retorna [] em caso de excecao

2. Modifique server.py: adicione handler @server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)

3. Crie tests/test_symbols.py com testes usando snippets Synesis reais.

Os ItemNodes dentro do SourceNode estao em node.items (lista).
Cada node tem location com .file, .line, .column (1-based).
Converta para 0-based ao criar Range/Position.
```

---

## Step 5: `textDocument/hover` (P1)

### Objetivo
Informacao contextual ao passar o mouse: @bibref -> bibliografia, codigo -> ontologia, campo -> template.

### Arquivos

**Criar:** `synesis_lsp/hover.py`

```python
import re
from typing import Optional
from lsprotocol.types import Hover, MarkupContent, MarkupKind, Position

def compute_hover(source: str, position: Position, cached_result) -> Optional[Hover]:
    """Computa hover baseado na posicao do cursor."""
    lines = source.splitlines()
    if position.line >= len(lines):
        return None
    line = lines[position.line]
    word = _get_word_at_position(line, position.character)
    if not word:
        return None

    # 1. @bibref -> bibliografia
    if word.startswith("@") and cached_result:
        bibref = word[1:]
        bib = getattr(cached_result.result, 'bibliography', None) or {}
        entry = bib.get(bibref)
        if entry:
            md = f"**{entry.get('title', 'N/A')}**\n\n"
            md += f"*{entry.get('author', 'N/A')}* ({entry.get('year', 'N/A')})\n\n"
            md += f"Type: `{entry.get('ENTRYTYPE', 'N/A')}`"
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))

    # 2. campo: -> template FieldSpec
    if _is_field_name(line, position.character, word) and cached_result:
        template = getattr(cached_result.result, 'template', None)
        if template:
            spec = template.field_specs.get(word)
            if spec:
                md = f"**Campo: `{spec.name}`**\n\n"
                md += f"- Tipo: `{spec.type.name}`\n"
                md += f"- Escopo: `{spec.scope.name}`\n"
                if spec.description:
                    md += f"- Descricao: {spec.description}\n"
                return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))

    # 3. codigo -> ontologia + uso
    if cached_result:
        lp = getattr(cached_result.result, 'linked_project', None)
        if lp and word in lp.ontology_index:
            onto = lp.ontology_index[word]
            usage = len(lp.code_usage.get(word, []))
            md = f"**Ontologia: `{onto.concept}`**\n\n"
            if onto.description:
                md += f"{onto.description}\n\n"
            for k, v in onto.fields.items():
                md += f"- {k}: {v[:80]}\n"
            md += f"\nUsado em **{usage}** itens"
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=md))

    return None
```

### Dados necessarios

Hover depende do `workspace_cache` (Step 1). Se cache vazio, hover retorna `None` (graceful degradation).

Fonte de dados empiricos (Apendice A):
- `bibliography["entrevista01"]` -> dict com year, author, title, ENTRYTYPE, ID
- `template.field_specs["ordem_1a"]` -> FieldSpec com name, type, scope, description
- `ontology_index["proposito"]` -> OntologyNode com concept, description, fields
- `code_usage["proposito"]` -> List[ItemNode] (321 items)

### Testes

`tests/test_hover.py`:
- `test_hover_bibref`: Mock bibliography, verifica markdown com titulo/autor/ano
- `test_hover_field`: Mock template com FieldSpec, verifica tipo e escopo
- `test_hover_code`: Mock ontology_index e code_usage, verifica contagem
- `test_hover_no_cache`: Retorna None
- `test_hover_unknown_word`: Retorna None

### Prompt para execucao

```
Implemente o Step 5 do plano LSP_Implementation.md:

1. Crie synesis_lsp/hover.py com:
   - compute_hover(source, position, cached_result) -> Optional[Hover]
   - _get_word_at_position(line, character) -> str: extrai palavra sob o cursor
   - _is_field_name(line, character, word) -> bool: verifica se e nome de campo (seguido de ":")
   - Logica:
     a) Se word comeca com @: buscar em cached_result.result.bibliography
     b) Se e campo (word:): buscar em cached_result.result.template.field_specs
     c) Senao: buscar em cached_result.result.linked_project.ontology_index
     d) Retornar None se cache vazio ou word nao encontrado
   - Formatar como Markdown com MarkupContent

2. Modifique server.py:
   - Importe TEXT_DOCUMENT_HOVER, HoverParams
   - Adicione handler que obtem documento, cached result do workspace_cache,
     e chama compute_hover

3. Crie tests/test_hover.py com mocks de CompilationResult.

cached_result e um CachedCompilation com .result (CompilationResult).
CompilationResult tem: .bibliography (Dict[str, dict]), .template (TemplateNode),
.linked_project (LinkedProject com ontology_index, code_usage).
```

---

## Step 6: Custom Requests para Explorer (P1)

### Objetivo
Tres custom requests que substituem os parsers regex do Explorer com dados do compilador.

### Arquivos

**Criar:** `synesis_lsp/explorer_requests.py`

```python
def get_references(cached_result) -> dict:
    """Retorna lista de SOURCEs com contagem de items."""
    if not cached_result or not cached_result.result.linked_project:
        return {"success": False, "error": "Projeto nao carregado"}
    lp = cached_result.result.linked_project
    refs = []
    for bibref, src in lp.sources.items():
        refs.append({
            "bibref": src.bibref,
            "itemCount": len(src.items),
            "fields": dict(src.fields),
            "location": {"file": str(src.location.file), "line": src.location.line, "column": src.location.column},
        })
    return {"success": True, "references": refs}

def get_codes(cached_result) -> dict:
    """Retorna lista de codigos com frequencia de uso."""
    if not cached_result or not cached_result.result.linked_project:
        return {"success": False, "error": "Projeto nao carregado"}
    lp = cached_result.result.linked_project
    codes = []
    for code, items in lp.code_usage.items():
        codes.append({
            "code": code,
            "usageCount": len(items),
            "ontologyDefined": code in lp.ontology_index,
        })
    return {"success": True, "codes": codes}

def get_relations(cached_result) -> dict:
    """Retorna lista de triples (relacoes)."""
    if not cached_result or not cached_result.result.linked_project:
        return {"success": False, "error": "Projeto nao carregado"}
    lp = cached_result.result.linked_project
    relations = [{"from": s, "relation": r, "to": o} for s, r, o in lp.all_triples]
    return {"success": True, "relations": relations}
```

**Modificar:** `synesis_lsp/server.py`
- 3 handlers `@server.command()`

### Dados empiricos

Projeto Davi: `sources` tem 61 entries, `code_usage` tem 281 entries, `all_triples` esta vazio (sem chains).

### Testes

`tests/test_explorer_requests.py`:
- `test_get_references`: Mock com 3 SourceNodes, verifica output
- `test_get_codes`: Mock com code_usage conhecido
- `test_get_relations`: Mock com triples
- `test_no_cache`: Todos retornam success=False

### Prompt para execucao

```
Implemente o Step 6 do plano LSP_Implementation.md:

1. Crie synesis_lsp/explorer_requests.py com tres funcoes:
   - get_references(cached_result) -> dict com lista de SOURCEs
   - get_codes(cached_result) -> dict com lista de codigos e frequencia
   - get_relations(cached_result) -> dict com lista de triples
   Cada funcao retorna {"success": False} se cache vazio.

2. Modifique server.py: adicione 3 handlers @server.command():
   - "synesis/getReferences" -> get_references
   - "synesis/getCodes" -> get_codes
   - "synesis/getRelations" -> get_relations
   Cada handler resolve workspace_root, obtem cache, e delega para funcao.

3. Crie tests/test_explorer_requests.py.

Dados do LinkedProject (ver Apendice A.3 do estudo):
- sources: Dict[str, SourceNode] com bibref, fields, items, location
- code_usage: Dict[str, List[ItemNode]] com contagem por codigo
- all_triples: List[Tuple[str,str,str]] com (sujeito, relacao, objeto)
```

---

## Step 7: `textDocument/inlayHint` (P2)

### Objetivo
Exibir (Autor, Ano) inline apos cada @bibref no editor.

### Arquivos

**Criar:** `synesis_lsp/inlay_hints.py`

```python
import re
from lsprotocol.types import InlayHint, InlayHintKind, Position

BIBREF_PATTERN = re.compile(r'@(\w+)')

def compute_inlay_hints(source: str, cached_result, range_=None) -> list[InlayHint]:
    if not cached_result:
        return []
    bib = getattr(cached_result.result, 'bibliography', None)
    if not bib:
        return []

    hints = []
    for line_num, line in enumerate(source.splitlines()):
        # Pular se fora do range solicitado
        if range_ and (line_num < range_.start.line or line_num > range_.end.line):
            continue
        for match in BIBREF_PATTERN.finditer(line):
            bibref = match.group(1)
            if bibref in bib:
                entry = bib[bibref]
                author = entry.get("author", "?")
                year = entry.get("year", "?")
                short = author.split(",")[0].strip() if author else "?"
                hints.append(InlayHint(
                    position=Position(line=line_num, character=match.end()),
                    label=f" ({short}, {year})",
                    kind=InlayHintKind.Type,
                    padding_left=True,
                ))
    return hints
```

### Testes

`tests/test_inlay_hints.py`:
- `test_bibref_hint`: Source com @entrevista01, mock bibliography, verifica hint
- `test_no_bibliography`: Retorna vazio
- `test_unknown_bibref`: @inexistente nao gera hint

### Prompt para execucao

```
Implemente o Step 7 do plano LSP_Implementation.md:

1. Crie synesis_lsp/inlay_hints.py com compute_inlay_hints(source, cached_result, range_).
   Usa regex para encontrar @bibref, busca em cached_result.result.bibliography,
   e retorna InlayHint com "(Autor, Ano)" apos cada referencia.

2. Modifique server.py: registre TEXT_DOCUMENT_INLAY_HINT com handler
   que obtem documento, cache, e chama compute_inlay_hints.

3. Crie tests/test_inlay_hints.py.

Bibliografia e um dict[str, dict] com keys: year, author, title, ENTRYTYPE, ID.
```

---

## Step 8: `textDocument/definition` + `textDocument/completion` (P2)

### Objetivo
Go-to-definition para @bibref e codigos. Autocomplete para bibrefs, codigos, campos.

### Arquivos

**Criar:** `synesis_lsp/definition.py`

```python
def compute_definition(source: str, position: Position, cached_result) -> Optional[Location]:
    """Resolve definicao: @bibref -> SOURCE, codigo -> ONTOLOGY."""
    word = _get_word_at_position(...)
    if not word or not cached_result:
        return None

    lp = getattr(cached_result.result, 'linked_project', None)
    if not lp:
        return None

    # @bibref -> SourceNode.location
    if word.startswith("@"):
        bibref = word[1:]
        src = lp.sources.get(bibref)
        if src:
            return Location(uri=_to_uri(src.location.file), range=_to_range(src.location))

    # codigo -> OntologyNode.location
    if word in lp.ontology_index:
        onto = lp.ontology_index[word]
        return Location(uri=_to_uri(onto.location.file), range=_to_range(onto.location))

    return None
```

**Criar:** `synesis_lsp/completion.py`

```python
def compute_completions(source: str, position: Position, cached_result, trigger_char=None) -> CompletionList:
    items = []
    if not cached_result:
        return CompletionList(is_incomplete=False, items=[])

    result = cached_result.result

    # Apos @: sugerir bibrefs
    if trigger_char == "@" or _is_after_at(line, position.character):
        bib = getattr(result, 'bibliography', {}) or {}
        for bibref, entry in bib.items():
            items.append(CompletionItem(
                label=f"@{bibref}",
                kind=CompletionItemKind.Reference,
                detail=f"{entry.get('author', '?')} ({entry.get('year', '?')})",
                insert_text=bibref,
            ))

    # Sugerir codigos da ontologia
    lp = getattr(result, 'linked_project', None)
    if lp:
        for concept in lp.ontology_index:
            items.append(CompletionItem(
                label=concept,
                kind=CompletionItemKind.EnumMember,
                detail=f"Ontologia ({len(lp.code_usage.get(concept, []))} usos)",
            ))

    # Sugerir campos do template
    template = getattr(result, 'template', None)
    if template:
        for name, spec in template.field_specs.items():
            items.append(CompletionItem(
                label=f"{name}:",
                kind=CompletionItemKind.Property,
                detail=f"{spec.type.name} ({spec.scope.name})",
                documentation=spec.description or "",
            ))

    return CompletionList(is_incomplete=False, items=items)
```

**Modificar:** `synesis_lsp/server.py`
- Handler `TEXT_DOCUMENT_DEFINITION`
- Handler `TEXT_DOCUMENT_COMPLETION` com `CompletionOptions(trigger_characters=["@"])`

### Nota sobre resolucao de arquivo

SourceNode.location.file e OntologyNode.location.file sao paths relativos (ex: `interviews\entrevista01.syn`, `Davi.syno`). Para construir o URI LSP, combinar com o workspace_root do cache:

```python
def _to_uri(workspace_root: Path, file_path) -> str:
    full = workspace_root / str(file_path)
    return full.as_uri()
```

### Testes

`tests/test_definition.py`:
- `test_goto_bibref`: Resolve @entrevista01 -> SourceNode location
- `test_goto_code`: Resolve proposito -> OntologyNode location
- `test_unknown`: Retorna None

`tests/test_completion.py`:
- `test_after_at`: Retorna bibrefs
- `test_codes`: Retorna codigos da ontologia
- `test_fields`: Retorna campos do template
- `test_no_cache`: Retorna lista vazia

### Prompt para execucao

```
Implemente o Step 8 do plano LSP_Implementation.md:

1. Crie synesis_lsp/definition.py com compute_definition(source, position, cached_result)
   que resolve: @bibref -> SourceNode.location, codigo -> OntologyNode.location.
   Os paths dos nodes sao relativos ao workspace; combine com cached_result.workspace_root.

2. Crie synesis_lsp/completion.py com compute_completions(source, position, cached_result, trigger_char)
   que sugere: bibrefs apos @, codigos da ontologia, campos do template.
   Use CompletionItemKind.Reference para bibrefs, EnumMember para codigos, Property para campos.

3. Modifique server.py:
   - Handler TEXT_DOCUMENT_DEFINITION
   - Handler TEXT_DOCUMENT_COMPLETION com CompletionOptions(trigger_characters=["@"])

4. Crie tests/test_definition.py e tests/test_completion.py.

SourceNode.location.file pode ser WindowsPath relativo (ex: "interviews\entrevista01.syn").
Combine com workspace_root para URI completo.
```

---

## Step 9: Integrar `error_handler.py` (P2)

### Objetivo
Enriquecer mensagens de diagnostico com contexto pedagogico do error_handler do compilador.

### Arquivos

**Modificar:** `synesis_lsp/converters.py`

### Investigacao necessaria

Antes de implementar, verificar a API publica do `error_handler.py` do compilador. O arquivo tem 574 linhas e pode conter funcoes como `format_error_message()` ou similar.

### Prompt para execucao

```
Implemente o Step 9 do plano LSP_Implementation.md:

1. Primeiro, leia o arquivo do compilador synesis/error_handler.py para entender
   sua API publica (funcoes exportadas, como formata mensagens de erro).

2. Modifique synesis_lsp/converters.py:
   - Tente importar a funcao de formatacao do error_handler (try/except ImportError)
   - Na funcao build_diagnostic(), se error_handler disponivel, use a formatacao
     enriquecida em vez de error.to_diagnostic()
   - Mantenha fallback para error.to_diagnostic() se import falhar

3. Atualize testes em tests/test_converters.py.

O error_handler tem 574 linhas e produz mensagens pedagogicas com contexto
e sugestoes de correcao. Nao esta sendo usado pelo LSP atualmente.
```

---

## Step 10: Features P3

### Step 10a: `synesis/getRelationGraph`

**Criar:** `synesis_lsp/graph.py`

```python
def get_relation_graph(cached_result, bibref=None) -> dict:
    if not cached_result or not cached_result.result.linked_project:
        return {"success": False, "error": "Projeto nao carregado"}
    triples = cached_result.result.linked_project.all_triples
    if not triples:
        return {"success": True, "mermaidCode": "graph LR\n    empty[Sem relacoes]"}
    lines = ["graph LR"]
    for subj, rel, obj in triples:
        lines.append(f'    {subj} -->|{rel}| {obj}')
    return {"success": True, "mermaidCode": "\n".join(lines)}
```

### Prompt para execucao (10a)

```
Implemente o Step 10a do plano LSP_Implementation.md:

Crie synesis_lsp/graph.py com get_relation_graph(cached_result, bibref) que gera
codigo Mermaid.js a partir de linked_project.all_triples.
Registre @server.command("synesis/getRelationGraph") em server.py.
Crie testes.
```

### Step 10b: `textDocument/signatureHelp`

Mostra definicao do campo (tipo, arity, descricao) durante preenchimento. Trigger: apos `campo:`.

### Prompt para execucao (10b)

```
Implemente o Step 10b do plano LSP_Implementation.md:

Crie synesis_lsp/signature_help.py com compute_signature_help(source, position, cached_result)
que detecta quando o usuario esta preenchendo um campo (ex: "ordem_2a: ") e mostra
a definicao do FieldSpec (tipo, arity, descricao, valores permitidos) como SignatureHelp.
Registre TEXT_DOCUMENT_SIGNATURE_HELP com trigger ":".
```

### Step 10c: `textDocument/rename`

Renomear codigo/bibref em todos os arquivos do workspace. Requer WorkspaceEdit com TextEdit por arquivo.

### Prompt para execucao (10c)

```
Implemente o Step 10c do plano LSP_Implementation.md:

Crie synesis_lsp/rename.py com compute_rename(source, position, new_name, cached_result)
que usa LinkedProject para encontrar todas as ocorrencias de um codigo ou bibref
em todos os arquivos do workspace e gera um WorkspaceEdit com TextEdits.
Para codigos: buscar em code_usage (todos os ItemNodes) + ontology_index.
Para bibrefs: buscar em sources (SourceNode + ItemNodes com mesmo bibref).
Registre TEXT_DOCUMENT_RENAME e TEXT_DOCUMENT_PREPARE_RENAME em server.py.
Este step requer cuidado especial com manipulacao de arquivos e integridade referencial.
```

---

## Verificacao Final

Apos implementar todos os steps, executar:

```bash
# 1. Testes unitarios
pytest tests/ -v

# 2. Verificar que o servidor inicia sem erro
python -m synesis_lsp

# 3. Teste manual com o projeto Davi
#    - Abrir Davi_Projeto_Completo/ no VSCode
#    - Verificar diagnostics, hover, completion, symbols
```
