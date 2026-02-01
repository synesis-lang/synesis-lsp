# Synesis Language Server Protocol (LSP)

**Servidor LSP para validação em tempo real de arquivos Synesis v1.1 no VSCode e outros editores compatíveis.**

## 🤖 AI INSTRUCTIONS

- Este LSP e um adaptador de protocolo; nao implemente parsing/semantica aqui.
- Toda validacao deve usar `synesis.lsp_adapter.validate_single_file`.
- Converta sempre `SourceLocation` (1-based) -> LSP Range (0-based).
- Se mudar contratos de erro/resultados, atualize `INTERFACES.md` e `converters.py`.
- Mantenha o servidor resiliente: excecoes viram diagnostics, nunca crash.

## 🎯 Funcionalidades

- ✅ **Validação Sintática**: Erros de gramática em tempo real
- ✅ **Validação Semântica**: Campos definidos no template, obrigatórios, tipos, BUNDLE, ARITY
- ✅ **Mensagens Pedagógicas**: Erros com sugestões e explicações
- ✅ **Descoberta Automática**: Carrega templates e bibliografia automaticamente
- ✅ **Fuzzy Matching**: Sugestões para bibrefs não encontrados
- ✅ **Suporte Completo**: Arquivos `.syn`, `.synp`, `.synt`, `.syno`
- ✅ **Semantic Tokens**: Colorização semântica baseada no compilador
- ✅ **Document Symbols**: Outline SOURCE/ITEM/ONTOLOGY
- ✅ **Hover**: Contexto de bibliografia, template e ontologia
- ✅ **Autocomplete**: Bibrefs, códigos e campos
- ✅ **Inlay Hints**: Autor/ano após @bibref
- ✅ **Go-to-Definition**: Bibrefs e códigos
- ✅ **Signature Help**: Definição de campo durante preenchimento
- ✅ **Rename**: Renomeia bibrefs e códigos no workspace
- ✅ **Relation Graph**: Mermaid.js a partir de relações

## 📋 Pré-Requisitos

- Python 3.10+
- Compilador Synesis v1.1 instalado
- Node.js 16+ (apenas para extensão VSCode)

## 🚀 Instalação

### Opção A: Instalar via TestPyPI (teste de publicação)

```bash
python -m pip install -i https://test.pypi.org/simple/ synesis-lsp --extra-index-url https://pypi.org/simple
```

### 1. Instalar o Compilador Synesis

```bash
cd ../Compiler
pip install -e .
```

### 2. Instalar o LSP Server

```bash
cd ../LSP
pip install -e .
```

### 3. Verificar Instalação

```bash
python -m synesis_lsp --help
# ou
synesis-lsp --help
```

## 🔧 Uso

### Como Servidor Standalone

```bash
python -m synesis_lsp
```

O servidor aguarda conexões via STDIO (entrada/saída padrão).

### Com VSCode

A extensão VSCode (incluída em `vscode-extension/`) gerencia o servidor automaticamente.

### Workspace Synesis (Recomendado)

Para validação semantica completa, o workspace deve conter:
- Um arquivo de projeto `*.synp` (obrigatorio)
- Um template `*.synt` referenciado no `.synp`
- Bibliografia `*.bib`, anotacoes `*.syn` e ontologias `*.syno` conforme necessario

Regras:
- Pode haver varios `.synt`, mas o **unico** valido e o definido no `.synp`.
- Sem `.synp`, o LSP faz apenas validacao sintatica e palavras-chave da gramatica.

## 📦 Estrutura do Projeto

```
LSP/
├── synesis_lsp/           # Pacote Python do servidor
│   ├── __init__.py
│   ├── __main__.py        # Entry point (python -m synesis_lsp)
│   ├── server.py          # Servidor principal com pygls
│   └── converters.py      # ValidationError → LSP Diagnostic
│   ├── cache.py           # Workspace cache
│   ├── semantic_tokens.py # Semantic tokens
│   ├── symbols.py         # Document symbols
│   ├── hover.py           # Hover provider
│   ├── definition.py      # Go-to-definition
│   ├── completion.py      # Autocomplete
│   ├── inlay_hints.py      # Inlay hints
│   ├── explorer_requests.py # Custom explorer requests
│   ├── graph.py           # Relation graph (Mermaid)
│   ├── signature_help.py  # Signature help
│   └── rename.py          # Rename provider
│
├── tests/                 # Testes unitários
│   └── test_converters.py
│   ├── test_cache.py
│   ├── test_semantic_tokens.py
│   ├── test_symbols.py
│   ├── test_hover.py
│   ├── test_definition.py
│   ├── test_completion.py
│   ├── test_inlay_hints.py
│   ├── test_explorer_requests.py
│   └── test_server_commands.py
│
├── vscode-extension/      # Extensão VSCode (cliente)
│   ├── src/extension.ts
│   └── package.json
│
├── docs/                  # Documentação de arquitetura
│   └── ADR-002.md         # Decisão arquitetural do LSP
│
├── pyproject.toml         # Configuração do pacote
├── requirements.txt       # Dependências
├── INTERFACES.md          # Contratos Compilador ↔ LSP
├── CHANGELOG.md           # Histórico de mudanças
├── LICENSE                # MIT License
└── README.md              # Este arquivo
```

