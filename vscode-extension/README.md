# Synesis Language Support for VSCode

**Suporte completo à linguagem Synesis v1.1 no Visual Studio Code com validação em tempo real.**

## 🤖 AI INSTRUCTIONS

- A extensao **nao** valida codigo; apenas inicia e conecta o LSP.
- O servidor deve ser iniciado via `python -m synesis_lsp` (config `synesis.pythonPath`).
- Nao adicione parsing/semantica no cliente; mantenha o fluxo LSP padrao.
- Se mudar command/args ou documentSelector, atualize `package.json` e docs.
- Diagnostics sao 0-based; nao tente converter no cliente.

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![VSCode](https://img.shields.io/badge/VSCode-1.75%2B-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

## ✨ Funcionalidades

- ✅ **Syntax Highlighting**: Destaque de sintaxe para arquivos `.syn`, `.synp`, `.synt`, `.syno`
- ✅ **Validação em Tempo Real**: Erros e warnings enquanto você digita
- ✅ **Mensagens Pedagógicas**: Erros com explicações e sugestões
- ✅ **Fuzzy Matching**: Sugestões para bibrefs não encontrados
- ✅ **Descoberta Automática**: Carrega templates e bibliografia automaticamente
- ✅ **Indentação Inteligente**: Auto-indentação para blocos Synesis
- ✅ **Bracket Matching**: Pareamento automático de colchetes

## 📦 Instalação

### Pré-Requisitos

1. **Python 3.10+** instalado
2. **Compilador Synesis** instalado:
   ```bash
   cd path/to/0_Synesis/Compiler
   pip install -e .
   ```
3. **LSP Server** instalado:
   ```bash
   cd path/to/0_Synesis/LSP
   pip install -e .
   ```

### Instalar Extensão

#### Método 1: Desenvolvimento Local

```bash
cd 0_Synesis/LSP/vscode-extension

# Instalar dependências
npm install

# Compilar TypeScript
npm run compile

# Testar no VSCode
# Pressione F5 no VSCode para abrir janela de desenvolvimento
```

#### Método 2: Instalar Pacote .vsix

```bash
cd vscode-extension

# Criar pacote
npm run package

# Instalar no VSCode
code --install-extension synesis-vscode-0.1.0.vsix
```

## 🚀 Uso

### 1. Abrir Workspace Synesis

```bash
code /caminho/para/seu/projeto/synesis
```

**Workspace esperado (para validacao semantica completa):**
- Projeto: `*.synp` (obrigatorio)
- Template: `*.synt` referenciado no `.synp`
- Bibliografia: `*.bib`
- Anotacoes: `*.syn`
- Ontologias: `*.syno`

**Regras:**
- Pode haver varios `.synt`, mas o **unico** valido e o definido no `.synp`.
- Sem `.synp`, o LSP identifica palavras-chave e erros sintaticos, mas nao valida campos.

### 2. Criar/Abrir Arquivo Synesis

Arquivos com extensões `.syn`, `.synp`, `.synt`, `.syno` serão automaticamente reconhecidos.

### 3. Validação Automática

A extensão valida automaticamente quando você:
- Abre um arquivo Synesis
- Edita o arquivo
- Salva o arquivo

### 4. Ver Diagnósticos

- **Erros/Warnings** aparecem sublinhados no editor
- **Lista de Problemas**: `View → Problems` (Ctrl+Shift+M)
- **Output do LSP**: `View → Output` → Selecione "Synesis LSP"

## ⚙️ Configurações

Acesse `Preferences → Settings` e busque por "Synesis":

### `synesis.pythonPath`
**Tipo**: `string`
**Padrão**: `"python3"`

Caminho para o interpretador Python com `synesis-lsp` instalado.
Se nao configurado, a extensao tenta usar `python.defaultInterpreterPath` da extensao Python do VSCode.

**Exemplo**:
```json
{
  "synesis.pythonPath": "${workspaceFolder}/.venv/bin/python"
}
```

### `synesis.trace.server`
**Tipo**: `"off" | "messages" | "verbose"`
**Padrão**: `"off"`

Nível de logging da comunicação LSP.

**Opções**:
- `"off"`: Sem logs
- `"messages"`: Logs de mensagens LSP
- `"verbose"`: Logs detalhados (útil para debug)

### `synesis.validation.enabled`
**Tipo**: `boolean`
**Padrão**: `true`

Ativar/desativar validação em tempo real.

## 📝 Exemplo de Uso

```synesis
PROJECT bibliometrics
    TEMPLATE "bibliometrics.synt"
    INCLUDE BIBLIOGRAPHY "bibliometrics.bib"
    INCLUDE ANNOTATIONS "bibliometrics.syn"
    INCLUDE ONTOLOGY "bibliometrics.syno"
END PROJECT
```

```synesis
PROJECT davi_pesquisa
    TEMPLATE "Davi.synt"
    INCLUDE ANNOTATIONS "Davi.syn"
END PROJECT
```

**Validação em tempo real mostrará**:
- ❌ Erros se o template referenciado no PROJECT nao existir
- ❌ Erros se um campo nao estiver definido no template
- ❌ Erros se campos obrigatórios faltarem
- ⚠️ Avisos se bibrefs não forem encontrados

## 🐛 Troubleshooting

### Extensão não valida arquivos

1. **Verifique instalação do LSP**:
   ```bash
   python3 -m synesis_lsp --help
   ```

2. **Verifique Output**:
   - `View → Output` → Selecione "Synesis LSP"
   - Procure por erros de inicialização

3. **Recarregue janela**:
   - `Ctrl+Shift+P` → "Reload Window"

### Erro: "synesis-lsp not found"

O Python não encontra o pacote. Soluções:

**Opção 1**: Configurar `pythonPath`
```json
{
  "synesis.pythonPath": "/caminho/completo/para/python"
}
```

**Opção 2**: Reinstalar LSP
```bash
cd 0_Synesis/LSP
pip install -e .
```

### Validação lenta em arquivos grandes

A validação recompila o arquivo a cada mudança. Para arquivos muito grandes (>1000 linhas):

1. Desabilite validação temporária:
   ```json
   {
     "synesis.validation.enabled": false
   }
   ```

2. Valide manualmente via CLI quando necessário:
   ```bash
   synesis check arquivo_grande.syn
   ```

### Diagnósticos incorretos

A extensão usa 100% do compilador Synesis. Se o diagnóstico está incorreto:

1. Teste com CLI:
   ```bash
   synesis check arquivo.syn
   ```

2. Se CLI também reporta incorreto, o bug está no compilador

3. Reporte em: [Synesis Compiler Issues]

## 📚 Sintaxe Destacada

A extensão fornece syntax highlighting para:

- **Keywords**: `PROJECT`, `SOURCE`, `ITEM`, `ONTOLOGY`, `TEMPLATE`, `FIELD`
- **Tipos**: `QUOTATION`, `MEMO`, `CODE`, `CHAIN`, `SCALE`, etc.
- **Bibrefs**: `@silva2023` (destacado como tags)
- **Chains**: `->` (destacado como operador)
- **Campos**: `author:`, `title:` (destacado como variável)
- **Comentários**: `# comentário` (destacado como comentário)

## 🔧 Desenvolvimento

### Setup

```bash
git clone <repo>
cd vscode-extension
npm install
```

### Build

```bash
npm run compile
```

### Watch Mode (desenvolvimento)

```bash
npm run watch
```

### Debug

1. Abra `vscode-extension` no VSCode
2. Pressione `F5` para abrir janela de desenvolvimento
3. Abra arquivo `.syn` na janela de desenvolvimento
4. Verifique logs em `Output → Synesis LSP`

### Publicar

```bash
# Criar pacote
npm run package

# Publicar (requer conta no marketplace)
npm run publish
```

## 📄 Licença

MIT License - Synesis Project

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:

1. Fork o repositório
2. Crie branch para feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para branch (`git push origin feature/nova-funcionalidade`)
5. Abra Pull Request

## 🔗 Links

- [Synesis Compiler](https://github.com/synesis-project/compiler)
- [LSP Server](../README.md)
- [Documentação Synesis v1.1](../../Compiler/index.md)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)

## 📧 Suporte

- Issues: [GitHub Issues](https://github.com/synesis-project/synesis-lsp/issues)
- Discussões: [GitHub Discussions](https://github.com/synesis-project/synesis-lsp/discussions)
- Email: support@synesis-project.org

---

**Desenvolvido com ❤️ para pesquisadores qualitativos**
