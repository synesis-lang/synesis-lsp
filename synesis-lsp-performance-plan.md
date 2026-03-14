# Synesis-LSP — Estudo de Performance Baseado em Pyright

> **Objetivo:** Identificar os pontos de maior impacto para melhorar a performance do synesis-lsp em arquivos grandes, propor refatorações concretas baseadas em padrões do Pyright, e organizar a implementação em fases seguras e verificáveis.

> **Restrição de estilo:** O synesis-lsp segue prioritariamente o estilo **procedural** do compilador Synesis. Usar funções puras para lógica de negócio, dicts/dataclasses leves para estado, e módulos simples. A classe `SynesisLanguageServer` é a **única exceção** (herda de `pygls.LanguageServer` por exigência do framework) — estado adicionado a ela deve ser mínimo (dicts simples, não sub-objetos complexos). Funções de validação, cache e providers são módulo-level, não métodos de classe.

> **Dependência do compilador:** Este plano coordena com o [synesis-performance-plan.md](../synesis/synesis-performance-plan.md) do compilador. A Fase 1 do compilador (criação de `synesis.ast.normalize.normalize_code`) é **pré-requisito** para a consolidação das 7 cópias de `_normalize_code` no LSP. A Fase 5 do compilador (parse_cache) requer coordenação com a invalidação de cache do LSP.

---

## Sumário Executivo

O synesis-lsp atual recompila o arquivo inteiro a cada keystroke (`did_change` → `validate_single_file`), revalida **todos** os documentos abertos quando um arquivo de contexto é salvo, e não cacheia resultados de providers (symbols, semantic tokens, explorer requests). Este estudo analisa a arquitetura de performance do Pyright e propõe **7 otimizações** organizadas em fases independentes que, combinadas, reduzem o trabalho redundante em **~80-90%** sem quebrar funcionalidade existente.

---

## PARTE I — Arquitetura do Pyright (Referência)

### 1.1 Visão Geral

O Pyright é um LSP de alta performance para Python, escrito em TypeScript. Sua arquitetura é construída sobre quatro pilares:

| Pilar | Mecanismo | Arquivo-Chave |
|-------|-----------|---------------|
| **Lazy Evaluation** | Tipos computados on-demand, cacheados por node ID | `analyzer/typeEvaluator.ts`, `analyzer/typeCacheUtils.ts` |
| **Incremental Analysis** | Dirty flags por arquivo, propagação via grafo de dependências | `analyzer/sourceFile.ts`, `analyzer/program.ts` |
| **Time-Sliced Execution** | `analyze(maxTime)` com budget de 50ms para arquivos abertos | `analyzer/program.ts`, `analyzer/service.ts` |
| **Cancellation** | Tokens de cancelamento verificados em checkpoints | `common/cancellationUtils.ts` |

### 1.2 Lazy Evaluation (typeEvaluator.ts, typeCacheUtils.ts)

**Padrão central:** Tipos nunca são computados proativamente. O avaliador usa `readTypeCache(nodeId)` para verificar se o tipo já foi computado. Se não, computa e armazena via `writeTypeCache(nodeId, type)`.

```
// Pseudocódigo do padrão Pyright
function getTypeOfExpression(node):
    cached = readTypeCache(node.id)
    if cached != undefined:
        return cached        // ← cache hit, zero custo

    type = evaluateExpression(node)   // ← computação real
    writeTypeCache(node.id, type)
    return type
```

**`SpeculativeTypeTracker`** (typeCacheUtils.ts): Gerencia até 8 resultados por nó em diferentes contextos (expected type, dependent type). Limpa automaticamente quando o contexto sai de escopo.

**Aplicação ao synesis-lsp:** O compilador Synesis é externo (pacote `synesis`), então não é possível implementar lazy evaluation interna. Mas o **padrão de cache por resultado** pode ser aplicado nos providers LSP (symbols, semantic tokens, hover, etc.).

### 1.3 Incremental Analysis (sourceFile.ts, program.ts)

**Dirty flags por arquivo** (sourceFile.ts `WriteableData`):

```typescript
class WriteableData {
    isBindingNeeded: boolean      // precisa re-binding?
    isCheckingNeeded: boolean     // precisa re-checking?
    fileContentsVersion: number   // incrementado a cada mudança de conteúdo
    analyzedFileContentsVersion: number  // versão da última análise completa
    diagnosticVersion: number     // incrementado quando diagnósticos mudam
}
```

**Propagação de dirty** (program.ts): Quando um arquivo muda, `_markFileDirtyRecursive()` propaga o dirty flag para todos os arquivos que importam dele, via grafo de dependências. Arquivos não afetados **não são reanalisados**.

**Aplicação ao synesis-lsp:** O ecossistema Synesis tem um grafo de dependências simples: `.syn`/`.syno` dependem de `.synt` (template) e `.bib` (bibliografia), orquestrados por `.synp`. Quando `.synt` muda, todos os `.syn` são afetados. Quando apenas um `.syn` muda, os outros **não precisam ser revalidados**.

### 1.4 Time-Sliced Execution (program.ts, service.ts)

```typescript
// program.ts — analyze() com budget de tempo
analyze(maxTime: MaxAnalysisTime): boolean {
    // Budget: 50ms para arquivos abertos, 200ms para background
    const budget = isCheckingOnlyOpenFiles()
        ? maxTime.openFilesTimeInMs    // 50ms
        : maxTime.noOpenFilesTimeInMs  // 200ms

    for (file of filesToAnalyze) {
        if (elapsedTime > budget) return true  // "mais trabalho pendente"
        analyzeFile(file)
    }
    return false  // "tudo feito"
}
```

**`scheduleReanalysis`** (service.ts): Debounce com backoff baseado em atividade do usuário. Quando o usuário está digitando, a análise é adiada. Usa `setTimeout` com mínimo de 5ms entre passes.

**Aplicação ao synesis-lsp:** A validação individual de arquivo no Synesis é rápida (3-69ms), então time-slicing dentro de um arquivo não é necessário. Mas o padrão de **priorizar o arquivo ativo** e adiar revalidação de outros arquivos é diretamente aplicável.

