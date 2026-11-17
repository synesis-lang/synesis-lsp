"""Estrutura do documento de um .synp: questões e blocos EXPORT sob o PROJECT.

Etapa Q do plano ROLE/EXPORT. Com um compilador anterior ao bloco QUESTIONS, o
PROJECT continua sem filhos, como antes.
"""

from __future__ import annotations

import pytest

from synesis_lsp.symbols import compute_document_symbols


def _compiler_has_questions() -> bool:
    import synesis.ast.nodes as nodes

    return hasattr(nodes, "QuestionNode")


SYNP = """\
PROJECT fraudes
TEMPLATE "fraudes.synt"

QUESTIONS
    Q1: Quais taticas aparecem em cada canal?
    Q2: Quais evidencias tratam de phishing?
END QUESTIONS

EXPORT JSON painel
    OUTPUT "saida/fraudes.json"
END EXPORT
END PROJECT
"""


@pytest.mark.skipif(not _compiler_has_questions(), reason="synesis sem o bloco QUESTIONS")
def test_questions_and_exports_are_project_children():
    symbols = compute_document_symbols(SYNP, "file:///tmp/fraudes.synp")
    project = next(s for s in symbols if s.name == "PROJECT fraudes")
    names = [c.name for c in project.children or []]
    assert names == ["Q1", "Q2", "EXPORT JSON painel"]
    q1 = project.children[0]
    assert q1.detail == "Quais taticas aparecem em cada canal?"
    assert q1.range.start.line == 4
    assert project.children[2].detail == "saida/fraudes.json"


def test_project_without_blocks_has_no_children():
    symbols = compute_document_symbols(
        'PROJECT p\nTEMPLATE "t.synt"\nEND PROJECT\n', "file:///tmp/p.synp"
    )
    project = next(s for s in symbols if s.name.startswith("PROJECT"))
    assert not project.children
