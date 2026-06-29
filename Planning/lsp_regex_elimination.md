# Plano de Implementação no LSP — Eliminação de Regex da Extensão

> Objetivo: estender o **Synesis LSP** com os endpoints necessários para que **synesis-explorer** elimine todo regex hardcoded de reconhecimento da gramática Synesis. A fonte de verdade da sintaxe passa a ser exclusivamente o compilador (via LSP).
>
> **Data:** 2026-06-22 · **Repos:** `synesis-lsp` (servidor) + `synesis-explorer` (cliente) · **Versão LSP alvo:** 0.14.0

---

## 1. Contexto e princípio

A extensão já consome o LSP para References, Codes, Relations, RelationGraph, OntologyTopics, OntologyAnnotations, Excerpts e Abstract (via `dataService.js`). Restam **parsers regex** (`src/parsers/*.js`) que reimplementam a gramática Synesis no cliente — risco de divergência sempre que a linguagem evolui (ex.: `OPTIONAL BUNDLE` adicionado em synesis 0.6.0).

**Diretriz:** nenhum reconhecimento de gramática Synesis no cliente. Tudo que dependa de entender a sintaxe vem do LSP, que delega ao `SynesisCompiler` / `TemplateNode` / `LinkedProject` já em cache.

---

## 2. Inventário: parsers regex e seu destino

| Parser regex (extensão) | Consumidor(es) | Shape produzido hoje | Destino |
|--------------------------|----------------|----------------------|---------|
| `templateParser.js` | `core/templateManager.js` | `{fields: [{name, type, scope, relations, arity, values}]}` | **WI-A** — novo `synesis/getTemplate` |
| `synesisParser.js` | `services/coderService.js` | blocos SOURCE/ITEM com **offsets** (`startOffset`, `endOffset`, `blockOffset`, `line`) | **WI-B** — novo `synesis/getBlocks` |
| `bibtexParser.js` + `synesisParser.js` | `viewers/abstractViewer.js` | abstract + excerpts | **WI-C** — `synesis/getAbstract` (✅ já existe) + `getBlocks` |
| `ontologyParser.js` | **nenhum (órfão)** | — | **WI-D** — remover sem endpoint |
| `chainParser.js` | lógica pura de relações | — | **mantém** (não é reconhecimento de gramática de arquivo; opera sobre dados já estruturados) |

> **Descoberta-chave:** `ontologyParser.js` não tem consumidores — é código morto. E `synesisParser` no `coderService` é usado por suas **posições de bloco** (para detectar bibref sob o cursor e inserir o ITEM gerado), não por semântica — o que muda a natureza do endpoint (posicional, não só de conteúdo).

---

## 3. Work Items

### WI-A — `synesis/getTemplate` (desbloqueia `templateParser.js`)

**Motivação.** `templateManager.js` chama `templateParser.parse(.synt)` via regex para obter field-specs. O LSP já tem o `TemplateNode` completo em `cached.result` (mesmo padrão de `getProjectStats`).

**Endpoint.** `@server.command("synesis/getTemplate")`

**Params** (mesmo padrão dos demais comandos):
```jsonc
{ "workspaceRoot": "<path>" }   // ou file, resolvido por _resolve_workspace_root
```

**Resposta** (espelha o que `templateParser` produz, mas autoritativo e **mais rico** — inclui bundles):
```jsonc
{
  "success": true,
  "template": {
    "name": "bibliometrics",
    "fields": [
      {
        "name": "period",
        "type": "TEXT",                 // FieldType.value
        "scope": "ITEM",                // SOURCE|ITEM|ONTOLOGY
        "relations": ["INFLUENCES"],    // null se não-CHAIN
        "arity": { "operator": ">=", "value": 2 },  // null se ausente
        "values": [                     // null se não enum/ordered
          { "index": 0, "label": "low", "description": "..." }
        ]
      }
    ],
    "requirements": {                   // NOVO — impossível via regex hoje de forma confiável
      "SOURCE":   { "required": [...], "optional": [...], "forbidden": [...],
                    "bundles": [[...]], "optional_bundles": [[...]] },
      "ITEM":     { ... },
      "ONTOLOGY": { ... }
    }
  }
}
```

**Implementação (servidor).**
1. Novo módulo `template_info.py` (ou função em `converters.py`) que recebe um `TemplateNode` e devolve o dict acima — reutiliza `TemplateNode.to_dict()` quando suficiente, normalizando para o shape do cliente.
2. Comando em `server.py` no padrão de `get_project_stats`: resolve workspace → busca `cached.result` → extrai `cached.result.template` → serializa.
3. Lida com cache vazio devolvendo `{"success": False, "error": "..."}`.

