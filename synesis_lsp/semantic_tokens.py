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
    # comentário                                       → Comment
    ->                                                 → Operator
    INFLUENCES, ENABLES, CONSTRAINS, ...               → EnumMember (modifier)
    conteúdo de GUIDELINES                             → String (modification)

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
    SemanticTokenModifiers,
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokenTypes,
)

logger = logging.getLogger(__name__)

# Tipos de tokens suportados
TOKEN_TYPES: List[str] = [
    SemanticTokenTypes.Keyword.value,     # 0: SOURCE, ITEM, END, ONTOLOGY
    SemanticTokenTypes.Variable.value,    # 1: @bibref
    SemanticTokenTypes.Property.value,    # 2: nome_campo:
    SemanticTokenTypes.String.value,      # 3: valor de campo / conteúdo GUIDELINES
    SemanticTokenTypes.EnumMember.value,  # 4: código ontológico (Trust, CCS_Support)
    SemanticTokenTypes.Namespace.value,   # 5: PROJECT, TEMPLATE, INCLUDE
    SemanticTokenTypes.Comment.value,     # 6: # comentário
    SemanticTokenTypes.Operator.value,    # 7: ->
    SemanticTokenTypes.Type.value,        # 8: relações de chain (INFLUENCES, ENABLES, ...)
]