## 🧪 Testes

```bash
# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Rodar testes
pytest tests/

# Com cobertura
pytest --cov=synesis_lsp tests/
```

## 📦 Publicação (TestPyPI/PyPI)

Veja RELEASING.md para passos de build e upload.

## 🛠️ Desenvolvimento

### Arquitetura

```
┌─────────────┐
│   VSCode    │  (Editor)
└──────┬──────┘
       │ LSP Protocol (JSON-RPC via STDIO)
       ▼
┌─────────────────────────────────┐
│   synesis_lsp.server.py         │  (Servidor Python)
├─────────────────────────────────┤
│ • Handlers: did_open, did_change│
│ • Converters: Error → Diagnostic│
│ • Providers: tokens, symbols,    │
│   hover, completion, definition, │
│   inlay, signature, rename       │
│ • Commands: loadProject, stats,  │
│   explorer, relation graph       │
└──────┬──────────────────────────┘
       │ importa
       ▼
┌─────────────────────────────────┐
│   synesis.lsp_adapter           │  (Adaptador no Compilador)
├─────────────────────────────────┤
│ • validate_single_file()        │
│ • Descoberta de contexto        │
└──────┬──────────────────────────┘
       │ usa
       ▼
┌─────────────────────────────────┐
│   synesis.compiler              │  (Compilador Existente)
├─────────────────────────────────┤
│ • Parser Lark (LALR)            │
│ • SemanticValidator             │
│ • ValidationResult              │
└─────────────────────────────────┘
```

### Princípios de Design (ADR-002)

1. **Fonte Única de Verdade**: O compilador é a única autoridade para validação
2. **Estado Efêmero**: LSP não persiste estado, apenas traduz
3. **Fluxo Unidirecional**: Editor → LSP → Compilador → Diagnósticos
4. **Sem Duplicação**: Zero lógica de validação reimplementada

### Adicionar Novo Tipo de Diagnóstico

1. Criar `ValidationError` no compilador (`synesis/ast/results.py`)
2. Implementar `to_diagnostic()` com mensagem pedagógica
3. O LSP converterá automaticamente via `converters.build_diagnostic()`

### Debugging

```bash
# Com logs detalhados
export PYTHONUNBUFFERED=1
python -m synesis_lsp 2>&1 | tee lsp.log
```

Logs são escritos em `stderr` e capturados pelo VSCode em **Output → Synesis LSP**.

## 🧩 Recursos avançados

- Comandos custom: `synesis/loadProject`, `synesis/getProjectStats`,
  `synesis/getReferences`, `synesis/getCodes`, `synesis/getRelations`,
  `synesis/getRelationGraph`
- Recursos cross-file (hover, definition, completion, rename, graph) dependem
  do cache do workspace carregado via `synesis/loadProject`

## 📚 Dependências

### Runtime
- `pygls>=1.0.0` - Framework LSP em Python
- `lsprotocol>=2023.0.0` - Tipos do protocolo LSP
- `synesis>=1.1.0` - Compilador Synesis (instalado localmente)

### Development
- `pytest>=7.0.0` - Framework de testes
- `pytest-asyncio>=0.20.0` - Suporte async para testes
- `black>=23.0.0` - Formatação de código
- `mypy>=1.0.0` - Type checking

## 🐛 Troubleshooting

### Erro: "Pacote 'synesis' não encontrado"

```bash
cd ../Compiler
pip install -e .
```

### LSP não valida após editar

1. Verifique logs: **Output → Synesis LSP** no VSCode
2. Recarregue janela: `Ctrl+Shift+P` → "Reload Window"
3. Verifique se o `.synp` referencia o template e a bibliografia corretos
4. Procure mensagens: `Projeto Synesis carregado`, `Template carregado`, `Bibliografia carregada`

### Diagnósticos incorretos

O LSP usa **100% do compilador**. Se o diagnóstico está incorreto:
1. Teste com CLI: `synesis check arquivo.syn`
2. Se CLI também reporta incorreto, o bug está no compilador
3. Reporte em: [Synesis Compiler Issues]

## 📄 Licença

MIT License - Synesis Project

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:

1. Siga as convenções de código do `coding_pattern.md`
2. Adicione testes para novos recursos
3. Mantenha documentação atualizada
4. Use type hints completos
5. Mensagens de commit descritivas

## 📖 Referências

- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [pygls Documentation](https://pygls.readthedocs.io/)
- [Synesis v1.1 Specification](../Compiler/index.md)
- [ADR-002: LSP Architecture](docs/ADR-002.md)
- [Interfaces e Contratos](INTERFACES.md)
- [Changelog](CHANGELOG.md)