**Impacto (rodar `gitnexus_impact` antes de editar `server.py`).** Adição pura — novo comando, sem alterar `validate_*` ou `get_project_stats`. Risco baixo.

**Lado extensão.** `templateManager.js` passa a chamar `dataService.getTemplate()`; `templateParser.js` removido. `chainParser` continua consumindo `field.relations` — agora vindo do LSP.

---

### WI-B — `synesis/getBlocks` (desbloqueia `synesisParser.js` no coderService)

**Motivação.** `coderService._detectBibref` usa `parseSourceBlocks/parseItems` para: (1) detectar o bibref do bloco sob o cursor (`startOffset ≤ cursor ≤ endOffset`); (2) com fallback para o bloco anterior mais próximo quando o cursor está entre blocos. Precisa de **(bibref, range) por bloco SOURCE/ITEM**.

**Decisão (tomada).** Verificação de `symbols.py` concluída: o `DocumentSymbol` já fornece `range` por bloco, **mas o bibref vem apenas embutido no label formatado** (`"SOURCE @smith2024"`, `"ITEM #1"`) e o ITEM-filho **não carrega bibref próprio** (herda do SOURCE pai na hierarquia). Reusar DocumentSymbol exigiria *string-parsing do label* no cliente — apenas troca um regex por outro.

**→ Rota escolhida: novo comando `synesis/getBlocks`** com bibref e range **estruturados**, bibref já resolvido em cada ITEM (sem herança implícita), eliminando qualquer parsing no cliente.

**Endpoint.** `@server.command("synesis/getBlocks")`

**Params:**
```jsonc
{ "file": "<path do .syn>", "workspaceRoot": "<path>" }   // padrão de getAbstract
```

**Resposta:**
```jsonc
{
  "success": true,
  "blocks": [
    { "kind": "SOURCE", "bibref": "smith2024",   // sem '@', como coderService espera
      "range": { "start": {"line": 9,  "character": 0}, "end": {"line": 14, "character": 8} } },
    { "kind": "ITEM",   "bibref": "smith2024",   // resolvido — não herdado do pai
      "range": { "start": {"line": 16, "character": 0}, "end": {"line": 23, "character": 6} } }
  ]
}
```

**Implementação (servidor).**
1. Reutilizar `compute_document_symbols` / `_build_symbols_from_nodes` de `symbols.py` (mesma travessia de `SourceNode`/`ItemNode` com `_make_block_range`), mas emitir o shape estruturado acima em vez de `DocumentSymbol` formatado. Extrair a travessia comum para evitar duplicação.
2. Resolver bibref diretamente de `node.bibref` (já disponível no AST — `snode.bibref` / `item.bibref`), normalizado sem `@`.
3. Herdar o **fallback regex já existente** (`_extract_symbols_regex`) para texto inválido durante edição — comportamento que o `coderService` precisa, pois opera no buffer ativo possivelmente não-compilável.

**Impacto (rodar `gitnexus_impact` em `symbols.py` antes de extrair a travessia).** Refatoração de `symbols.py` para compartilhar a travessia toca um símbolo com caller LSP (`textDocument/documentSymbol`) — **validar que o DocumentSymbol existente não regride**. Adição do comando em si é pura.

**Lado extensão.** `coderService._detectBibref` passa a chamar `dataService.getBlocks(file)`, converte `range` → offset via `document.offsetAt`, e aplica a mesma lógica de contenção/bloco-anterior. `synesisParser.js` removido.

> **Nota:** `getBlocks` é por-arquivo (via `compile_string`/`compute_document_symbols`), não via `LinkedProject` em cache — correto, pois o coderService age sobre o **documento ativo**, que pode estar sujo/não-salvo.

---

### WI-C — Migrar `abstractViewer.js` para LSP (sem novo endpoint)

**Motivação.** `abstractViewer` usa `bibtexParser` + `synesisParser`. O abstract já vem de `synesis/getAbstract` (server.py:1122). Os excerpts já vêm de `synesis/getExcerpts` (consumido via `dataService.getExcerpts`).

**Implementação.** Lado extensão apenas:
1. `abstractViewer` passa a chamar `dataService.getAbstract()` + `dataService.getExcerpts()`.
2. Remove imports de `bibtexParser` e `synesisParser`.
3. Posições de destaque no abstract usam `fuzzyMatcher` (lógica pura, mantida) sobre o texto vindo do LSP.

**Dependência.** Confirmar que `getAbstract` devolve o texto completo do abstract e não exige o `.bib` parseado no cliente. (Já implementado no servidor — validar shape.)

**Impacto.** Zero servidor; remove 2 parsers do cliente.

---

### WI-D — Remover `ontologyParser.js` (código morto)

