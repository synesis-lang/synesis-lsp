# Plano de Implementação - Synesis LSP v0.11.x

**Data de criação**: 2026-02-02
**Versão base**: v0.10.4
**Objetivo**: Eliminar completamente o fallback para regex local na extensão VSCode

---

## 📊 Análise da Situação Atual

### Código Base Existente

✅ **Já Implementado**:
- `explorer_requests.py`: getCodes, getReferences, getRelations com suporte parcial
- `graph.py`: getRelationGraph com filtro por bibref (mas com bugs)
- `template_diagnostics.py`: Validação de campos baseada em template
- Cache de workspace (`cache.py`)
- Semantic tokens, symbols, hover, completion, definition, inlay hints, signature help, rename

⚠️ **Parcialmente Implementado** (precisa de correções):
- `synesis/getCodes`: Retorna codes mas **falta occurrences** detalhadas
- `synesis/getRelations`: Retorna triples mas **falta location e type**
- `synesis/getRelationGraph`: Filtro por bibref **retorna vazio** (bug)
- `textDocument/publishDiagnostics`: template_diagnostics existe mas **não está integrado** ao fluxo de validação

❌ **Não Implementado**:
- `synesis/getOntologyTopics`: Endpoint não existe
- `synesis/getOntologyAnnotations`: Endpoint não existe
- `synesis/getAbstract`: Endpoint não existe

---

## 🎯 Objetivos por Fase

### **FASE 1: CRÍTICO** (Alta Prioridade)
**Meta**: Eliminar fallbacks em Code Explorer, Relation Explorer e Graph Viewer
**Prazo estimado**: Sprint de 1-2 semanas
**Impacto**: Funcionalidades críticas da extensão operarão 100% via LSP

### **FASE 2: COMPLETUDE** (Prioridade Média)
**Meta**: Eliminar toda dependência de regex local
**Prazo estimado**: Sprint de 2-3 semanas
**Impacto**: Todos explorers funcionarão via LSP, código regex removido

### **FASE 3: EXCELÊNCIA** (Nice to Have)
**Meta**: Recursos LSP avançados para paridade com IDEs modernos
**Prazo estimado**: Sprint de 3-4 semanas
**Impacto**: Experiência de desenvolvimento de classe mundial

---

## 📋 FASE 1: IMPLEMENTAÇÕES CRÍTICAS

### Task 1.1: Fix `synesis/getCodes` - Adicionar Occurrences ⚡

**Arquivo**: [explorer_requests.py](synesis_lsp/explorer_requests.py)
**Status Atual**: ⚠️ Parcialmente implementado (retorna codes sem occurrences detalhadas)
**Prioridade**: 🔴 **CRÍTICA**

#### Problema Identificado

A função `get_codes()` já retorna occurrences (linhas 293-353), mas segundo o documento de fixes, a extensão ainda usa fallback. Isso indica que:
1. As occurrences podem não estar no formato correto
2. Pode haver bug na detecção de posição exata (line/column)
3. O campo `context` pode não estar diferenciando corretamente "code" vs "chain"

#### Solução Proposta

**Arquivo a modificar**: `synesis_lsp/explorer_requests.py`

**Alterações necessárias**:

1. **Melhorar `_build_code_occurrences()` (linhas 293-353)**:
   ```python
   def _build_code_occurrences(code, items, field_specs, workspace_root: Optional[Path]) -> list[dict]:
       """
       MELHORIAS:
       1. Calcular posição EXATA dentro do campo (não apenas location do ITEM)
       2. Garantir que context seja "code" quando aparece em CODE field
       3. Garantir que context seja "chain" quando aparece em CHAIN field
       4. Adicionar offset de linha/coluna baseado na posição dentro do campo
       """
   ```

2. **Adicionar helper para calcular posição exata**:
   ```python
   def _find_token_position_in_field(
       field_value: str,
       token: str,
       base_line: int,
       base_column: int
   ) -> list[tuple[int, int]]:
       """
       Retorna lista de (line, column) para cada ocorrência de token em field_value.
       Considera field_value multiline e calcula offset relativo a base_line/base_column.
       """
   ```