### 1.5 Cancellation (cancellationUtils.ts)

```typescript
// Verificação lightweight espalhada pelo analyzer
function throwIfCancellationRequested(token: CancellationToken) {
    if (token.isCancellationRequested) {
        throw new OperationCanceledException()
    }
}

// Cancelamento baseado em arquivo (para worker threads)
class FileBasedToken {
    // Verifica existência de arquivo de cancelamento a cada 5ms
    isCancellationRequested: boolean
}
```

**Aplicação ao synesis-lsp:** O compilador Synesis é uma chamada síncrona que não suporta cancelamento interno. Porém, o cancelamento pode ser aplicado **entre etapas** do pipeline de validação (após `validate_single_file`, antes de `build_template_diagnostics`, etc.).

### 1.6 Background Analysis (backgroundAnalysis.ts, backgroundAnalysisBase.ts)

O Pyright usa **Worker Threads** para executar análise em background. O thread principal permanece responsivo para requests LSP (hover, completion, etc.) enquanto o worker processa análise pesada.

**Aplicação ao synesis-lsp:** Python tem `asyncio` + `concurrent.futures.ThreadPoolExecutor`. A compilação completa do projeto (`load_project`, ~3.7s) é candidata ideal para execução em thread separada.

### 1.7 Arquivos-Chave do Pyright para Referência

| Arquivo | Localização | O que adaptar |
|---------|-------------|---------------|
| **sourceFile.ts** | `LSP_Study/pyright/packages/pyright-internal/src/analyzer/sourceFile.ts` | Dirty flags (`WriteableData`), `fileContentsVersion` vs `analyzedFileContentsVersion` |
| **program.ts** | `LSP_Study/pyright/packages/pyright-internal/src/analyzer/program.ts` | `analyze(maxTime)`, `_markFileDirtyRecursive()`, priorização de arquivos abertos |
| **service.ts** | `LSP_Study/pyright/packages/pyright-internal/src/analyzer/service.ts` | `scheduleReanalysis`, debounce com backoff, `checkOnlyOpenFiles` |
| **typeCacheUtils.ts** | `LSP_Study/pyright/packages/pyright-internal/src/analyzer/typeCacheUtils.ts` | `SpeculativeTypeTracker`, cache multi-nível por node ID |
| **cancellationUtils.ts** | `LSP_Study/pyright/packages/pyright-internal/src/common/cancellationUtils.ts` | `throwIfCancellationRequested`, `CancelAfter` |
| **cacheManager.ts** | `LSP_Study/pyright/packages/pyright-internal/src/analyzer/cacheManager.ts` | Monitoramento de heap, `emptyCache()` sob pressão de memória |
| **backgroundAnalysisBase.ts** | `LSP_Study/pyright/packages/pyright-internal/src/backgroundAnalysisBase.ts` | Worker thread para análise, `MessagePort` para comunicação |
| **languageServerBase.ts** | `LSP_Study/pyright/packages/pyright-internal/src/languageServerBase.ts` | Handlers `onDidOpen/Change/Save`, pull diagnostics (LSP 3.17) |

---

## PARTE II — Diagnóstico do Synesis-LSP Atual

### 2.1 Mapeamento de Bottlenecks

Abaixo, os **7 pontos críticos** identificados no código atual, ordenados por impacto:

#### Bottleneck #1: Sem Debounce no `did_change` (IMPACTO: CRÍTICO)

**Arquivo:** `synesis_lsp/server.py`, linhas 1201-1212

```python
@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params):
    validate_document(ls, params.text_document.uri)  # ← chamado a CADA keystroke
```

**Problema:** Cada keystroke dispara `validate_single_file()` que faz parsing completo (3-69ms). Ao digitar 10 caracteres rapidamente, são 10 compilações seriais onde apenas a última importa.

**Nota no código (linha 1209):** O próprio desenvolvedor já documentou que pygls 1.0+ suporta debounce nativo via `@server.feature(TEXT_DOCUMENT_DID_CHANGE, debounce=0.3)`.

**Desperdício estimado:** ~80% do CPU durante digitação ativa.

---

#### Bottleneck #2: Revalidação de TODOS os documentos ao salvar contexto (IMPACTO: ALTO)

**Arquivo:** `synesis_lsp/server.py`, linhas 1295-1369

```python
@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params):
    if file_extension in [".synp", ".synt"]:
        # ...
        for doc_uri in documents_to_revalidate:     # ← TODOS os docs abertos
            validate_document(ls, doc_uri)           # ← compilação completa cada
```

**Problema:** Se 5 arquivos `.syn` estão abertos e o `.synt` é salvo, são 5 compilações síncronas (~5×50ms = 250ms bloqueando o thread principal). O usuário só está olhando para um arquivo.

**Mesmo padrão em:** `did_change_watched_files` (linha 1380), `did_change_configuration` (linha 1236).

---

#### Bottleneck #3: Fingerprint pesado via `os.walk` + SHA1 (IMPACTO: MÉDIO)

**Arquivo:** `synesis_lsp/server.py`, linhas 256-285

```python
def _compute_workspace_fingerprint(root: Path) -> str:
    for dirpath, dirnames, filenames in os.walk(root_path):  # ← percorre toda a árvore
        for name in filenames:
            stat = file_path.stat()                           # ← stat() por arquivo
            payload = f"{rel}|{stat.st_mtime_ns}|{stat.st_size}"
            hasher.update(payload.encode("utf-8"))            # ← SHA1 incremental
    return hasher.hexdigest()
```

**Problema:** Executado a cada `synesis/loadProject`. Para workspaces com centenas de arquivos, o `os.walk` + `stat()` pode levar 50-200ms antes mesmo de verificar se o cache é válido.

---

#### Bottleneck #4: Symbols e Semantic Tokens sem cache (IMPACTO: MÉDIO)

**Arquivos:** `synesis_lsp/symbols.py`, `synesis_lsp/semantic_tokens.py`

