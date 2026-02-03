# LSP Implementation Roadmap - Eliminar Fallback para Regex

**Data**: 2026-02-02
**Versão LSP atual**: v0.10.4
**Objetivo**: Implementar todas as funcionalidades necessárias no LSP para que a extensão funcione 100% via LSP, eliminando completamente o fallback para regex local.

---

## 📊 Status Atual das Funcionalidades

| Funcionalidade | Status LSP | Fallback Ativo | Prioridade |
|----------------|------------|----------------|------------|
| Reference Explorer | ✅ Parcial | ⚠️ Sim (quando vazio) | Baixa |
| Code Explorer | ❌ Incompleto | ✅ Sim (falta occurrences) | **ALTA** |
| Relation Explorer | ❌ Incompleto | ✅ Sim (falta location/type) | **ALTA** |
| Graph Viewer | ❌ Quebrado | ✅ Sim (bibref retorna vazio) | **ALTA** |
| Ontology Topics Explorer | ❌ Não implementado | ✅ Sim (100% regex) | Média |
| Ontology Annotations Explorer | ❌ Não implementado | ✅ Sim (100% regex) | Média |
| Abstract Viewer | ❌ Não implementado | ✅ Sim (100% regex) | Baixa |
| Diagnostics (validação) | ❌ Quebrado | N/A | **ALTA** |

---

## 🔧 IMPLEMENTAÇÕES CRÍTICAS (Alta Prioridade)

### 1. ✅ Fix `synesis/getCodes` - Adicionar Occurrences

**Status**: ⚠️ **PARCIALMENTE IMPLEMENTADO** (retorna codes mas sem occurrences)

**Problema Atual**:
```python
# LSP v0.10.4 retorna:
{
    "success": true,
    "codes": [
        {
            "code": "my_code",
            "usageCount": 5,
            "ontologyDefined": true
            # ❌ FALTA: occurrences
        }
    ]
}
```

**Contrato Esperado**:
```python
# Request
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getCodes",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project"
            }
        ]
    }
}

# Response Esperada
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "success": true,
        "codes": [
            {
                "code": "my_code",
                "usageCount": 5,
                "ontologyDefined": true,
                "occurrences": [
                    {
                        "file": "relative/path/to/file.syn",  # relativo ao workspaceRoot
                        "line": 42,                           # 1-based
                        "column": 15,                         # 1-based
                        "context": "code",                    # "code" | "chain"
                        "field": "CODE"                       # nome do campo no template
                    },
                    {
                        "file": "another/file.syn",
                        "line": 108,
                        "column": 8,
                        "context": "chain",
                        "field": "CHAIN"
                    }
                ]
            }
        ]
    }
}
```

**Implementação Necessária**:
1. Para cada code encontrado, rastrear todas as ocorrências em campos CODE e CHAIN
2. Calcular posição exata (line/column) de cada ocorrência dentro do campo
3. Armazenar contexto (se aparece em CODE ou CHAIN) e nome do campo
4. Retornar paths relativos ao `workspaceRoot` (não absolutos)

**Impacto**:
- ✅ Code Explorer terá navegação clickable para cada ocorrência
- ✅ Eliminará fallback para LocalRegexProvider.getCodes()
- ✅ Go to Definition usará dados LSP precisos

**Exemplo de Uso na Extensão**:
```javascript
// src/services/dataService.js linha 101-113
const codes = (result.codes || []).map(c => ({
    code: c.code,
    usageCount: c.usageCount || 0,
    ontologyDefined: c.ontologyDefined || false,
    occurrences: (c.occurrences || []).map(o => ({
        file: path.resolve(workspaceRoot, o.file),  // converte para absoluto
        line: o.line - 1,                            // converte para 0-based
        column: o.column - 1,                        // converte para 0-based
        context: o.context || 'code',
        field: o.field || ''
    }))
}));
return codes.length > 0 ? codes : null;
```

---

### 2. ✅ Fix `synesis/getRelations` - Adicionar Location e Type

**Status**: ⚠️ **PARCIALMENTE IMPLEMENTADO** (retorna relations mas sem location/type)

**Problema Atual**:
```python
# LSP v0.10.4 retorna (testado):
{
    "success": true,
    "relations": [
        {
            "from": "code1",
            "relation": "relates_to",
            "to": "code2"
            # ❌ FALTA: location (file/line/column)
            # ❌ FALTA: type (qualified/simple)
        }
    ]
}
```

