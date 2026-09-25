"""Checkpoint da avaliação não mistura configurações diferentes."""

from __future__ import annotations

import pytest

from evaluation import run_evaluation


@pytest.fixture
def checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evaluation, "_CHECKPOINT_PATH", tmp_path / "ckpt.json")
    dataset = tmp_path / "ds.json"
    dataset.write_text("[1]", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt v1", encoding="utf-8")
    monkeypatch.setattr(run_evaluation, "_PROMPT_FILES", (prompt,))
    run_evaluation._save_checkpoint(dataset, 1, {"PR-1": []})
    return dataset, prompt


def test_checkpoint_da_mesma_configuracao_e_retomado(checkpoint):
    dataset, _ = checkpoint
    assert run_evaluation._load_checkpoint(dataset, 1) == {"PR-1": []}


def test_checkpoint_e_descartado_se_o_dataset_mudou(checkpoint):
    dataset, _ = checkpoint
    dataset.write_text("[1, 2]", encoding="utf-8")
    assert run_evaluation._load_checkpoint(dataset, 1) == {}


def test_checkpoint_e_descartado_se_o_prompt_mudou(checkpoint):
    dataset, prompt = checkpoint
    prompt.write_text("prompt v2", encoding="utf-8")
    assert run_evaluation._load_checkpoint(dataset, 1) == {}
