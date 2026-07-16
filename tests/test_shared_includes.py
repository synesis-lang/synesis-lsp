"""test_shared_includes.py - Etapa 5: indice reverso e fingerprint dos INCLUDE SHARED.

Cobre o defeito que a Etapa 3 introduziu no LSP: a ontologia compartilhada vive
FORA da raiz do workspace, entao o os.walk do fingerprint nao a via — editar a
ontologia nao invalidava o cache e o loadProject devolvia dado obsoleto.

Cobre tambem o indice reverso `alvo -> projetos`, que o watcher da extensao usa
para saber QUAIS projetos invalidar quando um alvo muda.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from synesis_lsp.server import _compute_workspace_fingerprint, _shared_includes_payload
from synesis_lsp.shared_includes import (
    build_shared_include_index,
    shared_targets_fingerprint,
)

# Fixtures reais da Etapa 3, no repo do compilador.
SYNESIS_FIXTURES = Path(r"d:\GitHub\synesis\tests\fixtures")
SHARED_PROJECT = SYNESIS_FIXTURES / "T23-Shared-Ontology" / "projeto"
SHARED_TARGET = SYNESIS_FIXTURES / "T23-Shared-Ontology" / "shared" / "vocabulario.syno"
LEGACY_PROJECT = SYNESIS_FIXTURES / "Basic"

pytestmark = pytest.mark.skipif(
    not SHARED_PROJECT.exists(),
    reason="fixtures do compilador (T23) indisponiveis",
)


# ---------------------------------------------------------------------------
# Indice reverso
# ---------------------------------------------------------------------------


def test_index_maps_target_to_project():
    index = build_shared_include_index(SHARED_PROJECT)
    projects = index.projects_for(SHARED_TARGET)
    assert [p.name for p in projects] == ["t23.synp"]


def test_index_lists_the_external_target():
    index = build_shared_include_index(SHARED_PROJECT)
    assert [t.name for t in index.all_targets()] == ["vocabulario.syno"]


def test_index_empty_for_project_without_shared():
    """Projeto legado nao paga custo nenhum."""
    index = build_shared_include_index(LEGACY_PROJECT)
    assert index.is_empty()
    assert index.all_targets() == []


def test_projects_for_unknown_target_is_empty():
    index = build_shared_include_index(SHARED_PROJECT)
    assert index.projects_for(Path("nao/existe.syno")) == []


def test_index_survives_unparseable_synp(tmp_path):
    """Um .synp quebrado nao pode derrubar o indice (nem o servidor)."""
    (tmp_path / "quebrado.synp").write_text("PROJECT sem fim", encoding="utf-8")
    index = build_shared_include_index(tmp_path)
    assert index.is_empty()


def test_index_ignores_non_shared_ontology(tmp_path):
    """INCLUDE ONTOLOGY comum (sem SHARED) nao entra no indice."""
    (tmp_path / "p.synp").write_text(
        'PROJECT p\n\nTEMPLATE "t.synt"\nINCLUDE ONTOLOGY "local.syno"\n\nEND PROJECT\n',
        encoding="utf-8",
    )
    assert build_shared_include_index(tmp_path).is_empty()


# ---------------------------------------------------------------------------
# Fingerprint — o bug que o watcher sozinho nao resolveria
# ---------------------------------------------------------------------------


def test_fingerprint_detects_shared_ontology_edit():
    """O defeito central: editar a ontologia externa DEVE mudar o fingerprint."""
    before = _compute_workspace_fingerprint(SHARED_PROJECT)
    original = os.path.getmtime(SHARED_TARGET)
    try:
        os.utime(SHARED_TARGET, (time.time() + 60, time.time() + 60))
        after = _compute_workspace_fingerprint(SHARED_PROJECT)
        assert before != after, "fingerprint ignorou a edicao da ontologia SHARED"
    finally:
        os.utime(SHARED_TARGET, (original, original))


def test_fingerprint_unchanged_for_legacy_project():
    """NAO-REGRESSAO: sem SHARED, o fingerprint nao ganha sufixo."""
    fp = _compute_workspace_fingerprint(LEGACY_PROJECT)
    assert "|" not in fp


def test_fingerprint_is_stable_between_calls():
    a = _compute_workspace_fingerprint(SHARED_PROJECT)
    b = _compute_workspace_fingerprint(SHARED_PROJECT)
    assert a == b


def test_shared_fingerprint_empty_when_no_targets():
    assert shared_targets_fingerprint(build_shared_include_index(LEGACY_PROJECT)) == ""


def test_missing_target_counts_as_zero(tmp_path):
    """Alvo ausente entra como 0.0 — criar o arquivo depois muda o fingerprint."""
    (tmp_path / "p.synp").write_text(
        'PROJECT p\n\nTEMPLATE "t.synt"\n'
        'INCLUDE SHARED ONTOLOGY "../fora/ainda_nao_existe.syno"\n\nEND PROJECT\n',
        encoding="utf-8",
    )
    index = build_shared_include_index(tmp_path)
    fp = shared_targets_fingerprint(index)
    assert fp != ""
    assert ":0.0" in fp


# ---------------------------------------------------------------------------
# Payload do loadProject (o que a extensao consome para instalar watchers)
# ---------------------------------------------------------------------------


def test_payload_carries_target_and_projects():
    payload = _shared_includes_payload(SHARED_PROJECT)
    assert len(payload) == 1
    entry = payload[0]
    assert entry["target"].endswith("vocabulario.syno")
    assert entry["projects"][0].endswith("t23.synp")


def test_payload_is_empty_for_legacy_project():
    assert _shared_includes_payload(LEGACY_PROJECT) == []


def test_payload_is_json_serializable():
    import json

    json.dumps(_shared_includes_payload(SHARED_PROJECT))