**Contrato Esperado**:
```python
# Request
{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getRelations",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project"
            }
        ]
    }
}

# Response Esperada
{
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "success": true,
        "relations": [
            {
                "from": "code1",
                "relation": "relates_to",
                "to": "code2",
                "type": "qualified",                   # "qualified" | "simple"
                "location": {
                    "file": "relative/path/to/file.syn",  # relativo ao workspaceRoot
                    "line": 156,                          # 1-based (linha do triplet no CHAIN)
                    "column": 5                           # 1-based (coluna do início do triplet)
                }
            },
            {
                "from": "code2",
                "relation": "causes",
                "to": "code3",
                "type": "simple",
                "location": {
                    "file": "relative/path/to/file.syn",
                    "line": 158,
                    "column": 5
                }
            }
        ]
    }
}
```

**Implementação Necessária**:
1. Ao parsear campos CHAIN, rastrear a posição exata de cada triplet (from-relation-to)
2. Determinar tipo do chain (qualified vs simple) conforme parser existente
3. Calcular line/column exato do início do triplet dentro do campo CHAIN
4. Retornar paths relativos ao `workspaceRoot`

**Regras de Parsing**:
```python
# Qualified chain (tem "::" e type):
# "<type>::<code1>-<relation>-<code2>"
# Exemplo: "causes::smoking-causes-cancer"
# type = "qualified"

# Simple chain (sem type):
# "<code1>-<relation>-<code2>"
# Exemplo: "smoking-causes-cancer"
# type = "simple"
```

**Impacto**:
- ✅ Relation Explorer terá navegação clickable para cada triplet
- ✅ Eliminará fallback para LocalRegexProvider.getRelations()
- ✅ Display mostrará tipo do chain na UI

**Exemplo de Uso na Extensão**:
```javascript
// src/services/dataService.js linha 126-148
const grouped = new Map();
let hasAnyLocation = false;
for (const rel of (result.relations || [])) {
    if (!grouped.has(rel.relation)) {
        grouped.set(rel.relation, { relation: rel.relation, triplets: [] });
    }
    const hasLocation = Boolean(rel.location && rel.location.file);
    if (hasLocation) {
        hasAnyLocation = true;
    }
    grouped.get(rel.relation).triplets.push({
        from: rel.from,
        to: rel.to,
        file: hasLocation ? path.resolve(workspaceRoot, rel.location.file) : null,
        line: hasLocation ? (rel.location.line - 1) : -1,
        column: hasLocation ? (rel.location.column || 0) : -1,
        type: rel.type || ''
    });
}
if (!hasAnyLocation) {
    return null;  // ❌ Dispara fallback se nenhuma relation tem location
}
return Array.from(grouped.values());
```

---

### 3. ✅ Fix `synesis/getRelationGraph` - Consertar Filtro por Bibref

**Status**: ❌ **QUEBRADO** (retorna grafo vazio quando bibref fornecido)

**Problema Atual**:
```python
# Testado com synesis-lsp v0.10.4:

# SEM bibref - FUNCIONA (mas retorna vazio porque template não tem CODE):
{
    "workspaceRoot": "/path/to/project"
}
# Retorna: {"success": true, "mermaid": "graph LR\n..."}

# COM bibref - QUEBRADO (retorna vazio mesmo com CHAINs):
{
    "workspaceRoot": "/path/to/project",
    "bibref": "@ashworth2019"
}
# Retorna: {"success": true, "mermaid": ""}  ❌
```

**Contrato Esperado**:
```python
# Request SEM bibref (grafo completo)
{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getRelationGraph",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project"
            }
        ]
    }
}

# Request COM bibref (filtrado por referência)
{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getRelationGraph",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project",
                "bibref": "@ashworth2019"  # aceitar com ou sem @
            }
        ]
    }
}

# Response Esperada
{
    "jsonrpc": "2.0",
    "id": 4,
    "result": {
        "success": true,
        "mermaidCode": "graph LR\n  code1[Code 1]\n  code2[Code 2]\n  code1 -->|relates_to| code2",
        # OU (aceitar ambos nomes de campo):
        "mermaid": "graph LR\n  code1[Code 1]\n  code2[Code 2]\n  code1 -->|relates_to| code2"
    }
}
```