**Motivação.** Sem consumidores (confirmado por busca em `src/`). OntologyTopics e OntologyAnnotations já vêm de `synesis/getOntologyTopics` / `synesis/getOntologyAnnotations`.

**Implementação.** Deletar `src/parsers/ontologyParser.js`. Zero impacto servidor.

---

## 4. Sequenciamento

| Ordem | WI | Bloqueia? | Esforço servidor | Esforço extensão |
|-------|----|-----------|------------------|------------------|
| 1 | **WI-D** remover `ontologyParser` | não | nenhum | trivial (delete) |
| 2 | **WI-C** migrar `abstractViewer` | depende de `getAbstract` (pronto) | nenhum (validar shape) | médio |
| 3 | **WI-B** `getBlocks` p/ coderService | refatorar travessia de `symbols.py` | **baixo-médio** (extrair travessia + novo comando) | médio (coderService) |
| 4 | **WI-A** `getTemplate` | não | **médio** (novo serializer + comando) | médio (templateManager) |

> WI-A e WI-B têm trabalho de servidor; juntos **completam** a eliminação do regex de gramática. WI-D/C reduzem a superfície antes, com risco mínimo. WI-B carrega risco de regressão controlado (refatora `symbols.py`, que tem caller LSP) — mitigado por teste do DocumentSymbol existente.

---

## 5. Contrato e versionamento

- **Bump do LSP:** `0.13.0 → 0.14.0` (novos comandos = minor).
- **`MIN_LSP_VERSION` na extensão:** subir de `0.13.0` para `0.14.0` **somente após** WI-A entrar, pois `getTemplate` é o único endpoint novo de que a extensão passa a depender de forma dura. WI-B Rota 1 e WI-C não exigem nova versão.
- **Fallback gracioso:** seguir o padrão de `_sendRequestWithFallback` do `dataService`. Se `getTemplate` retornar method-not-found (LSP antigo), a extensão pode **degradar** mantendo `templateParser` como fallback explícito por uma versão de transição — depois removê-lo.
- **CHANGELOG (ambos repos):** documentar novos comandos no `synesis-lsp` e a remoção dos parsers no `synesis-explorer`, no molde do compilador.

---

## 6. Testes (liga com o plano de testes da extensão)

**No LSP (`synesis-lsp/tests/`):**
- `getTemplate` sobre projeto fixture devolve field-specs corretos, incluindo `optional_bundles` (regressão direta do synesis 0.6.0).
- `getTemplate` com cache vazio → `{success: False}`.
- (Se Rota 2) `getBlocks` devolve ranges corretos para SOURCE/ITEM.

**Na extensão (`synesis-explorer/test/`):**
- `lspMock` ganha payloads canned de `getTemplate`/`getBlocks` → testa `templateManager`/`coderService` **sem** servidor real.
- Teste de contrato de versão: endpoints esperados existem em `MIN_LSP_VERSION`.
- Após cada WI: garantir que nenhum `require('../parsers/...')` de gramática permanece (lint rule ou teste de import).

---

## 7. Critério de pronto (definição de "regex eliminado")

A eliminação está completa quando:
1. ✅ `templateParser.js`, `synesisParser.js`, `ontologyParser.js` removidos de `src/parsers/`.
2. ✅ Nenhum módulo da extensão reconhece blocos/campos da gramática Synesis via regex.
3. ✅ `chainParser.js` permanece (opera sobre dados já estruturados do LSP, não sobre texto-fonte).
4. ✅ `bibtexParser.js` — avaliar: se só serve ao abstract e o LSP cobre, remover; senão, manter isolado como utilitário BibTeX puro (BibTeX não é gramática Synesis).
5. ✅ Suítes de teste verdes em ambos os repos; `MIN_LSP_VERSION` alinhada.

---

## 8. Riscos

| Risco | Mitigação |
|-------|-----------|
| `getTemplate` shape diverge do que `templateManager` espera | Definir o shape a partir do consumidor real (§3 WI-A espelha `templateParser` + estende) e cobrir com teste antes de remover o parser |
| DocumentSymbol não carrega bibref/offsets (WI-B) | Passo de verificação explícito; Rota 2 como fallback projetada |
| Quebra de compatibilidade com LSP antigo | `_sendRequestWithFallback` + período de transição mantendo parser como fallback |
| `bibtexParser` ainda necessário para algo além do abstract | Auditar consumidores antes de remover; pode legitimamente permanecer (BibTeX ≠ gramática Synesis) |
| Cache do LSP desatualizado ao pedir `getTemplate` | Reusar a invalidação já existente (didSave/didChange → reload) — mesmo cache de `getProjectStats` |
