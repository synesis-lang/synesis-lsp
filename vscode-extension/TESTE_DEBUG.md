# Guia de Teste e Debug da Extensão Synesis LSP

## Status da Correção

✅ **Problemas corrigidos:**
1. Configuração `trace.server` renomeada de `synesis.trace.server` → `synesisLanguageServer.trace.server`
2. Implementado `synesis.validation.enabled` com handler de configuração
3. Docstring atualizada (removida referência incorreta a debounce)

✅ **Verificações concluídas:**
- Pacotes Python instalados: `synesis` e `synesis-lsp`
- Extensão TypeScript compilada sem erros
- Servidor LSP inicia corretamente
- Compilador detecta erros no arquivo Davi.syn

## Como Testar a Extensão

### Método 1: Testar em Modo Debug (Recomendado)

1. **Abra o projeto da extensão no VSCode:**
   ```bash
   code "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"
   ```

2. **Execute a extensão em modo debug:**
   - Pressione `F5` ou vá em `Run > Start Debugging`
   - Uma nova janela do VSCode será aberta com a extensão carregada

3. **Na nova janela, abra o projeto de teste:**
   - File > Open Folder
   - Navegue para: `Compiler/davi_pesquisa`
   - Abra o arquivo `Davi.syn`

4. **Verifique os diagnósticos:**
   - A extensão deve mostrar squiggles (sublinhados) nos erros
   - Abra "Problems" panel (View > Problems) para ver os erros

5. **Verifique os logs do servidor:**
   - Na janela de debug, abra "Output" panel
   - Selecione "Synesis LSP" no dropdown
   - Você deve ver mensagens como "Documento aberto: file://..."

### Método 2: Instalar Localmente

1. **Empacote a extensão:**
   ```bash
   cd "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"
   npm run package
   ```

2. **Instale o pacote .vsix:**
   - No VSCode: Extensions > ... (menu) > Install from VSIX
   - Selecione o arquivo `synesis-vscode-0.1.0.vsix` gerado

3. **Recarregue o VSCode e teste:**
   - Abra a pasta `Compiler/davi_pesquisa`
   - Abra `Davi.syn`

## Testando Configurações Novas

### Teste 1: Trace do Servidor

1. Abra Settings (Cmd+,)
2. Procure por "synesis"
3. Configure `Synesis Language Server > Trace: Server` para "verbose"
4. Recarregue VSCode
5. Abra Output > Synesis LSP
6. Você deve ver comunicação detalhada entre cliente e servidor

### Teste 2: Desabilitar Validação

1. Abra Settings (Cmd+,)
2. Procure por "synesis validation"
3. Desmarque `Synesis > Validation: Enabled`
4. Observe que os diagnósticos desaparecem
5. Marque novamente e eles devem reaparecer

## Problemas Conhecidos Resolvidos

### ❌ Antes:
- `synesis.trace.server` não funcionava (mismatch com clientId)
- `synesis.validation.enabled` era ignorada
- Docstring mencionava debounce inexistente

### ✅ Agora:
- `synesisLanguageServer.trace.server` funciona corretamente
- `synesis.validation.enabled` controla validação em tempo real
- Documentação precisa e consistente

## Verificação Manual do Compilador

Para testar o compilador diretamente (sem VSCode):

```bash
cd "/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler/davi_pesquisa"

python3 -c "
from synesis.lsp_adapter import validate_single_file
from pathlib import Path

syn_file = Path('Davi.syn')
uri = 'file://' + str(syn_file.absolute())
content = syn_file.read_text()

result = validate_single_file(content, uri, context=None)
print(f'Errors: {len(result.errors)}')
print(f'Warnings: {len(result.warnings)}')
for err in result.errors[:5]:
    print(f'  - {err}')
"
```

## Se Ainda Não Funcionar

Verifique:

1. **Python correto:**
   ```bash
   which python3
   python3 --version
   ```

2. **Extensão compilada:**
   ```bash
   ls -la out/extension.js
   ```

3. **Logs do servidor:**
   - Output > Synesis LSP
   - Procure por mensagens de erro

4. **Developer Tools:**
   - Na janela de debug: Help > Toggle Developer Tools
   - Console tab > procure erros JavaScript