**Implementação Necessária**:
1. Normalizar bibref (aceitar com/sem `@` prefix)
2. Filtrar apenas CHAINs de items que referenciam o bibref fornecido
3. Gerar grafo Mermaid apenas com relações desses items
4. Se bibref não existe, retornar grafo vazio com `success: true`
5. Se bibref é null/undefined, retornar grafo completo de todo o projeto

**Algoritmo de Filtragem**:
```python
def get_relation_graph(workspace_root, bibref=None):
    if bibref:
        # Normalizar bibref
        normalized = bibref if bibref.startswith('@') else f'@{bibref}'

        # Encontrar todos os items que referenciam este bibref
        items = [item for item in all_items
                 if normalized in item.get_field('BIBREF', [])]

        # Extrair apenas CHAINs desses items
        chains = []
        for item in items:
            chain_field = item.get_field('CHAIN', [])
            chains.extend(parse_chains(chain_field))

        # Gerar grafo Mermaid
        return generate_mermaid_from_chains(chains)
    else:
        # Gerar grafo completo
        all_chains = extract_all_chains(workspace_root)
        return generate_mermaid_from_chains(all_chains)
```

**Impacto**:
- ✅ Graph Viewer funcionará com filtro por referência bibliográfica
- ✅ Eliminará fallback para LocalRegexProvider.getRelationGraph()
- ✅ Comando `synesis.showGraph` usará LSP 100%

**Exemplo de Uso na Extensão**:
```javascript
// src/services/dataService.js linha 151-169
async getRelationGraph(workspaceRoot, bibref) {
    const params = { workspaceRoot };
    if (bibref) {
        params.bibref = bibref;
    }
    const result = await this._sendRequestWithFallback(
        'synesis/getRelationGraph',
        params,
        ['synesis/get_relation_graph']
    );
    if (!result || !result.success) {
        return null;
    }
    const mermaidCode = result.mermaidCode || result.mermaid || '';
    if (!mermaidCode) {
        return null;  // ❌ Dispara fallback se grafo vazio
    }
    return { mermaidCode };
}
```

---

### 4. ✅ Fix `textDocument/publishDiagnostics` - Validação de Template

**Status**: ❌ **NÃO FUNCIONA** (não publica diagnostics para campos inválidos)

**Problema Atual**:
```python
# Cenário testado:
# 1. Template define campos: CODE, CHAIN, BIBREF, NOTE
# 2. Arquivo .syn usa campo inválido: "notes" (plural)
# 3. LSP não publica nenhum diagnostic

# textDocument/didOpen ou didChange
{
    "jsonrpc": "2.0",
    "method": "textDocument/didOpen",
    "params": {
        "textDocument": {
            "uri": "file:///path/to/file.syn",
            "languageId": "synesis",
            "version": 1,
            "text": "ITEM: item1\nnotes: invalid field\n"  # ❌ "notes" não existe
        }
    }
}

# LSP deveria publicar:
# ❌ NÃO ACONTECE
```

**Contrato Esperado**:
```python
# Quando LSP detecta campo inválido, deve publicar:
{
    "jsonrpc": "2.0",
    "method": "textDocument/publishDiagnostics",
    "params": {
        "uri": "file:///path/to/file.syn",
        "diagnostics": [
            {
                "range": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 5}
                },
                "severity": 1,  # Error
                "source": "synesis-lsp",
                "message": "Unknown field 'notes'. Valid fields for this template: CODE, CHAIN, BIBREF, NOTE"
            }
        ]
    }
}
```

**Validações Necessárias**:

1. **Campos Inválidos**:
   ```python
   # Detectar campos que não existem no template
   # Exemplo: "notes" quando template define "note"
   # Severity: Error
   ```

2. **Campos Obrigatórios Faltando**:
   ```python
   # Se template marca campo como required, validar presença
   # Exemplo: ITEM faltando quando required=true
   # Severity: Error
   ```

3. **Valores de Campo Inválidos**:
   ```python
   # Validar formato de bibrefs (@reference)
   # Validar sintaxe de chains (code1-relation-code2)
   # Severity: Warning ou Error conforme gravidade
   ```