3. **Adicionar detecção de field_name precisa**:
   - Atualmente usa "CODE" como fallback (linha 333)
   - Deve rastrear o nome real do campo onde o code aparece

#### Critérios de Aceitação

✅ Response contém occurrences para cada code
✅ Cada occurrence tem: `file` (relativo), `line` (1-based), `column` (1-based)
✅ Campo `context` é "code" para CODE fields e "chain" para CHAIN fields
✅ Campo `field` contém nome exato do campo do template
✅ Posição aponta para o token exato, não apenas linha do ITEM
✅ Extensão VSCode não dispara fallback para `getCodes`

#### Testes

```python
# tests/test_explorer_requests.py

def test_get_codes_with_exact_positions(lsp_cache_with_project):
    """Valida que getCodes retorna posições exatas de cada code."""
    result = get_codes(lsp_cache_with_project)

    assert result["success"] is True
    assert len(result["codes"]) > 0

    code = result["codes"][0]
    assert "occurrences" in code
    assert len(code["occurrences"]) > 0

    occ = code["occurrences"][0]
    assert "file" in occ and isinstance(occ["file"], str)
    assert "line" in occ and isinstance(occ["line"], int) and occ["line"] > 0
    assert "column" in occ and isinstance(occ["column"], int) and occ["column"] > 0
    assert occ["context"] in ["code", "chain"]
    assert "field" in occ and isinstance(occ["field"], str)

    # Validar que path é relativo
    assert not Path(occ["file"]).is_absolute()
```

---

### Task 1.2: Fix `synesis/getRelations` - Adicionar Location e Type ⚡

**Arquivo**: [explorer_requests.py](synesis_lsp/explorer_requests.py)
**Status Atual**: ⚠️ Parcialmente implementado (retorna relations sem location/type consistente)
**Prioridade**: 🔴 **CRÍTICA**

#### Problema Identificado

A função `get_relations()` (linhas 93-118) já tenta adicionar location/type via `_build_relation_index()`, mas segundo o documento:
- Algumas relations não têm location
- O campo `type` (qualified vs simple) pode estar ausente

#### Solução Proposta

**Arquivo a modificar**: `synesis_lsp/explorer_requests.py`

**Alterações necessárias**:

1. **Melhorar `_build_relation_index()` (linhas 419-430)**:
   ```python
   def _build_relation_index(lp, workspace_root: Optional[Path]) -> dict:
       """
       MELHORIAS:
       1. Garantir que TODOS os triples tenham location (rastrear até o item pai)
       2. Detectar type baseado no formato do chain:
          - "type::code1-rel-code2" → type="qualified"
          - "code1-rel-code2" → type="simple"
       3. Se chain não tem location própria, usar location do item pai
       """
   ```

2. **Adicionar `_detect_chain_type()`**:
   ```python
   def _detect_chain_type(chain_str: str) -> str:
       """
       Detecta se chain é "qualified" (tem ::) ou "simple".

       Exemplos:
         "causes::smoking-causes-cancer" → "qualified"
         "smoking-causes-cancer" → "simple"
       """
       if "::" in chain_str:
           return "qualified"
       return "simple"
   ```

3. **Melhorar `_index_chain()` (linhas 467-490)**:
   - Adicionar parsing do chain original (string) para detectar type
   - Garantir que location seja sempre preenchida (fallback para item location)

#### Critérios de Aceitação

✅ Todas relations têm campo `location` com file/line/column
✅ Todas relations têm campo `type` ("qualified" ou "simple")
✅ Location aponta para linha do triplet no CHAIN (não linha do ITEM)
✅ Paths são relativos ao workspaceRoot
✅ Extensão VSCode não dispara fallback para `getRelations`

#### Testes