- `compute_document_symbols()` chama `compile_string()` (compilação completa) em cada request
- `compute_semantic_tokens()` faz scan regex do arquivo inteiro em cada render
- Nenhum dos dois cacheia resultados — recomputam mesmo se o conteúdo não mudou

**Chamados quando:** `did_open`, scroll, outline panel refresh, etc.

---

#### Bottleneck #5: Explorer requests computam tudo eagerly (IMPACTO: MÉDIO)

**Arquivo:** `synesis_lsp/explorer_requests.py`

- `get_codes()` itera **todos** os sources, items e `code_locations` para construir ocorrências
- `_build_code_occurrences()` faz loop aninhado: para cada código × cada item × cada field
- Resultado não é cacheado entre chamadas (cache LRU existe apenas para `get_relations`)

**Tempo:** 100-200ms para projetos com 100+ códigos.

---

#### Bottleneck #6: Filtro de ontology annotations pós-computação (IMPACTO: BAIXO-MÉDIO)

**Arquivo:** `synesis_lsp/ontology_annotations.py`

- `get_ontology_annotations()` computa **todas** as anotações do projeto inteiro
- Só depois filtra por `active_file` (se fornecido)
- `_merge_code_usage_with_chains()` itera todos os sources → items → chains

**Custo desnecessário:** Quando o Explorer mostra anotações para UM arquivo, computa para TODOS.

---

#### Bottleneck #7: Workspace Diagnostics sem incrementalidade (IMPACTO: BAIXO)

**Arquivo:** `synesis_lsp/workspace_diagnostics.py`

- `_find_synesis_files()` faz **4 chamadas separadas** de `rglob()` (uma por extensão)
- `compute_workspace_diagnostics()` valida **todos** os arquivos encontrados
- Sem tracking de quais arquivos mudaram desde a última validação

---

### 2.2 Fluxo Atual vs. Fluxo Ideal

```
FLUXO ATUAL (cada keystroke):
═══════════════════════════════════════════════════════════════
did_change
  → validate_document(uri)
    → validate_single_file(source, uri)     ← compilação completa (3-69ms)
    → build_diagnostics(result)             ← conversão (0ms)
    → build_template_diagnostics(...)       ← scan regex (2-5ms)
    → build_command_diagnostics(...)        ← lookup (0ms)
    → publish_diagnostics(uri, diags)       ← envio
  ← Total: 5-75ms POR KEYSTROKE

Salvar .synt com 5 arquivos abertos:
  → invalidate_cache
  → validate_document(uri_1)    ← 50ms
  → validate_document(uri_2)    ← 50ms
  → validate_document(uri_3)    ← 50ms
  → validate_document(uri_4)    ← 50ms
  → validate_document(uri_5)    ← 50ms
  ← Total: ~250ms BLOQUEANDO

═══════════════════════════════════════════════════════════════
FLUXO IDEAL (após otimizações):
═══════════════════════════════════════════════════════════════
did_change
  → cancel pending validation for URI (se existir)
  → schedule validation after 300ms debounce
  → [300ms depois, se sem novas mudanças]:
    → check FileState: content mudou? context mudou?
      → NÃO: republish cached diagnostics (0ms)
      → SIM: validate_single_file → cache result → publish
  ← Total: 0ms imediato, 5-75ms após debounce

Salvar .synt com 5 arquivos abertos:
  → invalidate context cache
  → bump context_version
  → validate focused document IMEDIATAMENTE     ← 50ms
  → schedule remaining 4 documents (deferred)   ← 0ms bloqueio
  → [background, yield entre cada]:
    → validate_document(uri_2)    ← 50ms
    → yield
    → validate_document(uri_3)    ← 50ms
    → yield  ...
  ← Total bloqueante: ~50ms (apenas arquivo ativo)
```

---

## PARTE III — Otimizações em Fases Independentes

### Fase 0: Consolidação de `_normalize_code` (Coordenada com Compilador)

> **Impacto:** BAIXO (performance) + ALTO (manutenibilidade) | **Risco:** MUITO BAIXO | **Esforço:** 30min
> **Pré-requisito:** Fase 1 do compilador (`synesis.ast.normalize.normalize_code`) concluída.

**O que:** Substituir as 7 cópias de `_normalize_code` nos módulos LSP por import de `synesis.ast.normalize.normalize_code`.

**Por que:** 9 implementações independentes da mesma lógica (2 no compilador + 7 no LSP) criam risco de divergência. Após a Fase 1 do compilador criar o módulo centralizado, o LSP deve consumi-lo.

**Módulos afetados (7 cópias a remover):**
- `synesis_lsp/explorer_requests.py:208`
- `synesis_lsp/hover.py:151`
- `synesis_lsp/graph.py:90`
- `synesis_lsp/rename.py:247`
- `synesis_lsp/references.py:202`
- `synesis_lsp/definition.py:80`
- `synesis_lsp/ontology_annotations.py:25`

**Como implementar:**
```python
# Em cada módulo acima, substituir:
#   def _normalize_code(code: str) -> str:
#       return " ".join(code.strip().split()).lower()
# Por:
from synesis.ast.normalize import normalize_code
# E substituir chamadas _normalize_code(x) → normalize_code(x)
```

**Verificação:**
1. `pytest tests/` passa
2. Buscar `def _normalize_code` no LSP — deve retornar 0 resultados
3. Testar getCodes, hover, rename, references, definition, ontology annotations — comportamento idêntico

---

### Fase 1: Debounce no `did_change` ⚡

> **Impacto:** CRÍTICO | **Risco:** BAIXO | **Esforço:** 1-2h

**O que:** Adiar validação por 300ms após último keystroke, cancelando timers pendentes.

**Por que:** Elimina ~80% das compilações redundantes durante digitação ativa.

**Padrão Pyright:** `service.ts` `scheduleReanalysis` — cancela timer anterior, agenda novo com backoff.

**Como implementar:**