4. **Referências Não Definidas**:
   ```python
   # Avisar quando code usado em CHAIN não está definido em ontologia
   # Exemplo: "smoking-causes-cancer" mas "smoking" não existe em .syno
   # Severity: Warning (não Error, pode ser intencional)
   ```

**Implementação Necessária**:
1. Ao receber `textDocument/didOpen` ou `didChange`, parsear o documento
2. Carregar template do projeto (.synp → .synt)
3. Validar cada campo contra o template
4. Publicar diagnostics via `textDocument/publishDiagnostics`
5. Limpar diagnostics quando arquivo corrigido

**Impacto**:
- ✅ Editor mostrará erros em tempo real (squiggly lines)
- ✅ Problems panel listará todos os erros de validação
- ✅ Melhorará UX significativamente (feedback imediato)

---

## 🔧 IMPLEMENTAÇÕES MÉDIAS (Prioridade Média)

### 5. ⭐ Novo Endpoint: `synesis/getOntologyTopics`

**Status**: ❌ **NÃO EXISTE** (extensão usa 100% regex)

**Funcionalidade Atual**:
- Extensão lê arquivos `.syno` via regex
- Parseia hierarquia de tópicos (indentação define nível)
- Organiza árvore de conceitos

**Contrato Proposto**:
```python
# Request
{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getOntologyTopics",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project"
            }
        ]
    }
}

# Response
{
    "jsonrpc": "2.0",
    "id": 5,
    "result": {
        "success": true,
        "topics": [
            {
                "name": "Health",
                "level": 0,
                "file": "ontology/health.syno",
                "line": 1,
                "children": [
                    {
                        "name": "Smoking",
                        "level": 1,
                        "file": "ontology/health.syno",
                        "line": 5,
                        "children": []
                    }
                ]
            }
        ]
    }
}
```

**Estrutura do .syno**:
```
Health
    Smoking
        Tobacco Use
        Nicotine Addiction
    Diseases
        Cancer
        Heart Disease
```

**Implementação Necessária**:
1. Parsear arquivos `.syno` respeitando indentação (hierarquia)
2. Construir árvore de tópicos com níveis (level 0, 1, 2...)
3. Rastrear posição de cada tópico (file/line)
4. Retornar estrutura hierárquica completa

**Impacto**:
- ✅ Ontology Topics Explorer usará LSP
- ✅ Eliminará dependência de WorkspaceScanner para .syno

---

### 6. ⭐ Novo Endpoint: `synesis/getOntologyAnnotations`

**Status**: ❌ **NÃO EXISTE** (extensão usa 100% regex)

**Funcionalidade Atual**:
- Extensão cruza dados de `.syno` (conceitos) com `.syn` (anotações)
- Encontra occurrences de cada conceito em campos CODE/CHAIN
- Calcula posição exata dentro do ITEM

**Contrato Proposto**:
```python
# Request
{
    "jsonrpc": "2.0",
    "id": 6,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getOntologyAnnotations",
        "arguments": [
            {
                "workspaceRoot": "/path/to/project",
                "activeFile": "/path/to/file.syn"  # opcional: filtrar por arquivo ativo
            }
        ]
    }
}

# Response
{
    "jsonrpc": "2.0",
    "id": 6,
    "result": {
        "success": true,
        "annotations": [
            {
                "code": "smoking",
                "ontologyDefined": true,
                "ontologyFile": "ontology/health.syno",
                "ontologyLine": 5,
                "occurrences": [
                    {
                        "file": "data/study1.syn",
                        "itemName": "participant_001",
                        "line": 42,           # linha exata dentro do ITEM
                        "column": 15,         # coluna exata
                        "context": "code",    # "code" | "chain"
                        "field": "CODE"       # nome do campo
                    },
                    {
                        "file": "data/study1.syn",
                        "itemName": "participant_002",
                        "line": 108,
                        "column": 8,
                        "context": "chain",
                        "field": "CHAIN"
                    }
                ]
            }
        ]
    }
}
```

**Implementação Necessária**:
1. Carregar todos os conceitos definidos em `.syno`
2. Escanear arquivos `.syn` procurando por esses conceitos
3. Calcular posição exata de cada ocorrência dentro do ITEM (não apenas linha do ITEM)
4. Retornar lista de annotations com todas as occurrences
5. Se `activeFile` fornecido, filtrar apenas occurrences desse arquivo

