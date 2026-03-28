from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from app.core.config import Settings


@pytest.mark.rag_light
def test_rag_config_defaults_present():
    cfg = Settings()
    assert cfg.rag_chunk_size == 800
    assert cfg.rag_chunk_overlap == 120
    assert cfg.rag_recall_k == 24
    assert cfg.rag_final_k == 6
    assert cfg.rag_sparse_k == 12
    assert cfg.rag_threshold_diversify_enabled is True
    assert cfg.rag_hybrid_enabled is False
    assert cfg.rag_rerank_enabled is False
    assert cfg.rag_rerank_timeout_ms == 300
    assert cfg.rag_context_budget_tokens == 2200
    assert cfg.rag_ingest_dedup_enabled is True