```python
# server.py — Adicionar ao SynesisLanguageServer.__init__
class SynesisLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_documents: dict[str, set[str]] = {}
        self.validation_enabled: bool = True
        self.workspace_cache: WorkspaceCache = WorkspaceCache()
        # NOVO: debounce state
        self._pending_validations: dict[str, asyncio.TimerHandle] = {}
        self._validation_debounce_s: float = 0.3  # 300ms

# server.py — Modificar did_change
@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: SynesisLanguageServer, params: DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri

    # Cancelar validação pendente para este URI
    pending = ls._pending_validations.pop(uri, None)
    if pending is not None:
        pending.cancel()

    # Agendar nova validação com debounce
    loop = asyncio.get_event_loop()
    handle = loop.call_later(
        ls._validation_debounce_s,
        lambda: validate_document(ls, uri)
    )
    ls._pending_validations[uri] = handle

# did_open mantém validação imediata (ação explícita do usuário)
# did_save mantém validação imediata (ação explícita do usuário)
```

**Alternativa (pygls nativo):** Se pygls 1.0+ estiver disponível:
```python
@server.feature(TEXT_DOCUMENT_DID_CHANGE, debounce=0.3)
def did_change(ls, params):
    validate_document(ls, params.text_document.uri)
```

**Arquivos afetados:**
- `synesis_lsp/server.py` — `SynesisLanguageServer.__init__`, `did_change`

**Verificação:**
1. Abrir arquivo `.syn` grande
2. Digitar 10 caracteres rapidamente
3. Verificar logs: deve haver apenas 1-2 chamadas a `validate_document` (não 10)
4. Diagnósticos devem aparecer ~300ms após parar de digitar
5. Rodar `pytest tests/` — todos os testes devem passar

**O que NÃO pode quebrar:**
- `did_open` e `did_save` continuam com validação imediata
- Diagnósticos ainda aparecem (apenas com delay de 300ms)
- Nenhum handler existente é removido

---

### Fase 2: Dirty Flags e Cache de Validação por Arquivo 🏷️

> **Impacto:** ALTO | **Risco:** MÉDIO | **Esforço:** 2-3h

**O que:** Rastrear versão do conteúdo por arquivo e pular revalidação quando nada mudou.

**Por que:** Ao salvar `.synt`, os 5 arquivos `.syn` abertos são recompilados. Se apenas o `.synt` mudou (contexto), os `.syn` cujo conteúdo não mudou poderiam reutilizar diagnósticos cacheados — exceto que o contexto mudou. Com dirty flags, distinguimos: "conteúdo mudou" vs "apenas contexto mudou".

**Padrão Pyright:** `sourceFile.ts` `WriteableData` — `fileContentsVersion` vs `analyzedFileContentsVersion`.

**Como implementar:**

```python
# cache.py — Novo dataclass
@dataclass
class FileState:
    """Estado de validação por arquivo, inspirado em sourceFile.ts do Pyright."""
    content_hash: int = 0                   # hash do conteúdo atual
    validated_content_hash: int = -1         # hash do conteúdo na última validação
    context_version: int = 0                 # versão do contexto usado na validação
    last_diagnostics: list = field(default_factory=list)  # diagnósticos cacheados
    last_validation_result: object = None    # ValidationResult cacheado

# server.py — Adicionar ao SynesisLanguageServer
class SynesisLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ... existente ...
        # NOVO: per-file state
        self._file_states: dict[str, FileState] = {}
        self._context_versions: dict[str, int] = {}  # workspace_key → version

# server.py — Modificar validate_document
def validate_document(ls, uri):
    if not ls.validation_enabled:
        ls.publish_diagnostics(uri, [])
        return

    doc = ls.workspace.get_document(uri)
    source = doc.source
    content_hash = hash(source)

    # Obter ou criar FileState
    state = ls._file_states.setdefault(uri, FileState())

    # Obter context_version do workspace
    workspace_root = _find_workspace_root(uri)
    workspace_key = _workspace_key(workspace_root) if workspace_root else ""
    ctx_version = ls._context_versions.get(workspace_key, 0)

    # SKIP se conteúdo E contexto não mudaram
    if (state.content_hash == content_hash
        and state.validated_content_hash == content_hash
        and state.context_version == ctx_version
        and state.last_diagnostics is not None):
        logger.debug(f"Cache hit para {uri}, republicando diagnósticos")
        ls.publish_diagnostics(uri, state.last_diagnostics)
        return

    # Compilação necessária
    result = validate_single_file(source, uri, context=None)
    diagnostics = build_diagnostics(result)
    # ... template diagnostics, command diagnostics ...

    # Atualizar FileState
    state.content_hash = content_hash
    state.validated_content_hash = content_hash
    state.context_version = ctx_version
    state.last_diagnostics = diagnostics
    state.last_validation_result = result

    ls.publish_diagnostics(uri, diagnostics)

# server.py — Em did_save para .synp/.synt/.bib, bumpar context_version
def did_save(ls, params):
    if file_extension in [".synp", ".synt"]:
        # ... invalidar caches ...
        workspace_key = _workspace_key(workspace_root)
        ls._context_versions[workspace_key] = ls._context_versions.get(workspace_key, 0) + 1

        # COORDENAÇÃO COM COMPILADOR (após Fase 5 do compilador):
        # Quando contexto muda (.synt/.synp), invalidar parse_cache do compilador
        # para que nós cacheados não sejam reutilizados com template desatualizado.
        # from synesis.parser.parse_cache import invalidate_cache
        # invalidate_cache()

        # Revalidar (agora com context_version novo, forçará recompilação)
        for doc_uri in documents_to_revalidate:
            validate_document(ls, doc_uri)
```

**Ganho principal:** Quando um `.syn` é salvo (sem mudar `.synt`), se 3 outros `.syn` estão abertos, eles **não são recompilados** (content e context não mudaram).

**Arquivos afetados:**
- `synesis_lsp/cache.py` — novo `FileState`
- `synesis_lsp/server.py` — `SynesisLanguageServer.__init__`, `validate_document`, `did_save`, `did_change_watched_files`

**Verificação:**
1. Abrir 3 arquivos `.syn`. Salvar um deles sem mudanças → logs devem mostrar "Cache hit" para os outros 2
2. Modificar `.synt` e salvar → todos os 3 devem ser revalidados (context_version mudou)
3. `pytest tests/` passa