**Impacto**:
- ✅ Ontology Annotations Explorer usará LSP
- ✅ Navegação clickable será mais precisa (LSP calcula posição)
- ✅ Eliminará dependência de positionUtils.findTokenPosition()

---

### 7. ⭐ Novo Endpoint: `synesis/getAbstract`

**Status**: ❌ **NÃO EXISTE** (extensão usa 100% regex)

**Funcionalidade Atual**:
- Extensão lê arquivo `.syn` ativo
- Extrai campo ABSTRACT usando SynesisParser
- Renderiza em webview

**Contrato Proposto**:
```python
# Request
{
    "jsonrpc": "2.0",
    "id": 7,
    "method": "workspace/executeCommand",
    "params": {
        "command": "synesis/getAbstract",
        "arguments": [
            {
                "file": "/path/to/file.syn"
            }
        ]
    }
}

# Response
{
    "jsonrpc": "2.0",
    "id": 7,
    "result": {
        "success": true,
        "abstract": "This study examines the relationship between...",
        "file": "/path/to/file.syn",
        "line": 5  # linha onde campo ABSTRACT começa
    }
}
```

**Implementação Necessária**:
1. Parsear arquivo `.syn` fornecido
2. Extrair campo ABSTRACT (multiline)
3. Retornar conteúdo completo do campo
4. Retornar line onde campo começa (para navegação)

**Impacto**:
- ✅ Abstract Viewer usará LSP
- ✅ Eliminará dependência de SynesisParser local
- **Prioridade Baixa**: Funcionalidade simples, regex funciona bem

---

## 🔧 MELHORIAS ADICIONAIS (Nice to Have)

### 8. 🎯 Implementar `textDocument/documentSymbol`

**Benefício**: Outline view no VSCode mostrando estrutura do documento

```python
# Response para .syn file
{
    "jsonrpc": "2.0",
    "id": 8,
    "result": [
        {
            "name": "participant_001",
            "kind": 5,  # SymbolKind.Class (ITEM)
            "range": {...},
            "selectionRange": {...},
            "children": [
                {"name": "CODE", "kind": 8, ...},      # SymbolKind.Field
                {"name": "CHAIN", "kind": 8, ...},
                {"name": "BIBREF", "kind": 8, ...}
            ]
        }
    ]
}
```

---

### 9. 🎯 Implementar `textDocument/references`

**Benefício**: "Find All References" para codes/bibrefs

```python
# Request ao clicar em "smoking" e executar Find References
{
    "textDocument": {"uri": "file:///path/to/file.syn"},
    "position": {"line": 42, "character": 15}
}

# Response (todas as occorrences de "smoking")
[
    {
        "uri": "file:///path/to/file1.syn",
        "range": {"start": {"line": 42, "character": 15}, ...}
    },
    {
        "uri": "file:///path/to/file2.syn",
        "range": {"start": {"line": 108, "character": 8}, ...}
    }
]
```

---

### 10. 🎯 Implementar `textDocument/codeAction`

**Benefício**: Quick fixes para erros comuns

```python
# Exemplo: sugerir correção de "notes" → "note"
{
    "diagnostics": [...],  # diagnostic de campo inválido
    "context": {...}
}

# Response
[
    {
        "title": "Change 'notes' to 'note'",
        "kind": "quickfix",
        "edit": {
            "changes": {
                "file:///path/to/file.syn": [
                    {
                        "range": {...},
                        "newText": "note"
                    }
                ]
            }
        }
    }
]
```

---

## 📋 ROADMAP DE IMPLEMENTAÇÃO

### Fase 1: CRÍTICO (Eliminar Fallbacks em Explorers)
**Prazo sugerido**: 1-2 semanas

1. ✅ Fix `synesis/getCodes` - adicionar occurrences
2. ✅ Fix `synesis/getRelations` - adicionar location/type
3. ✅ Fix `synesis/getRelationGraph` - consertar filtro bibref
4. ✅ Fix `textDocument/publishDiagnostics` - validação funcionar

**Resultado**: Code Explorer, Relation Explorer e Graph Viewer funcionarão 100% via LSP

---

### Fase 2: COMPLETUDE (Eliminar Regex Completamente)
**Prazo sugerido**: 2-3 semanas

5. ⭐ Implementar `synesis/getOntologyTopics`
6. ⭐ Implementar `synesis/getOntologyAnnotations`
7. ⭐ Implementar `synesis/getAbstract` (opcional, baixa prioridade)

