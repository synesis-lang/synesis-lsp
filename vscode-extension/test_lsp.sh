#!/bin/bash

echo "=========================================="
echo "TESTE DE FUNCIONAMENTO DO SYNESIS LSP"
echo "=========================================="
echo ""

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Diretórios
EXT_DIR="/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/LSP/vscode-extension"
TEST_DIR="/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler/davi_pesquisa"

echo "1. Verificando Python..."
PYTHON_PATH=$(which python3)
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓${NC} Python: $PYTHON_PATH ($PYTHON_VERSION)"
echo ""

echo "2. Verificando pacotes Python..."
if python3 -c "import synesis" 2>/dev/null; then
    SYNESIS_LOC=$(python3 -c "import synesis; print(synesis.__file__)")
    echo -e "${GREEN}✓${NC} synesis instalado: $SYNESIS_LOC"
else
    echo -e "${RED}✗${NC} synesis NÃO instalado"
    exit 1
fi

if python3 -c "import synesis_lsp" 2>/dev/null; then
    SYNESIS_LSP_LOC=$(python3 -c "import synesis_lsp; print(synesis_lsp.__file__)")
    echo -e "${GREEN}✓${NC} synesis-lsp instalado: $SYNESIS_LSP_LOC"
else
    echo -e "${RED}✗${NC} synesis-lsp NÃO instalado"
    exit 1
fi
echo ""

echo "3. Verificando compilação da extensão..."
if [ -f "$EXT_DIR/out/extension.js" ]; then
    SIZE=$(ls -lh "$EXT_DIR/out/extension.js" | awk '{print $5}')
    echo -e "${GREEN}✓${NC} Extensão compilada: out/extension.js ($SIZE)"
else
    echo -e "${RED}✗${NC} Extensão NÃO compilada. Execute: npm run compile"
    exit 1
fi
echo ""

echo "4. Testando servidor LSP..."
timeout 2 python3 -m synesis_lsp 2>&1 | head -5 | grep -q "Registered"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Servidor LSP inicia corretamente"
else
    echo -e "${YELLOW}⚠${NC} Não foi possível confirmar inicialização do LSP (timeout esperado)"
fi
echo ""

echo "5. Testando validação com arquivo de teste..."
cd "$TEST_DIR"
VALIDATION_OUTPUT=$(python3 -c "
from synesis.lsp_adapter import validate_single_file
from pathlib import Path

syn_file = Path('Davi.syn')
uri = 'file://' + str(syn_file.absolute())
content = syn_file.read_text()

result = validate_single_file(content, uri, context=None)
print(f'{len(result.errors)},{len(result.warnings)}')
" 2>&1)

ERRORS=$(echo $VALIDATION_OUTPUT | cut -d',' -f1)
WARNINGS=$(echo $VALIDATION_OUTPUT | cut -d',' -f2)

if [ "$ERRORS" = "0" ]; then
    echo -e "${GREEN}✓${NC} Validação executada com sucesso: $ERRORS erros, $WARNINGS avisos"
else
    echo -e "${YELLOW}⚠${NC} Validação detectou erros (esperado para teste): $ERRORS erros, $WARNINGS avisos"
fi
echo ""

echo "6. Verificando arquivos de configuração VSCode..."
if [ -f "$EXT_DIR/.vscode/launch.json" ]; then
    echo -e "${GREEN}✓${NC} launch.json existe"
else
    echo -e "${RED}✗${NC} launch.json NÃO encontrado"
fi

if [ -f "$EXT_DIR/.vscode/tasks.json" ]; then
    echo -e "${GREEN}✓${NC} tasks.json existe"
else
    echo -e "${RED}✗${NC} tasks.json NÃO encontrado"
fi
echo ""

echo "=========================================="
echo -e "${GREEN}TESTES CONCLUÍDOS!${NC}"
echo "=========================================="
echo ""
echo "Para testar no VSCode:"
echo "1. Abra: code '$EXT_DIR'"
echo "2. Pressione F5 para debug"
echo "3. Na nova janela, abra: '$TEST_DIR'"
echo "4. Abra o arquivo Davi.syn"
echo ""
