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


def test_results_salvam_linhas_e_deteccoes_de_cada_pr(tmp_path):
    import json

    from evaluation.metrics import AggregatedEvaluation, LineResult, RepetitionResult

    linha = LineResult(
        pr_id="PR-1", line="x = 1", expected_viola=False, regra=None,
        sub_regra=None, hard_negative=False, signaled=True, cell="FP",
        cites_correct_norm=None,
    )
    agg = AggregatedEvaluation(repetitions=[
        RepetitionResult(repetition_index=0, line_results=[linha], total_detections=1)
    ])
    deteccao = {"line_content": "x = 1", "norm_reference": "coding_standards.md 2.2"}
    details = [[{"pr_id": "PR-1", "line_results": [{"line": "x = 1", "cell": "FP"}],
                 "detections": [deteccao]}]]
    out = tmp_path / "r.json"

    run_evaluation._save_results(agg, tmp_path / "ds.json", 1, "m", out, details)

    salvo = json.loads(out.read_text(encoding="utf-8"))["per_pr_detail"]
    assert salvo == details[0]


def test_checkpoint_e_descartado_se_a_variante_mudou(checkpoint):
    dataset, _ = checkpoint
    assert run_evaluation._load_checkpoint(dataset, 1, sem_recuperacao=True) == {}


def test_fingerprint_difere_entre_com_e_sem_recuperacao(tmp_path):
    dataset = tmp_path / "ds.json"
    dataset.write_text("[1]", encoding="utf-8")
    assert run_evaluation._config_fingerprint(
        dataset
    ) != run_evaluation._config_fingerprint(dataset, sem_recuperacao=True)