**O que NÃO pode quebrar:**
- Diagnósticos SEMPRE atualizados quando conteúdo ou contexto muda
- Primeira validação (sem cache) funciona normalmente
- `did_close` limpa `FileState` para evitar memory leak

---

### Fase 3: Fingerprint Leve com mtime-max 🔑

> **Impacto:** MÉDIO | **Risco:** MUITO BAIXO | **Esforço:** 30min

**O que:** Substituir SHA1 directory walk por verificação rápida de mtime máximo.

**Por que:** `_compute_workspace_fingerprint` faz `os.walk` + `stat()` + SHA1 em toda a árvore. Para decidir se o cache é válido, basta saber se algum arquivo mudou (mtime diferente).

**Padrão Pyright:** File watchers incrementais em vez de scans periódicos.

**Como implementar:**

```python
# server.py — Substituir _compute_workspace_fingerprint
def _compute_workspace_fingerprint(root: Path) -> str:
    """Fingerprint rápido baseado em max(mtime) + contagem de arquivos."""
    exts = {".synp", ".syn", ".syno", ".synt", ".bib"}
    max_mtime = 0
    file_count = 0

    root_path = root if root.is_dir() else root.parent

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames.sort()
        for name in filenames:
            if Path(name).suffix.lower() not in exts:
                continue
            file_count += 1
            try:
                mtime = os.path.getmtime(os.path.join(dirpath, name))
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                continue

    return f"{file_count}:{max_mtime}"
```

**Ganho:** Elimina construção de string + SHA1 por arquivo. O `os.walk` ainda ocorre, mas o custo por arquivo cai de ~3 operações (stat + string format + SHA1 update) para ~1 (getmtime).

**Melhoria futura (Fase 3b):** Cachear a lista de arquivos na primeira chamada e apenas re-stat os conhecidos nas chamadas subsequentes, eliminando o `os.walk`.

**Arquivos afetados:**
- `synesis_lsp/server.py` — `_compute_workspace_fingerprint`

**Verificação:**
1. Medir tempo de `synesis/loadProject` antes e depois
2. Salvar um `.syn` → fingerprint deve mudar → cache invalidado → recompilação
3. Chamar `loadProject` novamente sem mudanças → fingerprint igual → cache hit

---

### Fase 4: Cache de Providers (Symbols, Semantic Tokens, Explorer) 📦

> **Impacto:** MÉDIO | **Risco:** BAIXO | **Esforço:** 2-3h

**O que:** Cachear resultados de `compute_document_symbols`, `compute_semantic_tokens`, `get_codes`, e `get_ontology_annotations` por hash do conteúdo/compilação.

**Por que:** Estes providers recomputam tudo em cada request mesmo quando o conteúdo não mudou. `compute_document_symbols` chama `compile_string()` a cada abertura do outline.

**Padrão Pyright:** `readTypeCache(nodeId)` / `writeTypeCache(nodeId, type)` — compute-on-demand com cache.

**Como implementar:**

```python
# symbols.py — Adicionar cache por (uri, content_hash)
_symbols_cache: dict[tuple[str, int], list] = {}

def compute_document_symbols(uri, source, ...):
    cache_key = (uri, hash(source))
    if cache_key in _symbols_cache:
        return _symbols_cache[cache_key]

    # ... computação existente ...
    result = [...]

    _symbols_cache.clear()  # manter apenas último resultado por URI
    _symbols_cache[cache_key] = result
    return result

# semantic_tokens.py — Mesmo padrão
_tokens_cache: dict[tuple[str, int], SemanticTokens] = {}

def compute_semantic_tokens(source, uri, ...):
    cache_key = (uri, hash(source))
    if cache_key in _tokens_cache:
        return _tokens_cache[cache_key]
    # ... computação existente ...

# explorer_requests.py — Formalizar cache de getCodes
# (get_relations e get_ontology_annotations já têm LRU cache)
_codes_cache: dict[tuple, list] = {}

def get_codes(cached_result, workspace_root, ...):
    if cached_result is None:
        return _build_empty_codes()
    cache_key = (id(cached_result.result), cached_result.timestamp)
    if cache_key in _codes_cache:
        return _codes_cache[cache_key]
    # ... computação existente ...
    _codes_cache.clear()
    _codes_cache[cache_key] = result
    return result
```

**Arquivos afetados:**
- `synesis_lsp/symbols.py` — cache por (uri, content_hash)
- `synesis_lsp/semantic_tokens.py` — cache por (uri, content_hash)
- `synesis_lsp/explorer_requests.py` — cache para `get_codes` (mesmo padrão de `_RELATIONS_CACHE`)

**Verificação:**
1. Abrir arquivo `.syn`, abrir Outline (symbols) → logs mostram "computado"
2. Mudar para outro arquivo e voltar → logs mostram "cache hit"
3. Editar o arquivo → logs mostram "recomputado" (hash mudou)
4. `pytest tests/` passa

---

### Fase 5: Revalidação Deferida de Documentos Não-Focados 🔄

> **Impacto:** MÉDIO | **Risco:** BAIXO | **Esforço:** 1-2h

**O que:** Ao salvar arquivo de contexto, validar apenas o documento ativo imediatamente. Agendar os demais para validação background com yield points.

**Por que:** O usuário está olhando para um arquivo. Os 4 outros abertos podem esperar 1-2 segundos sem impacto percebido.

**Padrão Pyright:** `program.ts` `analyze()` prioriza `openFiles` com budget curto, processa restantes com budget maior.

**Como implementar:**