```python
# tests/test_explorer_requests.py

def test_get_relations_with_location_and_type(lsp_cache_with_project):
    """Valida que getRelations retorna location e type para cada triplet."""
    result = get_relations(lsp_cache_with_project)

    assert result["success"] is True
    assert len(result["relations"]) > 0

    for rel in result["relations"]:
        assert "from" in rel and "relation" in rel and "to" in rel
        assert "location" in rel, f"Falta location em {rel}"
        assert "type" in rel, f"Falta type em {rel}"

        loc = rel["location"]
        assert "file" in loc and isinstance(loc["file"], str)
        assert "line" in loc and isinstance(loc["line"], int)
        assert "column" in loc and isinstance(loc["column"], int)
        assert not Path(loc["file"]).is_absolute()

        assert rel["type"] in ["qualified", "simple"]
```

---

### Task 1.3: Fix `synesis/getRelationGraph` - Consertar Filtro por Bibref ⚡

**Arquivo**: [graph.py](synesis_lsp/graph.py)
**Status Atual**: ❌ **QUEBRADO** (retorna grafo vazio quando bibref fornecido)
**Prioridade**: 🔴 **CRÍTICA**

#### Problema Identificado

Segundo testes descritos no documento (LSP_last_fixes.md linhas 258-273):
- Sem bibref: funciona (mas retorna vazio se template não tem CODE)
- Com bibref: retorna vazio mesmo quando existem CHAINs

A função `_codes_for_bibref()` (linhas 92-121) tem dois branches:
1. Usa `code_usage` (linhas 96-107)
2. Fallback via `sources/items` (linhas 109-121)

O bug provavelmente está na normalização ou na busca do bibref nos items.

#### Solução Proposta

**Arquivo a modificar**: `synesis_lsp/graph.py`

**Alterações necessárias**:

1. **Melhorar `_codes_for_bibref()` (linhas 92-121)**:
   ```python
   def _codes_for_bibref(lp, bibref: str) -> set[str]:
       """
       MELHORIAS:
       1. Normalizar bibref (aceitar com/sem @)
       2. Debugar com logging se nenhum code foi encontrado
       3. Verificar se _item_bibref() está retornando corretamente
       4. Adicionar fallback robusto: verificar fields["BIBREF"] diretamente
       """
       normalized = _normalize_bibref(bibref)
       logger.debug(f"Buscando codes para bibref normalizado: '{normalized}'")

       # ... resto da implementação com logs ...
   ```

2. **Adicionar fallback adicional**:
   ```python
   # Se code_usage não retornar nada, verificar extra_fields["BIBREF"]
   for src in _iter_sources(sources):
       for item in getattr(src, "items", []) or []:
           # Verificar extra_fields.BIBREF diretamente
           extra_fields = getattr(item, "extra_fields", {}) or {}
           bibref_field = extra_fields.get("BIBREF", [])
           # ... comparar com normalized ...
   ```

3. **Adicionar validação de entrada**:
   ```python
   def get_relation_graph(cached_result, bibref: Optional[str] = None) -> dict:
       # Aceitar bibref com ou sem @
       if bibref:
           bibref = bibref.strip()
           if not bibref.startswith("@"):
               bibref = f"@{bibref}"
   ```

#### Critérios de Aceitação

✅ Sem bibref: retorna grafo completo
✅ Com bibref válido: retorna grafo filtrado (apenas relations dos codes desse bibref)
✅ Com bibref inexistente: retorna grafo vazio com success=true
✅ Aceita bibref com ou sem @ prefix
✅ Response tem campo `mermaid` ou `mermaidCode` (suportar ambos)
✅ Extensão VSCode não dispara fallback para `getRelationGraph`

#### Testes