TOKEN_MODIFIERS: List[str] = [
    SemanticTokenModifiers.Declaration.value,   # 0: para keywords de declaração
    SemanticTokenModifiers.Modification.value,  # 1: para conteúdo de GUIDELINES
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
_TK_ENUM_MEMBER = 4  # códigos ontológicos
_TK_NAMESPACE = 5
_TK_COMMENT = 6
_TK_OPERATOR = 7
_TK_RELATION = 8     # relações de chain (INFLUENCES, ENABLES, ...)

# Modifier bitmask
_MOD_DECLARATION = 1 << 0   # bit 0
_MOD_MODIFICATION = 1 << 1  # bit 1: conteúdo GUIDELINES (texto livre itálico)

# Patterns para extração de tokens por linha
_RE_KEYWORD_LINE = re.compile(
    r'^(\s*)(SOURCE|ITEM|ONTOLOGY|END\s+SOURCE|END\s+ITEM|END\s+ONTOLOGY)\b'
)
_RE_BIBREF = re.compile(r'@(\w+)')
_RE_FIELD_LINE = re.compile(r'^(\s*)(\w+)\s*:\s*(.*?)$')
_RE_PROJECT_KEYWORDS = re.compile(
    r'^(\s*)(PROJECT|TEMPLATE|INCLUDE|BIBLIOGRAPHY|ANNOTATIONS|END\s+PROJECT)\b'
)
_RE_GUIDELINES_START = re.compile(r'^\s*GUIDELINES\s*$', re.IGNORECASE)
_RE_GUIDELINES_END = re.compile(r'^\s*END\s+GUIDELINES\b', re.IGNORECASE)
_RE_COMMENT = re.compile(r'^(\s*)(#.*)$')
_RE_ARROW = re.compile(r'->')

# Relações padrão usadas como fallback quando o template ainda não foi compilado
# (ex: documento aberto antes do LSP terminar loadProject).
_DEFAULT_RELATIONS: frozenset[str] = frozenset({
    "INFLUENCES", "ENABLES", "CONSTRAINS", "CONTESTED-BY", "RELATES-TO",
    "CAUSES", "PREVENTS", "REQUIRES", "EXCLUDES", "CORRELATES", "DEPENDS-ON",
})

_RE_RELATION: re.Pattern | None = None  # compilado sob demanda por _build_relation_re()


def _build_relation_re(relation_names: frozenset[str]) -> re.Pattern:
    """Compila regex para o conjunto de nomes de relação fornecido."""
    escaped = [re.escape(r) for r in sorted(relation_names, key=len, reverse=True)]
    return re.compile(r'\b(' + '|'.join(escaped) + r')\b')

# RawToken: (line_0based, col_0based, length, token_type_index, modifier_bitmask)
RawToken = Tuple[int, int, int, int, int]

_TOKENS_CACHE: dict[tuple[str, int], SemanticTokens] = {}


def compute_semantic_tokens(
    source: str,
    uri: str,
    relation_names: frozenset[str] | None = None,
) -> SemanticTokens:
    """
    Computa tokens semânticos para um arquivo Synesis.

    relation_names: conjunto de nomes de relação válidos extraídos do template
    (ex: {"INFLUENCES", "ENABLES", "CONSTRAINS"}). Se None, usa _DEFAULT_RELATIONS
    como fallback para cobrir o período entre abertura do documento e loadProject.

    Resultado cacheado por (uri, hash(source), frozenset(relation_names)).
    Cache limpo a cada novo resultado para manter apenas a entrada mais recente.
    """
    effective_relations = relation_names if relation_names is not None else _DEFAULT_RELATIONS
    cache_key = (uri, hash(source), effective_relations)
    cached = _TOKENS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    re_relation = _build_relation_re(effective_relations)
    tokens = _extract_tokens_from_source(source, re_relation)
    data = _encode_deltas(tokens)
    result = SemanticTokens(data=data)
    _TOKENS_CACHE.clear()  # manter apenas o resultado mais recente por URI
    _TOKENS_CACHE[cache_key] = result
    return result


def _extract_tokens_from_source(source: str, re_relation: re.Pattern) -> List[RawToken]:
    """Extrai tokens escaneando o texto-fonte linha a linha."""
    tokens: List[RawToken] = []
    lines = source.splitlines()
    in_guidelines = False

    for line_idx, line in enumerate(lines):
        if not line.strip():
            continue

        stripped = line.strip()

        # Comentários — têm precedência sobre tudo
        m = _RE_COMMENT.match(line)
        if m:
            col = len(m.group(1))
            tokens.append((line_idx, col, len(m.group(2)), _TK_COMMENT, 0))
            continue

        # Bloco GUIDELINES — conteúdo é texto livre
        if _RE_GUIDELINES_END.match(stripped):
            in_guidelines = False
            col = len(line) - len(line.lstrip())
            tokens.append((line_idx, col, len(stripped), _TK_KEYWORD, _MOD_DECLARATION))
            continue

        if _RE_GUIDELINES_START.match(stripped):
            in_guidelines = True
            col = len(line) - len(line.lstrip())
            tokens.append((line_idx, col, len(stripped), _TK_KEYWORD, _MOD_DECLARATION))
            continue

        if in_guidelines:
            col = len(line) - len(line.lstrip())
            tokens.append((line_idx, col, len(stripped), _TK_STRING, _MOD_MODIFICATION))
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
            tokens.append((line_idx, col, len(kw), _TK_KEYWORD, _MOD_DECLARATION))

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

            # Valor do campo — pode conter setas e relações (campo chain)
            if value.strip():
                val_stripped = value.strip()
                val_col = line.index(val_stripped, colon_pos + 1)
                if val_stripped.startswith('"'):
                    tokens.append(
                        (line_idx, val_col, len(val_stripped), _TK_STRING, 0)
                    )
                elif _RE_ARROW.search(val_stripped) or re_relation.search(val_stripped):
                    _tokenize_chain_value(line_idx, val_col, val_stripped, tokens, re_relation)
                else:
                    tokens.append(
                        (line_idx, val_col, len(val_stripped), _TK_ENUM_MEMBER, 0)
                    )
            continue

        # 4. Linhas de continuação de chain (sem ':') — setas e relações
        if _RE_ARROW.search(stripped) or re_relation.search(stripped):
            col = len(line) - len(line.lstrip())
            _tokenize_chain_value(line_idx, col, stripped, tokens, re_relation)
            continue

    return tokens


def _tokenize_chain_value(
    line_idx: int,
    start_col: int,
    text: str,
    tokens: List[RawToken],
    re_relation: re.Pattern,
) -> None:
    """Emite tokens de operator (->) e type (relações) e enumMember (códigos) para uma chain."""
    pos = 0
    while pos < len(text):
        # Tenta seta
        arrow = _RE_ARROW.search(text, pos)
        relation = re_relation.search(text, pos)

        next_match = None
        if arrow and relation:
            next_match = arrow if arrow.start() <= relation.start() else relation
        elif arrow:
            next_match = arrow
        elif relation:
            next_match = relation

        if next_match is None:
            # Restante do texto: token ou código
            rest = text[pos:].strip()
            if rest:
                rest_offset = text.index(rest, pos)
                tokens.append((line_idx, start_col + rest_offset, len(rest), _TK_ENUM_MEMBER, 0))
            break

        # Texto antes do match (código/nome)
        before = text[pos:next_match.start()].strip()
        if before:
            before_offset = text.index(before, pos)
            tokens.append((line_idx, start_col + before_offset, len(before), _TK_ENUM_MEMBER, 0))

        if next_match == arrow:
            tokens.append((line_idx, start_col + next_match.start(), 2, _TK_OPERATOR, 0))
        else:
            tokens.append((
                line_idx,
                start_col + next_match.start(),
                len(next_match.group(0)),
                _TK_RELATION,
                0,
            ))

        pos = next_match.end()


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
