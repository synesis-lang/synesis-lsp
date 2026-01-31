#!/bin/bash
# Wrapper Python para Extensão Synesis VSCode
# Adiciona o compilador Synesis ao PYTHONPATH antes de executar python3

COMPILER_PATH="/Users/debritto/Library/CloudStorage/GoogleDrive-cristianidade@gmail.com/Meu Drive/OneDrive/PÓS DOUTORADO/Bibliometria/0_Synesis/Compiler"

export PYTHONPATH="${COMPILER_PATH}:${PYTHONPATH}"

exec python3 "$@"
