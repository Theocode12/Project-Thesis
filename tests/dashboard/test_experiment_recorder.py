import json

import pytest

from experiment_recorder import ExperimentRecorder


def _read_json_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_recorder_writes_events_metrics_and_manifest(tmp_path):
    recorder = ExperimentRecorder(tmp_path)
    experiment_id = recorder.start(
        {
            "experiment_id": "test_run",
            "deployment_mode": "hybrid",
            "scenario": "baseline",
        }
    )

    recorder.record_event(
        "anomaly/detected",
        {
            "timestamp": 100.0,
            "payload": {"fault": 5, "sample": {"value": 1}},
        },
        "edge",
    )
    recorder.record_event(
        "orchestrator/decision",
        {
            "timestamp": 101.0,
            "payload": {
                "batch_id": "batch_1",
                "or_metrics": {"container": {"cpu_cores": 0.2}},
            },
        },
        "edge",
    )
    recorder.record_command("sg_set_fault", {"fault": 5}, "edge")
    recorder.set_phase("fault")
    directory = recorder.stop()

    assert experiment_id == "test_run"
    assert directory == tmp_path / "test_run"
    manifest = json.loads((directory / "manifest.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    assert manifest["status"] == "completed"
    assert summary["event_counts"]["anomaly/detected"] == 1
    assert summary["event_counts"]["orchestrator/decision"] == 1

    anomaly = _read_json_lines(directory / "anomaly_events.jsonl")
    orchestration = _read_json_lines(directory / "orchestration_events.jsonl")
    metrics = _read_json_lines(directory / "service_metrics.jsonl")
    commands = _read_json_lines(directory / "commands.jsonl")
    assert anomaly[0]["payload"]["fault"] == 5
    assert orchestration[0]["payload"]["batch_id"] == "batch_1"
    assert metrics[0]["service"] == "orchestrator"
    assert any(command["action"] == "phase" for command in commands)


def test_recorder_rejects_duplicate_experiment(tmp_path):
    recorder = ExperimentRecorder(tmp_path)
    recorder.start({"experiment_id": "test_run"})

    with pytest.raises(RuntimeError):
        recorder.start({"experiment_id": "another_run"})

    recorder.stop()


def test_recorder_ignores_events_until_started(tmp_path):
    recorder = ExperimentRecorder(tmp_path)
    recorder.record_event(
        "anomaly/detected",
        {"timestamp": 1, "payload": {}},
        "edge",
    )
    assert recorder.experiment_id is None