```python
# tests/test_graph.py

def test_relation_graph_with_bibref_filter(lsp_cache_with_bibliometrics):
    """Valida que getRelationGraph filtra por bibref corretamente."""
    from synesis_lsp.graph import get_relation_graph

    # Teste sem filtro
    result_all = get_relation_graph(lsp_cache_with_bibliometrics, bibref=None)
    assert result_all["success"] is True
    mermaid_all = result_all.get("mermaidCode") or result_all.get("mermaid")
    assert mermaid_all and len(mermaid_all) > 0

    # Teste com filtro (assumindo @ashworth2019 existe no dataset)
    result_filtered = get_relation_graph(lsp_cache_with_bibliometrics, bibref="@ashworth2019")
    assert result_filtered["success"] is True
    mermaid_filtered = result_filtered.get("mermaidCode") or result_filtered.get("mermaid")
    assert mermaid_filtered and len(mermaid_filtered) > 0
    assert "graph LR" in mermaid_filtered

    # Teste com bibref sem @
    result_no_at = get_relation_graph(lsp_cache_with_bibliometrics, bibref="ashworth2019")
    assert result_no_at["success"] is True
    assert result_no_at.get("mermaidCode") or result_no_at.get("mermaid")

    # Teste com bibref inexistente
    result_invalid = get_relation_graph(lsp_cache_with_bibliometrics, bibref="@invalid9999")
    assert result_invalid["success"] is True
    assert result_invalid.get("mermaidCode") or result_invalid.get("mermaid")
```

---

### Task 1.4: Fix `textDocument/publishDiagnostics` - Integrar Validação de Template ⚡

**Arquivos**: [server.py](synesis_lsp/server.py), [template_diagnostics.py](synesis_lsp/template_diagnostics.py)
**Status Atual**: ⚠️ Módulo existe mas **não está integrado** ao fluxo de validação
**Prioridade**: 🔴 **CRÍTICA**

#### Problema Identificado

O módulo `template_diagnostics.py` existe e implementa validação de:
- Campos desconhecidos (linha 69)
- Campos com escopo errado (linha 74)
- Campos proibidos (linha 83)
- Campos obrigatórios faltando (linha 88)
- Bundles incompletos (linha 97)

Mas segundo o documento (LSP_last_fixes.md linhas 384-476), a validação **não está funcionando** - diagnostics não são publicados.

#### Solução Proposta

**Arquivo a modificar**: `synesis_lsp/server.py`

**Alterações necessárias**:

1. **Localizar handler de didOpen/didChange** (procurar no código):
   ```python
   @server.feature(TEXT_DOCUMENT_DID_OPEN)
   async def did_open(ls: SynesisLanguageServer, params: DidOpenTextDocumentParams):
       """Handler para textDocument/didOpen"""
       # Aqui deve chamar validação E template_diagnostics
   ```

2. **Integrar template_diagnostics no fluxo**:
   ```python
   # No handler de validação (_validate_document ou similar)

   # 1. Validação via compilador (já existe)
   diagnostics_from_compiler = build_diagnostics(validation_result)

   # 2. NOVO: Validação de template (complementar)
   template = None
   if workspace_cache and has_cache:
       cached = workspace_cache.get(workspace_key)
       if cached and cached.result:
           template = getattr(cached.result, "template", None)

   # 3. NOVO: Extrair campos já reportados pelo compilador
   existing_field_errors = _extract_field_errors(diagnostics_from_compiler)

   # 4. NOVO: Adicionar diagnostics de template
   if template:
       template_diags = build_template_diagnostics(
           source=source_text,
           uri=uri,
           template=template,
           existing_field_errors=existing_field_errors
       )
       diagnostics_from_compiler.extend(template_diags)

   # 5. Publicar diagnostics consolidados
   ls.publish_diagnostics(uri, diagnostics_from_compiler)
   ```

3. **Adicionar `_extract_field_errors()`**:
   ```python
   def _extract_field_errors(diagnostics: list[Diagnostic]) -> set[tuple[str, Optional[str]]]:
       """
       Extrai set de (field_name, block_type) dos diagnostics do compilador
       para evitar duplicar erros já reportados.
       """
       errors = set()
       for diag in diagnostics:
           # Parse da mensagem para extrair field_name
           # Exemplo: "Unknown field 'notes'" → ('notes', None)
           # ...
       return errors
   ```