```python
# server.py — Novo atributo e helper
class SynesisLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ... existente ...
        self._last_focused_uri: Optional[str] = None

@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params):
    ls._last_focused_uri = params.text_document.uri
    # ... debounce ...

@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params):
    ls._last_focused_uri = params.text_document.uri
    validate_document(ls, params.text_document.uri)

# server.py — Revalidação deferida em did_save
async def _revalidate_workspace_deferred(ls, workspace_key, focused_uri):
    """Revalida arquivo focado imediatamente, demais com yield."""
    docs = list(ls.workspace_documents.get(workspace_key, set()))

    # 1. Arquivo focado primeiro (imediato)
    if focused_uri and focused_uri in docs:
        validate_document(ls, focused_uri)
        docs.remove(focused_uri)

    # 2. Demais com yield entre cada um
    for doc_uri in docs:
        await asyncio.sleep(0)  # yield para processar LSP requests
        try:
            validate_document(ls, doc_uri)
        except Exception as e:
            logger.error(f"Erro ao revalidar {doc_uri}: {e}", exc_info=True)

# Modificar did_save para usar versão deferida
@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls, params):
    if file_extension in [".synp", ".synt"]:
        # ... invalidar caches (existente) ...
        # MUDANÇA: usar revalidação deferida
        asyncio.ensure_future(
            _revalidate_workspace_deferred(ls, workspace_key, ls._last_focused_uri)
        )
```

**Arquivos afetados:**
- `synesis_lsp/server.py` — `SynesisLanguageServer.__init__`, `did_change`, `did_open`, `did_save`, `did_change_watched_files`, nova `_revalidate_workspace_deferred`

**Verificação:**
1. Abrir 5 arquivos `.syn`. Salvar `.synt`
2. Arquivo ativo deve mostrar diagnósticos atualizados imediatamente (~50ms)
3. Outros arquivos devem atualizar em sequência (~50ms cada, com responsividade entre eles)
4. Durante revalidação, hover e completion devem responder normalmente

---

### Fase 6: Cancelamento de Validação em Progresso ❌

> **Impacto:** MÉDIO | **Risco:** MÉDIO | **Esforço:** 1-2h

**O que:** Ao receber novo `did_change` para um URI, cancelar validação em andamento para esse URI.

**Por que:** Combina com debounce (Fase 1) para evitar trabalho desperdiçado. Sem cancelamento, uma validação que levou >300ms ainda roda até o fim mesmo que o conteúdo já mudou novamente.

**Padrão Pyright:** `service.ts` `_backgroundAnalysisCancellationSource?.cancel()` ao início de `scheduleReanalysis`.

**Como implementar:**

```python
# server.py
class SynesisLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ... existente ...
        self._validation_tasks: dict[str, asyncio.Task] = {}

async def _validate_document_async(ls, uri):
    """Versão async de validate_document com checkpoints de cancelamento."""
    try:
        doc = ls.workspace.get_document(uri)
        source = doc.source

        # Checkpoint 1: antes da compilação
        await asyncio.sleep(0)  # yield point

        result = validate_single_file(source, uri, context=None)

        # Checkpoint 2: antes de construir diagnósticos
        await asyncio.sleep(0)

        diagnostics = build_diagnostics(result)
        # ... template diagnostics, command diagnostics ...

        # Checkpoint 3: antes de publicar
        await asyncio.sleep(0)

        ls.publish_diagnostics(uri, diagnostics)

    except asyncio.CancelledError:
        logger.debug(f"Validação cancelada para {uri}")
        raise
    except Exception as e:
        logger.error(f"Erro na validação de {uri}: {e}", exc_info=True)

def _schedule_validation(ls, uri):
    """Agenda validação com cancelamento da anterior."""
    # Cancelar task anterior para este URI
    old_task = ls._validation_tasks.pop(uri, None)
    if old_task and not old_task.done():
        old_task.cancel()

    # Criar nova task
    task = asyncio.ensure_future(_validate_document_async(ls, uri))
    ls._validation_tasks[uri] = task
```

**Limitação:** `validate_single_file` é síncrono (chamada ao compilador externo). O cancelamento só funciona **entre** as etapas (após compilação, antes de build_diagnostics). Para cancelar a compilação em si, seria necessário executá-la em thread separada via `run_in_executor`.

**Arquivos afetados:**
- `synesis_lsp/server.py` — `SynesisLanguageServer.__init__`, nova `_validate_document_async`, nova `_schedule_validation`, modificar `did_change`

**Verificação:**
1. Adicionar `time.sleep(0.5)` temporário antes de `validate_single_file` para simular compilação lenta
2. Digitar rapidamente → logs devem mostrar "Validação cancelada para {uri}" seguido de validação final completa
3. Remover `time.sleep` e rodar `pytest tests/`

---

### Fase 7: Pre-filtro de Ontology Annotations por Arquivo Ativo 🎯

> **Impacto:** BAIXO-MÉDIO | **Risco:** BAIXO | **Esforço:** 1h

**O que:** Quando `get_ontology_annotations` recebe `active_file`, filtrar sources/items ANTES de iterar chains.

**Por que:** Atualmente, `_merge_code_usage_with_chains` itera todos os sources, todos os items, todos os chains do projeto inteiro. Depois filtra por `active_file`. Para projetos grandes, o loop completo pode levar 50-200ms quando bastaria ~5ms.

**Como implementar:**

```python
# ontology_annotations.py — Modificar _merge_code_usage_with_chains
def _merge_code_usage_with_chains(
    linked_project, code_usage, active_file=None
):
    """Merge code_usage com chains, com pre-filtro opcional por arquivo."""
    merged = dict(code_usage)

    for source in linked_project.sources:
        # PRE-FILTRO: se active_file especificado, pular sources de outros arquivos
        if active_file and hasattr(source, 'location'):
            source_file = getattr(source.location, 'file', None)
            if source_file and _normalize_path(source_file) != _normalize_path(active_file):
                continue

        for item in source.items:
            # ... iteração existente sobre chains ...
```

**Arquivos afetados:**
- `synesis_lsp/ontology_annotations.py` — `_merge_code_usage_with_chains`, `get_ontology_annotations`

**Verificação:**
1. Abrir projeto com 10+ sources. Verificar que ontology annotations para arquivo ativo aparecem corretamente
2. Medir tempo com e sem `active_file` — com filtro deve ser significativamente mais rápido
3. Verificar que sem `active_file`, o comportamento é idêntico ao atual

---

## PARTE IV — Arquitetura Final Otimizada