**Resultado**: Todos os explorers e viewers funcionarão via LSP, regex eliminado

---

### Fase 3: EXCELÊNCIA (LSP Features Avançadas)
**Prazo sugerido**: 3-4 semanas

8. 🎯 Implementar `textDocument/documentSymbol` (outline view)
9. 🎯 Implementar `textDocument/references` (find all references)
10. 🎯 Implementar `textDocument/codeAction` (quick fixes)

**Resultado**: Experiência LSP completa, paridade com IDEs modernos

---

## 🧪 TESTES DE VALIDAÇÃO

Para cada endpoint implementado, validar com:

```python
# test/lsp_validation.py

import subprocess
import json

def test_get_codes_with_occurrences():
    """Valida que getCodes retorna occurrences completos"""
    result = send_lsp_request('synesis/getCodes', {
        'workspaceRoot': 'test/fixtures/bibliometrics'
    })

    assert result['success'] == True
    assert len(result['codes']) > 0

    # Validar estrutura de occurrences
    code = result['codes'][0]
    assert 'occurrences' in code
    assert len(code['occurrences']) > 0

    occ = code['occurrences'][0]
    assert 'file' in occ
    assert 'line' in occ and isinstance(occ['line'], int)
    assert 'column' in occ and isinstance(occ['column'], int)
    assert occ['context'] in ['code', 'chain']
    assert 'field' in occ

def test_get_relations_with_location():
    """Valida que getRelations retorna location completo"""
    result = send_lsp_request('synesis/getRelations', {
        'workspaceRoot': 'test/fixtures/bibliometrics'
    })

    assert result['success'] == True
    assert len(result['relations']) > 0

    # Validar location
    rel = result['relations'][0]
    assert 'location' in rel
    assert 'file' in rel['location']
    assert 'line' in rel['location']
    assert 'column' in rel['location']
    assert 'type' in rel
    assert rel['type'] in ['qualified', 'simple']

def test_get_relation_graph_with_bibref():
    """Valida que getRelationGraph filtra por bibref"""
    result = send_lsp_request('synesis/getRelationGraph', {
        'workspaceRoot': 'test/fixtures/bibliometrics',
        'bibref': '@ashworth2019'
    })

    assert result['success'] == True
    mermaid = result.get('mermaidCode') or result.get('mermaid')
    assert mermaid is not None
    assert len(mermaid) > 0
    assert 'graph LR' in mermaid

def test_diagnostics_invalid_field():
    """Valida que diagnostics detecta campos inválidos"""
    # Abrir documento com campo inválido
    send_lsp_notification('textDocument/didOpen', {
        'textDocument': {
            'uri': 'file:///test.syn',
            'languageId': 'synesis',
            'version': 1,
            'text': 'ITEM: test\ninvalid_field: value\n'
        }
    })

    # Aguardar publicação de diagnostics
    diagnostics = wait_for_diagnostics('file:///test.syn')

    assert len(diagnostics) > 0
    assert diagnostics[0]['severity'] == 1  # Error
    assert 'invalid_field' in diagnostics[0]['message'].lower()
```

---

## 📊 MÉTRICAS DE SUCESSO

Após implementação completa:

| Métrica | Antes | Meta |
|---------|-------|------|
| % Funcionalidades usando LSP | 33% (5/15) | **100% (15/15)** |
| % Explorers com fallback ativo | 60% (3/5) | **0% (0/5)** |
| Linhas de regex parsing local | ~2000 | **0** |
| Diagnostics funcionando | ❌ Não | ✅ **Sim** |
| Navegação clickable completa | ⚠️ Parcial | ✅ **100%** |

---

## 🔗 REFERÊNCIAS

- **LSP Specification**: https://microsoft.github.io/language-server-protocol/
- **Código atual da extensão**: `src/services/dataService.js` (adapter pattern)
- **Tests existentes**: `test/fixtures/bibliometrics/` (dataset de teste)
- **Scripts de teste**: `C:\Users\DeBritto\AppData\Local\Temp\claude\d--GitHub-synesis-explorer\cd7aadb1-52a6-4b97-a746-d60ae39f01b4\scratchpad\test_lsp2.py`

---

**Documento criado por**: Claude Code
**Última atualização**: 2026-02-02