#### Critérios de Aceitação

✅ Ao abrir arquivo `.syn` com campo inválido, diagnostic é publicado
✅ Ao editar e adicionar campo inválido, diagnostic aparece em tempo real
✅ Ao corrigir campo, diagnostic desaparece
✅ Campos obrigatórios faltando são reportados
✅ Bundles incompletos são reportados
✅ Diagnostics aparecem no Problems panel do VSCode
✅ Squiggly lines aparecem sob campos inválidos

#### Testes

```python
# tests/test_template_diagnostics.py (já existe, expandir)

def test_publish_diagnostics_for_invalid_field(lsp_client):
    """Valida que LSP publica diagnostics para campo inválido."""

    # Abrir documento com campo inválido
    uri = "file:///test/invalid_field.syn"
    source = """SOURCE: test
ITEM: item1
notes: this field is invalid
END
"""

    lsp_client.did_open(uri, source)

    # Aguardar e capturar diagnostics
    diagnostics = lsp_client.wait_for_diagnostics(uri, timeout=2.0)

    assert len(diagnostics) > 0
    assert any("notes" in d.message.lower() for d in diagnostics)
    assert any(d.severity == DiagnosticSeverity.Error for d in diagnostics)


def test_diagnostics_cleared_after_fix(lsp_client):
    """Valida que diagnostics somem após correção."""

    uri = "file:///test/fixed_field.syn"
    source_invalid = "ITEM: item1\ninvalid_field: value\nEND"
    source_valid = "ITEM: item1\nCODE: valid_code\nEND"

    lsp_client.did_open(uri, source_invalid)
    diagnostics = lsp_client.wait_for_diagnostics(uri)
    assert len(diagnostics) > 0

    lsp_client.did_change(uri, source_valid)
    diagnostics = lsp_client.wait_for_diagnostics(uri)
    assert len(diagnostics) == 0
```

---

## 📋 FASE 2: IMPLEMENTAÇÕES DE COMPLETUDE

### Task 2.1: Novo Endpoint `synesis/getOntologyTopics` 📦

**Arquivo a criar**: `synesis_lsp/ontology_topics.py`
**Status Atual**: ❌ Não existe
**Prioridade**: 🟡 **MÉDIA**

#### Requisito

Parsear arquivos `.syno` e retornar hierarquia de tópicos baseada em indentação.

#### Implementação Proposta

**Arquivo novo**: `synesis_lsp/ontology_topics.py`

```python
"""
ontology_topics.py - Extração de hierarquia de tópicos de arquivos .syno

Propósito:
    Parsear arquivos .syno respeitando indentação para construir
    árvore de conceitos hierárquica.

Custom Request:
    synesis/getOntologyTopics → Lista hierárquica de topics
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

def get_ontology_topics(cached_result) -> dict:
    """
    Retorna hierarquia de tópicos da ontologia.

    Returns:
        {
            "success": bool,
            "topics": [
                {
                    "name": str,
                    "level": int,
                    "file": str (relativo),
                    "line": int,
                    "children": [...]
                }
            ]
        }
    """
    pass  # Implementar


def _parse_syno_file(file_path: Path, workspace_root: Path) -> list[dict]:
    """
    Parseia arquivo .syno e extrai hierarquia.

    Indentação define nível (0, 1, 2...).
    Cada linha não vazia é um tópico.
    """
    pass  # Implementar
```

**Integração no servidor** (`server.py`):

```python
from synesis_lsp.ontology_topics import get_ontology_topics

@server.command("synesis/getOntologyTopics")
def ontology_topics_command(ls: SynesisLanguageServer, params) -> dict:
    """Retorna hierarquia de tópicos da ontologia."""
    workspace_root = _resolve_workspace_root(ls, params)
    if not workspace_root:
        return {"success": False, "error": "Workspace não encontrado"}

    ws_key = _workspace_key(workspace_root)
    cached = ls.workspace_cache.get(ws_key) if ws_key else None
    return get_ontology_topics(cached)
```