```
┌──────────────────────────────────────────────────────────────────────┐
│                     SynesisLanguageServer                            │
│                                                                      │
│  ESTADO POR ARQUIVO (Fase 2):                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ _file_states: dict[str, FileState]                              │ │
│  │   FileState:                                                     │ │
│  │     content_hash        → hash do source atual                   │ │
│  │     validated_hash      → hash na última validação               │ │
│  │     context_version     → versão do contexto usado               │ │
│  │     last_diagnostics    → diagnósticos cacheados                 │ │
│  │     last_validation_result → resultado compilação cacheado       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  CONTROLE DE FLUXO (Fases 1, 5, 6):                                 │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ _pending_validations: dict[str, TimerHandle]  → debounce 300ms  │ │
│  │ _validation_tasks: dict[str, Task]            → cancelamento    │ │
│  │ _last_focused_uri: str                        → priorização     │ │
│  │ _context_versions: dict[str, int]             → dirty tracking  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  CACHE (existente + Fase 4):                                         │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ workspace_cache: WorkspaceCache → LinkedProject por workspace   │ │
│  │ _symbols_cache: dict → symbols por (uri, hash)                  │ │
│  │ _tokens_cache: dict → semantic tokens por (uri, hash)           │ │
│  │ _codes_cache: dict → getCodes por (compilation_id, timestamp)   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

                    FLUXO DE EVENTOS
                    ════════════════

did_change(uri, content)
    │
    ▼
┌───────────────────────────┐
│ 1. Cancel pending timer   │ ← Fase 1
│ 2. Cancel running task    │ ← Fase 6
│ 3. Schedule after 300ms   │ ← Fase 1
│ 4. Track _last_focused    │ ← Fase 5
└─────────┬─────────────────┘
          │ [300ms sem mudanças]
          ▼
┌───────────────────────────┐
│ Check FileState           │ ← Fase 2
│ content_hash == validated? │
│ context_version matches?  │
│  ┌─ SIM → republish cache│ (0ms)
│  └─ NÃO ↓                │
└─────────┬─────────────────┘
          ▼
┌───────────────────────────┐
│ validate_single_file()    │ ← Compilador externo (3-69ms)
│     ↓                     │
│ [Checkpoint: cancelled?]  │ ← Fase 6
│     ↓                     │
│ build_diagnostics()       │ (0ms)
│ build_template_diags()    │ (2-5ms)
│ build_command_diags()     │ (0ms)
│     ↓                     │
│ Update FileState cache    │ ← Fase 2
│ publish_diagnostics()     │
└───────────────────────────┘

did_save(.synt / .bib)
    │
    ▼
┌───────────────────────────────────────┐
│ 1. Invalidate workspace_cache        │
│ 2. Bump _context_versions[workspace] │ ← Fase 2
│ 3. Validate focused_uri IMMEDIATELY  │ ← Fase 5
│ 4. Schedule remaining docs (deferred)│ ← Fase 5
│    └─ yield between each validation  │
└───────────────────────────────────────┘

Explorer Request (getCodes, getRelations, etc.)
    │
    ▼
┌───────────────────────────────────────┐
│ Check provider cache                  │ ← Fase 4
│ (compilation_id, timestamp)           │
│  ┌─ HIT  → return cached  (0ms)     │
│  └─ MISS → compute, cache, return    │
└───────────────────────────────────────┘
```

---

## PARTE V — Ordem de Implementação e Dependências

```
Fase 0 (Normalize)          ─── DEPENDE de Fase 1 do compilador (synesis.ast.normalize)
                                  └─ Pode ser feita junto com Sprint 1 do compilador

Fase 1 (Debounce)           ─── independente ─── deploy primeiro
  │
  │  (opcional)
  ▼
Fase 6 (Cancelamento)       ─── potenciado pela Fase 1, mas independente

Fase 2 (Dirty Flags)        ─── independente
  │                              (após Fase 5 do compilador: coordenar parse_cache)
  │  (beneficia)
  ▼
Fase 5 (Revalidação Deferida) ─── usa _last_focused_uri e context_version da Fase 2

Fase 3 (Fingerprint Leve)   ─── totalmente independente

Fase 4 (Cache Providers)    ─── totalmente independente

Fase 7 (Pre-filtro Ontology) ─── totalmente independente
```

### Cronograma Sugerido

| Sprint | Fases | Foco | Esforço Total | Dependência Compilador |
|--------|-------|------|---------------|------------------------|
| **Sprint 0** | Fase 0 | Consolidar normalize (após compilador Fase 1) | ~30min | Compilador Fase 1 |
| **Sprint 1** | Fases 1 + 3 | Quick wins, risco mínimo | ~2h | Nenhuma |
| **Sprint 2** | Fases 2 + 4 | Cache inteligente | ~4-5h | Compilador Fase 5 (coordenação parse_cache) |
| **Sprint 3** | Fases 5 + 7 | Priorização e filtros | ~2-3h | Nenhuma |
| **Sprint 4** | Fase 6 | Cancelamento (mais complexo) | ~2h | Nenhuma |

### Impacto Cumulativo Estimado

| Cenário | Antes | Após Todas as Fases | Redução |
|---------|-------|---------------------|---------|
| Digitar 10 chars rapidamente | 10 compilações (500ms total) | 1 compilação após 300ms | **~90%** |
| Salvar `.synt` (5 docs abertos) | 5 compilações síncronas (250ms bloqueante) | 1 imediata + 4 deferred (~50ms bloqueante) | **~80%** |
| `loadProject` (cache válido) | Walk + SHA1 (100ms) + cache hit | Walk + mtime check (30ms) + cache hit | **~70%** |
| Explorer refresh (sem mudanças) | getCodes (150ms) + getRelations (50ms) | Cache hit (0ms) | **~99%** |
| Reabrir arquivo sem mudanças | Symbols + tokens recomputados (70ms) | Cache hit (0ms) | **~99%** |
| Ontology annotations (arquivo ativo) | Full project scan (100ms) | Filtered scan (10ms) | **~90%** |
| Manutenibilidade normalize_code | 9 cópias independentes | 1 função centralizada (compilador) | **9→1** |

