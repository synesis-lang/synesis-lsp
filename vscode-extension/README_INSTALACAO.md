# Instalação e Teste da Extensão Synesis VSCode

## 📋 Pré-requisitos

✅ Todos os pré-requisitos estão instalados:
- Python 3.12.10
- Pacote `synesis` (compilador)
- Pacote `synesis-lsp` (servidor LSP)
- Node.js e npm
- Extensão compilada

## 🚀 Método 1: Modo Debug (Recomendado para Desenvolvimento)

Este é o método mais rápido para testar mudanças durante o desenvolvimento.

### Passo 1: Abra o projeto da extensão

```bash
code "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"
```

### Passo 2: Inicie o Debug

1. Pressione **F5** (ou vá em Run > Start Debugging)
2. Uma nova janela do VSCode será aberta com "[Extension Development Host]" no título
3. Essa janela tem a extensão Synesis carregada

### Passo 3: Abra o Projeto de Teste

Na janela de desenvolvimento:
1. File > Open Folder
2. Navegue para: `Compiler/davi_pesquisa`
3. Abra o arquivo `Davi.syn`

### Passo 4: Verifique o Funcionamento

Você deve ver:

1. **Output do Servidor:**
   - View > Output
   - Selecione "Synesis LSP" no dropdown
   - Você verá: "Documento aberto: file://..."

2. **No arquivo Davi.syn:**
   - Syntax highlighting (se configurado)
   - A extensão detectará o arquivo como linguagem Synesis

3. **Teste validação:**
   - Adicione um erro proposital (ex: campo inexistente)
   - Salve o arquivo
   - Veja o erro aparecer no painel "Problems"

## 📦 Método 2: Instalar como Extensão

Para usar a extensão normalmente no VSCode:

### Passo 1: Empacotar a Extensão

```bash
cd "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"
npm run package
```

Isso criará: `synesis-vscode-0.1.0.vsix`

### Passo 2: Instalar

1. Abra VSCode
2. View > Extensions (Cmd+Shift+X)
3. Clique no menu "..." (três pontos) no topo
4. Selecione "Install from VSIX..."
5. Escolha o arquivo `synesis-vscode-0.1.0.vsix`

### Passo 3: Recarregar e Testar

1. Recarregue VSCode (Cmd+Shift+P > "Reload Window")
2. Abra a pasta `Compiler/davi_pesquisa`
3. Abra `Davi.syn`

## ⚙️ Configurações Disponíveis

Abra Settings (Cmd+,) e procure "synesis":

### 1. Python Path
**Configuração:** `synesis.pythonPath`
- Caminho para o interpretador Python
- Padrão: `python3`
- Exemplo: `${workspaceFolder}/.venv/bin/python3`

### 2. Trace do Servidor (CORRIGIDO) ✨
**Configuração:** `synesisLanguageServer.trace.server`
- Controla logs de comunicação LSP
- Opções: `off`, `messages`, `verbose`
- Padrão: `off`

**Como usar:**
1. Configure para "verbose"
2. Recarregue VSCode
3. View > Output > Synesis LSP
4. Você verá toda comunicação entre cliente e servidor

### 3. Habilitar/Desabilitar Validação (NOVO) ✨
**Configuração:** `synesis.validation.enabled`
- Liga/desliga validação em tempo real
- Tipo: boolean
- Padrão: `true`

**Como usar:**
1. Desmarque a opção em Settings
2. Os diagnósticos desaparecem imediatamente
3. Marque novamente para reativar

## 🧪 Testando as Correções

### Teste 1: Trace Funcionando

```json
// settings.json
{
  "synesisLanguageServer.trace.server": "verbose"
}
```

Após recarregar, você verá no Output:
```
Sending request 'initialize - (0)'
Received response 'initialize - (0)' in 5ms
```

### Teste 2: Validação On/Off

```json
// settings.json
{
  "synesis.validation.enabled": false
}
```

Sem recarregar, os diagnósticos devem desaparecer instantaneamente.

## 🐛 Troubleshooting

### Problema: "Extensão não está funcionando"

Execute o script de diagnóstico:
```bash
"/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension/test_lsp.sh"
```

### Problema: "Python não encontrado"

Configure o caminho manualmente:
```json
{
  "synesis.pythonPath": "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
}
```

### Problema: "Servidor não inicia"

1. Verifique logs: View > Output > Synesis LSP
2. Verifique Developer Tools: Help > Toggle Developer Tools
3. Procure erros na aba Console

### Problema: "Diagnósticos não aparecem"

1. Verifique se o arquivo tem extensão correta (`.syn`, `.synp`, `.synt`, `.syno`)
2. Verifique se há um arquivo `.synp` no diretório
3. Verifique se `synesis.validation.enabled` está `true`

## 📝 Arquivos Importantes

- `package.json` - Manifesto da extensão (configurações, comandos)
- `src/extension.ts` - Cliente LSP (ponte VSCode ↔ Servidor)
- `out/extension.js` - Código compilado
- `.vscode/launch.json` - Configuração de debug
- `.vscode/tasks.json` - Tarefas de build

## 🔄 Workflow de Desenvolvimento

1. **Edite código TypeScript:** `src/extension.ts`
2. **Compile:** `npm run compile` (ou use watch mode: `npm run watch`)
3. **Teste:** Pressione F5 para recarregar extensão em debug
4. **Verifique logs:** Output > Synesis LSP
5. **Itere:** Faça mudanças e repita

## ✅ Status das Correções

| Problema | Status | Arquivo |
|----------|--------|---------|
| trace.server quebrado | ✅ Corrigido | package.json:62, extension.ts:120 |
| validation.enabled ignorado | ✅ Implementado | server.py:227-277 |
| Docstring desatualizada | ✅ Corrigido | server.py:21-26 |

## 📚 Documentação Adicional

- **Guia de debug detalhado:** [TESTE_DEBUG.md](TESTE_DEBUG.md)
- **Documentação do projeto:** [../../SYNESIS.md](../../SYNESIS.md)
- **LSP Protocol:** https://microsoft.github.io/language-server-protocol/
