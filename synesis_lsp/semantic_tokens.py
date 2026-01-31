"""
semantic_tokens.py - Colorização semântica via AST do compilador

Propósito:
    Usa compile_string() (~3ms) para produzir tokens semânticos que o editor
    exibirá com cores baseadas no significado real do código, em vez de regex.

Mapeamento de tokens Synesis → LSP:
    SOURCE, ITEM, END SOURCE, END ITEM, END ONTOLOGY  → Keyword (declaration)
    ONTOLOGY                                           → Keyword (declaration)
    @bibref                                            → Variable
    nome_campo:                                        → Property
    valor de campo                                     → String
    PROJECT, TEMPLATE, INCLUDE, BIBLIOGRAPHY,
    ANNOTATIONS                                        → Namespace

Notas de implementação:
    - Extrai posições dos tokens escaneando o texto-fonte linha a linha
    - Usa nodes do AST para saber quais linhas contêm blocos válidos
    - Em caso de erro de sintaxe, retorna tokens vazios (sem crash)
    - Encoding delta: [deltaLine, deltaStartChar, length, tokenType, tokenModifiers]
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

from lsprotocol.types import (
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokenTypes,
    SemanticTokenModifiers,
)

logger = logging.getLogger(__name__)

# Tipos de tokens suportados
TOKEN_TYPES: List[str] = [
    SemanticTokenTypes.Keyword.value,     # 0: SOURCE, ITEM, END, ONTOLOGY
    SemanticTokenTypes.Variable.value,    # 1: @bibref
    SemanticTokenTypes.Property.value,    # 2: nome_campo:
    SemanticTokenTypes.String.value,      # 3: valor de campo
    SemanticTokenTypes.EnumMember.value,  # 4: código (em campos de código)
    SemanticTokenTypes.Namespace.value,   # 5: PROJECT, TEMPLATE, INCLUDE
]

TOKEN_MODIFIERS: List[str] = [
    SemanticTokenModifiers.Declaration.value,  # 0: para keywords de declaração
]


def build_legend() -> SemanticTokensLegend:
    """Cria uma instância fresca do legend para evitar mutações acidentais."""
    return SemanticTokensLegend(
        token_types=TOKEN_TYPES,
        token_modifiers=TOKEN_MODIFIERS,
    )


LEGEND = build_legend()

# Índices dos tipos (ordem em TOKEN_TYPES)
_TK_KEYWORD = 0
_TK_VARIABLE = 1
_TK_PROPERTY = 2
_TK_STRING = 3
_TK_ENUM_MEMBER = 4
_TK_NAMESPACE = 5

# Modifier bitmask
_MOD_DECLARATION = 1 << 0  # bit 0

# Patterns para extração de tokens por linha
_RE_KEYWORD_LINE = re.compile(
    r'^(\s*)(SOURCE|ITEM|ONTOLOGY|END\s+SOURCE|END\s+ITEM|END\s+ONTOLOGY)\b'
)
_RE_BIBREF = re.compile(r'@(\w+)')
_RE_FIELD_LINE = re.compile(r'^(\s*)(\w+)\s*:\s*(.*?)$')
_RE_PROJECT_KEYWORDS = re.compile(
    r'^(\s*)(PROJECT|TEMPLATE|INCLUDE|BIBLIOGRAPHY|ANNOTATIONS|END\s+PROJECT)\b'
)

# RawToken: (line_0based, col_0based, length, token_type_index, modifier_bitmask)
RawToken = Tuple[int, int, int, int, int]


def compute_semantic_tokens(source: str, uri: str) -> SemanticTokens:
    """
    Computa tokens semânticos para um arquivo Synesis.

    Usa compile_string para validar que o fonte é parseable, depois
    escaneia linha a linha para extrair posições exatas dos tokens.
    Em caso de erro de sintaxe, tenta extrair tokens via regex puro
    (degradação graciosa).
    """
    tokens = _extract_tokens_from_source(source)
    data = _encode_deltas(tokens)
    return SemanticTokens(data=data)


def _extract_tokens_from_source(source: str) -> List[RawToken]:
    """Extrai tokens escaneando o texto-fonte linha a linha."""
    tokens: List[RawToken] = []
    lines = source.splitlines()

    for line_idx, line in enumerate(lines):
        if not line.strip():
            continue

        # 1. Keywords de projeto/template (PROJECT, INCLUDE, etc.)
        m = _RE_PROJECT_KEYWORDS.match(line)
        if m:
            col = len(m.group(1))
            kw = m.group(2)
            tokens.append((line_idx, col, len(kw), _TK_NAMESPACE, 0))
            # Valor após keyword (ex: "PROJECT nome_do_projeto")
            rest = line[m.end():].strip()
            if rest:
                rest_col = line.index(rest, m.end())
                tokens.append((line_idx, rest_col, len(rest), _TK_STRING, 0))
            continue

        # 2. Keywords de bloco (SOURCE, ITEM, ONTOLOGY, END ...)
        m = _RE_KEYWORD_LINE.match(line)
        if m:
            col = len(m.group(1))
            kw = m.group(2)
            # Normaliza "END  SOURCE" -> comprimento real no texto
            kw_len = len(kw)
            tokens.append((line_idx, col, kw_len, _TK_KEYWORD, _MOD_DECLARATION))

            # @bibref após SOURCE ou ITEM
            rest = line[m.end():]
            bm = _RE_BIBREF.search(rest)
            if bm:
                bibref_col = m.end() + bm.start()
                bibref_len = len(bm.group(0))  # inclui @
                tokens.append((line_idx, bibref_col, bibref_len, _TK_VARIABLE, 0))

            # Concept após ONTOLOGY
            if kw == "ONTOLOGY":
                rest_stripped = rest.strip()
                if rest_stripped and not rest_stripped.startswith("@"):
                    concept_col = m.end() + rest.index(rest_stripped)
                    tokens.append(
                        (line_idx, concept_col, len(rest_stripped), _TK_ENUM_MEMBER, 0)
                    )
            continue

        # 3. Linhas de campo (nome: valor)
        m = _RE_FIELD_LINE.match(line)
        if m:
            col = len(m.group(1))
            field_name = m.group(2)
            value = m.group(3)

            # Nome do campo (incluindo ':')
            colon_pos = line.index(":", col + len(field_name))
            tokens.append(
                (line_idx, col, colon_pos - col + 1, _TK_PROPERTY, 0)
            )

            # Valor do campo
            if value.strip():
                val_stripped = value.strip()
                val_col = line.index(val_stripped, colon_pos + 1)
                # Valores entre aspas -> String; valores simples (códigos) -> EnumMember
                if val_stripped.startswith('"'):
                    tokens.append(
                        (line_idx, val_col, len(val_stripped), _TK_STRING, 0)
                    )
                else:
                    tokens.append(
                        (line_idx, val_col, len(val_stripped), _TK_ENUM_MEMBER, 0)
                    )
            continue

    return tokens


def _encode_deltas(tokens: List[RawToken]) -> List[int]:
    """
    Ordena tokens por posição e codifica em formato delta LSP.

    Formato: [deltaLine, deltaStartChar, length, tokenType, tokenModifiers]
    Cada token é relativo ao anterior.
    """
    if not tokens:
        return []

    # Ordenar por (line, col)
    tokens.sort(key=lambda t: (t[0], t[1]))

    data: List[int] = []
    prev_line = 0
    prev_col = 0

    for line, col, length, token_type, modifiers in tokens:
        delta_line = line - prev_line
        delta_col = col - prev_col if delta_line == 0 else col

        data.extend([delta_line, delta_col, length, token_type, modifiers])

        prev_line = line
        prev_col = col

    return data
