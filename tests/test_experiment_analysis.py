import json

import pytest

from analysis.experiment_analysis import (
    _summary,
    analyse_run,
    application_sample_bytes,
)


def _write_json(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _write_jsonl(path, values):
    path.write_text(
        "".join(json.dumps(value) + "\n" for value in values),
        encoding="utf-8",
    )


def test_application_sample_size_is_compact_utf8_json():
    assert application_sample_bytes({"x": 1, "name": "a"}) == len(
        b'{"x":1,"name":"a"}'
    )


def test_summary_contains_percentile_and_sample_statistics():
    result = _summary([1.0, 2.0, 3.0, 4.0])

    assert result["count"] == 4
    assert result["mean"] == 2.5
    assert result["median"] == 2.5
    assert result["p95"] == pytest.approx(3.85)


def test_hybrid_cloud_volume_uses_escalated_sample_count(tmp_path):
    run_dir = tmp_path / "hybrid" / "hfs-01"
    run_dir.mkdir(parents=True)
    sample = {"faultNumber": 4, "x": 1.0}
    size = application_sample_bytes(sample)

    _write_json(
        run_dir / "manifest.json",
        {
            "experiment_id": "hfs-01",
            "deployment_mode": "hybrid",
            "scenario": "fault_sustained",
            "fault": 4,
            "tep_run": 1,
            "stream_interval_seconds": 0.1,
            "phase_changes": [
                {"phase": "warmup", "timestamp": "2026-01-01T00:00:00+00:00"},
                {"phase": "fault", "timestamp": "2026-01-01T00:01:00+00:00"},
            ],
            "ended_at": "2026-01-01T00:06:00+00:00",
        },
    )
    _write_jsonl(
        run_dir / "anomaly_events.jsonl",
        [{"payload": {"sample": sample}}],
    )
    _write_jsonl(
        run_dir / "orchestration_events.jsonl",
        [{"payload": {"decision": "anomaly", "reported": True, "batch_size": 3}}],
    )

    result = analyse_run(run_dir, dataset_root=None)

    assert result["cloud_escalations"] == 1
    assert result["escalated_samples"] == 3
    assert result["estimated_cloud_data_bytes"] == 3 * size


def test_edge_cloud_volume_is_zero_without_sample_data(tmp_path):
    run_dir = tmp_path / "edge_only" / "efn-01"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "experiment_id": "efn-01",
            "deployment_mode": "edge",
            "phase_changes": [],
            "ended_at": "2026-01-01T00:01:00+00:00",
        },
    )

    result = analyse_run(run_dir, dataset_root=None)

    assert result["estimated_cloud_data_bytes"] == 0.0