#### Critérios de Aceitação

✅ Retorna hierarquia de tópicos com níveis corretos
✅ Paths são relativos ao workspace
✅ Line numbers são 1-based
✅ Children são aninhados corretamente
✅ Extensão VSCode não usa fallback para Ontology Topics Explorer

---

### Task 2.2: Novo Endpoint `synesis/getOntologyAnnotations` 📦

**Arquivo a criar**: `synesis_lsp/ontology_annotations.py`
**Status Atual**: ❌ Não existe
**Prioridade**: 🟡 **MÉDIA**

#### Requisito

Cruzar conceitos da ontologia (`.syno`) com anotações (`.syn`) e retornar occurrences de cada conceito.

#### Implementação Proposta

Similar a `get_codes()`, mas focado em conceitos da ontologia.

**Arquivo novo**: `synesis_lsp/ontology_annotations.py`

```python
"""
ontology_annotations.py - Cruzamento de ontologia com anotações

Propósito:
    Encontrar todas as ocorrências de conceitos da ontologia
    nos arquivos de anotação.

Custom Request:
    synesis/getOntologyAnnotations → Lista de annotations por conceito
"""

def get_ontology_annotations(cached_result, active_file: Optional[str] = None) -> dict:
    """
    Retorna anotações de ontologia com occurrences.

    Args:
        active_file: Se fornecido, filtra apenas occurrences desse arquivo

    Returns:
        {
            "success": bool,
            "annotations": [
                {
                    "code": str,
                    "ontologyDefined": bool,
                    "ontologyFile": str,
                    "ontologyLine": int,
                    "occurrences": [...]
                }
            ]
        }
    """
    pass  # Implementar
```

#### Critérios de Aceitação

✅ Retorna occurrences com itemName, line, column
✅ Context diferencia "code" vs "chain"
✅ Field mostra nome exato do campo
✅ Se activeFile fornecido, filtra apenas esse arquivo
✅ Extensão VSCode não usa fallback para Ontology Annotations Explorer

---

### Task 2.3: Novo Endpoint `synesis/getAbstract` 📦

**Arquivo a criar**: `synesis_lsp/abstract_viewer.py`
**Status Atual**: ❌ Não existe
**Prioridade**: 🟢 **BAIXA**

#### Requisito

Extrair campo ABSTRACT de arquivo `.syn`.

#### Implementação Proposta

**Arquivo novo**: `synesis_lsp/abstract_viewer.py`

```python
"""
abstract_viewer.py - Extração de campo ABSTRACT

Custom Request:
    synesis/getAbstract → Conteúdo do campo ABSTRACT
"""

def get_abstract(file_path: str) -> dict:
    """
    Extrai campo ABSTRACT do arquivo.

    Returns:
        {
            "success": bool,
            "abstract": str,
            "file": str,
            "line": int
        }
    """
    pass  # Implementar
```

#### Critérios de Aceitação

✅ Retorna conteúdo completo do ABSTRACT (multiline)
✅ Line indica onde campo começa
✅ Extensão VSCode não usa fallback para Abstract Viewer

---

## 📋 FASE 3: MELHORIAS AVANÇADAS

### Task 3.1: Implementar `textDocument/references` 🎯

**Arquivo**: `synesis_lsp/references.py` (novo)
**Prioridade**: 🟢 **BAIXA (Nice to Have)**

Find All References para codes e bibrefs.

### Task 3.2: Implementar `textDocument/codeAction` 🎯

**Arquivo**: `synesis_lsp/code_actions.py` (novo)
**Prioridade**: 🟢 **BAIXA (Nice to Have)**

Quick fixes para erros comuns (ex: "Change 'notes' to 'note'").

### Task 3.3: Workspace Diagnostics 🎯