---

## PARTE VI — Verificação End-to-End (Projetos Reais)

> **Projetos de teste:** Todos os testes usam projetos reais da pasta `case-studies/` (repositório irmão).
>
> | Projeto | Caminho | Escala | Uso no LSP |
> |---------|---------|--------|------------|
> | **Basic** | `case-studies/Basic/project.synp` | 1 source, 1 item, 2 ontologies | Smoke test rápido |
> | **AIDS Corpus** | `case-studies/Sociology/iramuteq_aids_corpus/aids_corpus.synp` | 5 sources, 5 items, 2 ontologies | Funcional pequeno |
> | **Social Acceptance** | `case-studies/Sociology/Social_Acceptance/social_acceptance.synp` | 484 sources, 1614 items, 1388 ontologies | Benchmark funcional + performance |
> | **Thompson** | `case-studies/Theology/Thompson_Chain_Reference/thompson_bible.synp` | 1 source, 15757 items, 1728 ontologies | Performance grande |
> | **Nave** | `case-studies/Theology/Nave_Topical_Concordance/nave.synp` | 1 source, 82826 items, 5317 ontologies | Stress test (489K linhas) |

### Testes de Regressão (obrigatório após cada fase)

```bash
# 1. Testes unitários existentes
cd synesis-lsp
pytest tests/ -v
```

#### Smoke Test — Basic

```
1. Abrir pasta case-studies/Basic/ como workspace no VSCode
2. Abrir annotations.syn
3. Verificar: diagnósticos aparecem (0 erros esperados)
4. Introduzir erro de sintaxe → diagnóstico aparece
5. Desfazer → diagnóstico desaparece
6. Hover sobre @smith2024 → tooltip com dados bibliográficos
7. Outline panel → symbols corretos (1 SOURCE, 1 ITEM)
```

#### Teste Funcional — Social Acceptance

```
1. Abrir pasta case-studies/Sociology/Social_Acceptance/ como workspace
2. Abrir social_acceptance.syn (18819 linhas)
3. Verificar: diagnósticos aparecem em tempo razoável (<5s)
4. Hover sobre código de ontologia → definição aparece
5. Ctrl+Click em código → go-to-definition no .syno (20819 linhas)
6. Renomear código → refactoring propaga para .syn e .syno
7. Outline panel → 484 SOURCEs, 1614 ITEMs listados
```

#### Teste de Explorer — Social Acceptance

```
1. Com Social Acceptance aberto no workspace:
2. synesis/loadProject → sucesso, retorna stats corretos
   - sources: 484, items: 1614, ontologies: 1388
3. getCodes → lista de códigos com ocorrências
   - Verificar que códigos têm localizações corretas (file + line)
4. getRelations → triples corretos (chains com relações semânticas)
5. getOntologyAnnotations → anotações por código no arquivo ativo
   - Mudar arquivo ativo → anotações atualizam corretamente
```

#### Stress Test — Nave

```
1. Abrir pasta case-studies/Theology/Nave_Topical_Concordance/ como workspace
2. Abrir nave.syn (489898 linhas)
3. Verificar: LSP NÃO dá timeout nem crash
4. Diagnósticos devem aparecer (pode levar >10s — aceitável para este volume)
5. synesis/loadProject → sucesso
   - sources: 1, items: 82826, ontologies: 5317
6. getCodes → lista de 5317 códigos
7. Scroll e hover devem responder sem travamento do editor
```

### Métricas de Performance (antes/depois)

```python
# Adicionar ao server.py temporariamente para medição
import time

_perf_log = []

def validate_document_instrumented(ls, uri):
    t0 = time.perf_counter()
    validate_document(ls, uri)
    elapsed = time.perf_counter() - t0
    _perf_log.append({"uri": uri, "time_ms": elapsed * 1000})
    logger.info(f"validate_document took {elapsed*1000:.1f}ms for {uri}")
```

#### Benchmark Template

```
| Projeto            | Linhas .syn | Items  | validate_document (ms) | loadProject (ms) |
|--------------------|-------------|--------|------------------------|-------------------|
| Basic              | 15          | 1      |                        |                   |
| AIDS Corpus        | 65          | 5      |                        |                   |
| Social Acceptance  | 18819       | 1614   |                        |                   |
| Thompson           | 78787       | 15757  |                        |                   |
| Nave               | 489898      | 82826  |                        |                   |
```

Medir **antes** de cada fase e **depois**. Registrar para comparação cumulativa.

### Checklist de Segurança por Fase

| Fase | Teste Crítico | Projeto de Teste | Indicador de Falha |
|------|---------------|------------------|-------------------|
| 0 | getCodes, hover, rename retornam mesmos resultados | Social Acceptance (1388 códigos) | Normalização divergente (import errado) |
| 1 | Diagnósticos aparecem após 300ms | Social Acceptance (digitar em 18K linhas) | Diagnósticos nunca aparecem (timer bug) |
| 2 | Diagnósticos atualizam ao editar | Thompson (15757 items, salvar .synt) | Diagnósticos ficam stale (dirty flag bug) |
| 3 | loadProject detecta mudanças | Social Acceptance (tocar .syn, reload) | Cache nunca invalida (fingerprint bug) |
| 4 | Symbols mudam ao editar | Social Acceptance (editar, verificar outline) | Symbols ficam congelados (cache key errada) |
| 5 | Todos os docs atualizam após salvar .synt | Social Acceptance (3+ .syn abertos) | Docs não-focados nunca atualizam (deferred bug) |
| 6 | Validação final sempre completa | Thompson (digitar rápido em 78K linhas) | Diagnósticos desaparecem (cancel excessivo) |
| 7 | Anotações mostram dados corretos | Social Acceptance (filtro por arquivo ativo) | Anotações missing (filtro agressivo demais) |

---

*Documento gerado em: 2026-03-13*
*Baseado em: Pyright (LSP_Study/) + synesis-lsp v0.14.15*
*Referências: Pyright sourceFile.ts, program.ts, service.ts, cancellationUtils.ts, cacheManager.ts*