**Prioridade**: 🟢 **BAIXA (Nice to Have)**

Diagnostics para todo workspace (não apenas arquivos abertos).

---

## 🧪 Estratégia de Testes

### Testes Unitários

Cada task deve ter testes em `tests/`:

- `test_explorer_requests.py`: Expandir com testes de occurrences
- `test_graph.py`: Expandir com testes de filtro por bibref
- `test_template_diagnostics.py`: Expandir com testes de integração
- `test_ontology_topics.py`: Criar novo
- `test_ontology_annotations.py`: Criar novo
- `test_abstract_viewer.py`: Criar novo

### Testes de Integração

Usar dataset `test/fixtures/bibliometrics/` (mencionado no LSP_last_fixes.md linha 913).

### Validação Manual

Para cada task:
1. Iniciar LSP server: `python -m synesis_lsp`
2. Abrir extensão VSCode
3. Executar comando correspondente (ex: Code Explorer)
4. Verificar que **nenhum fallback** é disparado (checar logs)
5. Verificar que dados estão corretos

---

## 📊 Métricas de Sucesso

| Métrica | Antes (v0.10.4) | Meta (v0.11.x) |
|---------|-----------------|----------------|
| % Funcionalidades via LSP | 33% (5/15) | **100% (15/15)** |
| % Explorers com fallback | 60% (3/5) | **0% (0/5)** |
| Linhas de regex local | ~2000 | **0** |
| Diagnostics funcionando | ❌ Não | ✅ **Sim** |
| Navegação clickable | ⚠️ Parcial | ✅ **100%** |

---

## 🗓️ Cronograma Sugerido

### Sprint 1 (Semana 1-2): FASE 1 - CRÍTICO
- **Dia 1-2**: Task 1.1 (Fix getCodes occurrences)
- **Dia 3-4**: Task 1.2 (Fix getRelations location/type)
- **Dia 5-6**: Task 1.3 (Fix getRelationGraph bibref)
- **Dia 7-10**: Task 1.4 (Integrar template diagnostics)

### Sprint 2 (Semana 3-5): FASE 2 - COMPLETUDE
- **Dia 1-4**: Task 2.1 (getOntologyTopics)
- **Dia 5-8**: Task 2.2 (getOntologyAnnotations)
- **Dia 9-10**: Task 2.3 (getAbstract) - opcional

### Sprint 3 (Semana 6-9): FASE 3 - EXCELÊNCIA
- **Dia 1-4**: Task 3.1 (textDocument/references)
- **Dia 5-8**: Task 3.2 (textDocument/codeAction)
- **Dia 9-10**: Task 3.3 (Workspace diagnostics) - opcional

---

## 🔗 Referências

- **Documento de Fixes**: [LSP_last_fixes.md](LSP_last_fixes.md)
- **Arquitetura**: [README.md](README.md)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **LSP Specification**: https://microsoft.github.io/language-server-protocol/
- **Dataset de Teste**: `test/fixtures/bibliometrics/`

---

## 📝 Notas de Implementação

### Convenções de Código

- **Type hints** obrigatórios em todas as funções
- **Docstrings** em formato Google (conforme `coding_pattern.md`)
- **Logging** para debugging (nível INFO para operações principais)
- **Paths relativos** em responses (nunca absolutos)
- **Posições 1-based** em responses LSP (converter internamente quando necessário)

### Tratamento de Erros

- **Nunca crashar** o servidor LSP
- **Degradação graciosa**: retornar `{"success": False, "error": "..."}` em vez de exception
- **Fallback** quando dados não disponíveis (ex: cache vazio)

### Performance

- **Cache**: Usar workspace_cache para evitar recompilação
- **Lazy loading**: Não carregar dados até serem solicitados
- **Debounce**: didChange não precisa (validação é rápida), mas considerar se houver problemas

---

**Criado por**: Claude Code
**Última atualização**: 2026-02-02
**Status**: 📋 **PRONTO PARA IMPLEMENTAÇÃO**
