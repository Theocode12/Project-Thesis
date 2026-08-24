"""Analyse recorded edge-cloud inference experiments.

The module deliberately produces flat, JSON/CSV-friendly rows.  Those rows can
be consumed directly by pandas, Plotly, or a later dashboard without coupling
visualisation code to the raw recorder format.

Cloud communication is application-data volume only.  It excludes MQTT,
HTTP, envelope, metrics, and transport overhead.  A sensor sample is encoded
as compact UTF-8 JSON for the purpose of estimating its application size.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from collections.abc import Iterable
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

log = logging.getLogger(__name__)

JSON_KWARGS = {"separators": (",", ":"), "ensure_ascii": True}
SERVICE_KEYS = {
    "sensor-generator": "sg_metrics",
    "detector": "det_metrics",
    "orchestrator": "or_metrics",
    "classifier": "cl_metrics",
}
SCENARIO_BY_PREFIX = {
    "nf": "fault_free",
    "fs": "fault_sustained",
    "fn": "fault_alternate",
}
MODE_BY_DIRECTORY = {
    "edge_only": "edge_only",
    "cloud_only": "cloud_only",
    "hybrid": "hybrid",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("Skipping invalid JSON in %s:%d (%s)", path, line_number, exc.msg)
    return records


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _summary(values: Iterable[float]) -> dict[str, float | int | None]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return {"count": 0, "mean": None, "median": None, "std": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(clean),
        "mean": mean(clean),
        "median": median(clean),
        "std": stdev(clean) if len(clean) > 1 else 0.0,
        "p95": _percentile(clean, 0.95),
        "min": min(clean),
        "max": max(clean),
    }


def application_sample_bytes(sample: dict[str, Any]) -> int:
    """Return the size of one sensor sample as application JSON data."""
    return len(json.dumps(sample, **JSON_KWARGS).encode("utf-8"))


@lru_cache(maxsize=32)
def estimate_sample_size_from_parquet(path_string: str) -> float:
    """Estimate sample size from a matching runtime parquet stream.

    Pandas is imported lazily so the event analysis remains usable in a small
    environment.  The row is extended with the same ``_stream`` field added by
    the replay engine before being published.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Install pandas and pyarrow to read runtime parquet files") from exc
    path = Path(path_string)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    sizes = []
    for row in frame.to_dict(orient="records"):
        sample = {key: _native(value) for key, value in row.items()}
        sample["_stream"] = {
            "fault": int(sample.get("faultNumber", 0)),
            "run": int(sample.get("simulationRun", 0)),
        }
        sizes.append(application_sample_bytes(sample))
    if not sizes:
        raise ValueError(f"Runtime stream is empty: {path}")
    return mean(sizes)


def _native(value: Any) -> Any:
    """Convert numpy scalar values returned by pandas into JSON values."""
    return value.item() if hasattr(value, "item") else value


def _sample_size_from_events(records: Iterable[dict[str, Any]]) -> float | None:
    sizes = []
    for record in records:
        sample = (record.get("payload") or {}).get("sample")
        if isinstance(sample, dict):
            sizes.append(application_sample_bytes(sample))
    return mean(sizes) if sizes else None


def canonical_metadata(run_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Infer canonical metadata from the experiment directory name."""
    experiment_id = run_dir.name
    prefix = experiment_id[:3].lower()
    scenario = SCENARIO_BY_PREFIX.get(prefix[1:])
    if scenario is None:
        raise ValueError(f"Unknown experiment ID prefix: {experiment_id}")
    deployment_mode = MODE_BY_DIRECTORY.get(run_dir.parent.name)
    if deployment_mode is None:
        raise ValueError(f"Unknown deployment directory: {run_dir.parent.name}")
    return {
        "experiment_id": experiment_id,
        "deployment_mode": deployment_mode,
        "scenario": scenario,
    }


def normalize_manifests(experiments_root: str | Path = "experiments") -> list[Path]:
    """Normalize manifests using directory names and preserve old values."""
    root = Path(experiments_root)
    normalized = []
    for manifest_path in sorted(root.glob("*/*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        canonical = canonical_metadata(manifest_path.parent, manifest)
        mismatch_fields = []
        for field in ("experiment_id", "deployment_mode", "scenario"):
            original_field = f"original_{field}"
            original_value = manifest.setdefault(original_field, manifest.get(field))
            if original_value != canonical[field]:
                mismatch_fields.append(field)
            manifest[field] = canonical[field]
        manifest["metadata_source"] = "experiment_directory_name"
        manifest["metadata_normalized"] = True
        manifest["metadata_mismatch"] = bool(mismatch_fields)
        manifest["metadata_mismatch_fields"] = mismatch_fields
        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        normalized.append(manifest_path)
    return normalized


def _measurement_seconds(manifest: dict[str, Any]) -> float:
    end = _timestamp(manifest.get("ended_at"))
    phases = manifest.get("phase_changes") or []
    starts = [_timestamp(item.get("timestamp")) for item in phases if item.get("phase") != "warmup"]
    start = next((value for value in starts if value is not None), None)
    if start is None or end is None or end <= start:
        return 0.0
    return end - start


def _metric(record: dict[str, Any], service: str) -> dict[str, Any]:
    payload = record.get("payload") or {}
    return payload.get(SERVICE_KEYS[service]) or {}


def _duration(records: Iterable[dict[str, Any]], start: str, end: str) -> list[float]:
    values = []
    for record in records:
        payload = record.get("payload") or {}
        metrics = record.get("metrics") or payload.get("or_metrics") or {}
        if not metrics and record.get("service") in SERVICE_KEYS:
            metrics = _metric(record, record["service"])
        started = _number(metrics.get(start))
        ended = _number(metrics.get(end))
        if started is not None and ended is not None and ended >= started:
            values.append((ended - started) * 1000)
    return values


def analyse_run(run_dir: Path, dataset_root: Path | None = None) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    canonical = canonical_metadata(run_dir, manifest)
    mode = canonical["deployment_mode"]
    anomalies = _jsonl(run_dir / "anomaly_events.jsonl")
    decisions = _jsonl(run_dir / "orchestration_events.jsonl")
    results = _jsonl(run_dir / "classification_results.jsonl")
    service_metrics = _jsonl(run_dir / "service_metrics.jsonl")

    detection_latency = []
    for record in anomalies:
        metrics = (record.get("payload") or {}).get("det_metrics") or {}
        started = _number(metrics.get("sensor_published_at"))
        ended = _number(metrics.get("inference_ended_at"))
        if started is not None and ended is not None and ended >= started:
            detection_latency.append((ended - started) * 1000)

    decision_time = _duration(decisions, "decision_started_at", "decision_ended_at")
    diagnosis_latency = []
    e2e_latency = []
    for record in results:
        payload = record.get("payload") or {}
        result_at = _number(record.get("publisher_timestamp"))
        meta = payload.get("meta") or {}
        timestamps = meta.get("orchestrator_timestamps") or {}
        request_at = _number(timestamps.get("reporting_started_at"))
        sensor_times = []
        for event in meta.get("event_audit") or []:
            sensor_at = _number(((event.get("det_metrics") or {}).get("sensor_published_at")))
            if sensor_at is not None:
                sensor_times.append(sensor_at)
        if result_at is not None and request_at is not None and result_at >= request_at:
            diagnosis_latency.append((result_at - request_at) * 1000)
        if result_at is not None and sensor_times and result_at >= min(sensor_times):
            e2e_latency.append((result_at - min(sensor_times)) * 1000)

    sample_size = None
    if dataset_root is not None:
        fault = int(manifest.get("fault", 0))
        tep_run = int(manifest.get("tep_run", 0))
        dataset_path = dataset_root / f"fault_{fault}" / f"run_{tep_run}.parquet"
        if dataset_path.exists():
            try:
                sample_size = estimate_sample_size_from_parquet(str(dataset_path))
            except (ImportError, RuntimeError) as exc:
                log.warning("Using recorded samples for %s: %s", run_dir.name, exc)
    sample_size = sample_size or _sample_size_from_events(anomalies)

    escalated_samples = sum(
        int((record.get("payload") or {}).get("batch_size") or 0)
        for record in decisions
        if (record.get("payload") or {}).get("decision") == "anomaly"
        and (record.get("payload") or {}).get("reported") is True
    )
    if mode == "edge_only":
        cloud_bytes = 0.0
    elif mode == "hybrid":
        cloud_bytes = (escalated_samples * sample_size) if sample_size is not None else None
    else:
        sample_interval = float(manifest.get("stream_interval_seconds", 0.1))
        continuous_samples = _measurement_seconds(manifest) / sample_interval
        cloud_bytes = continuous_samples * sample_size if sample_size is not None else None

    resource = {service: {"cpu": [], "memory": []} for service in SERVICE_KEYS}
    processing = {service: [] for service in SERVICE_KEYS}
    correct_count = 0
    ground_truth_count = 0
    for record in service_metrics:
        service = record.get("service")
        if service not in SERVICE_KEYS:
            continue
        metrics = _metric(record, service)
        container = metrics.get("container") or {}
        for key, output in (("cpu_percent", "cpu"), ("memory_used_bytes", "memory")):
            value = _number(container.get(key))
            if value is not None:
                resource[service][output].append(value)
        started = _number(metrics.get("processing_started_at"))
        ended = _number(metrics.get("processing_ended_at"))
        if started is not None and ended is not None and ended >= started:
            processing[service].append((ended - started) * 1000)

    for record in results:
        payload = record.get("payload") or {}
        correct_count += int(payload.get("correct_count") or 0)
        ground_truth_count += int(payload.get("ground_truth_available") or 0)
        metrics = payload.get("cl_metrics") or {}
        started = _number(metrics.get("inference_started_at"))
        ended = _number(metrics.get("inference_ended_at"))
        if started is not None and ended is not None and ended >= started:
            processing["classifier"].append((ended - started) * 1000)

    decisions_by_type = {name: 0 for name in ("normal", "uncertain", "anomaly")}
    for record in decisions:
        decision = (record.get("payload") or {}).get("decision")
        if decision in decisions_by_type:
            decisions_by_type[decision] += 1

    row = {
        "experiment_id": canonical["experiment_id"],
        "deployment_mode": mode,
        "scenario": canonical["scenario"],
        "fault": manifest.get("fault"),
        "tep_run": manifest.get("tep_run"),
        "repetition": manifest.get("repetition"),
        "measurement_seconds": _measurement_seconds(manifest),
        "anomaly_events": len(anomalies),
        "decision_windows": len(decisions),
        "normal_decisions": decisions_by_type["normal"],
        "uncertain_decisions": decisions_by_type["uncertain"],
        "anomaly_decisions": decisions_by_type["anomaly"],
        "cloud_escalations": sum(1 for record in decisions if (record.get("payload") or {}).get("reported") is True),
        "escalated_samples": escalated_samples,
        "estimated_sample_bytes": sample_size,
        "estimated_cloud_data_bytes": cloud_bytes,
        "estimated_cloud_data_bytes_per_minute": (
            cloud_bytes / (_measurement_seconds(manifest) / 60.0)
            if cloud_bytes is not None and _measurement_seconds(manifest) > 0
            else None
        ),
        "classifier_accuracy": (
            correct_count / ground_truth_count if ground_truth_count else None
        ),
        "classifier_correct_count": correct_count,
        "classifier_ground_truth_count": ground_truth_count,
    }
    for name, values in (("detection_latency_ms", detection_latency), ("decision_time_ms", decision_time), ("diagnosis_latency_ms", diagnosis_latency), ("e2e_latency_ms", e2e_latency)):
        for key, value in _summary(values).items():
            row[f"{name}_{key}"] = value
    for service, values in resource.items():
        for metric, observations in values.items():
            for key, value in _summary(observations).items():
                row[f"{service}_{metric}_{key}"] = value
    for service, observations in processing.items():
        for key, value in _summary(observations).items():
            row[f"{service}_processing_ms_{key}"] = value
    return row


def analyse_experiments(experiments_root: str | Path = "experiments", dataset_root: str | Path | None = "datasets/runtime") -> list[dict[str, Any]]:
    """Return one flat analysis row per completed experiment."""
    root = Path(experiments_root)
    dataset = Path(dataset_root) if dataset_root is not None else None
    rows = []
    for manifest_path in sorted(root.glob("*/*/manifest.json")):
        row = analyse_run(manifest_path.parent, dataset)
        rows.append(row)
    return rows


def aggregate_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return long-form mean/median/std/p95 values by mode and scenario."""
    excluded = {
        "experiment_id", "deployment_mode", "scenario", "fault",
        "tep_run", "repetition",
    }
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("deployment_mode")), str(row.get("scenario")))
        groups.setdefault(key, []).append(row)

    output = []
    for (mode, scenario), group in sorted(groups.items()):
        fields = sorted(set().union(*(row.keys() for row in group)) - excluded)
        for field in fields:
            values = [_number(row.get(field)) for row in group]
            values = [value for value in values if value is not None]
            if not values:
                continue
            for statistic, value in _summary(values).items():
                output.append({
                    "deployment_mode": mode,
                    "scenario": scenario,
                    "metric": field,
                    "statistic": statistic,
                    "value": value,
                    "run_count": len(group),
                })
    return output


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_metrics.json").write_text(json.dumps(rows, indent=2, default=str) + "\n", encoding="utf-8")
    if not rows:
        return
    with (output_dir / "run_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    aggregates = aggregate_metrics(rows)
    (output_dir / "group_metrics.json").write_text(json.dumps(aggregates, indent=2, default=str) + "\n", encoding="utf-8")
    with (output_dir / "group_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["deployment_mode", "scenario", "metric", "statistic", "value", "run_count"])
        writer.writeheader()
        writer.writerows(aggregates)


def print_summary(rows: list[dict[str, Any]]) -> None:
    """Print the primary comparison metrics in a compact table."""
    fields = [
        ("deployment_mode", "Mode"),
        ("scenario", "Scenario"),
        ("runs", "Runs"),
        ("detection_latency_ms_median", "Det med ms"),
        ("detection_latency_ms_p95", "Det p95 ms"),
        ("diagnosis_latency_ms_median", "Diag med ms"),
        ("e2e_latency_ms_median", "E2E med ms"),
        ("detector_cpu_mean", "Det CPU %"),
        ("classifier_cpu_mean", "Cl CPU %"),
        ("detector_memory_mean", "Det MB"),
        ("classifier_memory_mean", "Cl MB"),
        ("estimated_cloud_data_bytes", "Cloud MB"),
        ("cloud_escalations", "Escalations"),
        ("classifier_accuracy", "Accuracy"),
    ]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["deployment_mode"], row["scenario"]), []).append(row)
    header = " | ".join(label for _, label in fields)
    print(header)
    print("-" * len(header))
    for key, group in sorted(groups.items()):
        values = []
        for field, _ in fields:
            if field == "deployment_mode":
                value = key[0]
            elif field == "scenario":
                value = key[1]
            elif field == "runs":
                value = len(group)
            else:
                observations = [_number(row.get(field)) for row in group]
                observations = [value for value in observations if value is not None]
                value = mean(observations) if observations else None
                if field.endswith("_memory_mean") and value is not None:
                    value /= 1024 * 1024
                if field == "estimated_cloud_data_bytes" and value is not None:
                    value /= 1024 * 1024
                if field == "classifier_accuracy" and value is not None:
                    value *= 100
            values.append("-" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value)))
        print(" | ".join(values))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", type=Path, default=Path("experiments"))
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/runtime"))
    parser.add_argument("--output", type=Path, default=Path("results/analysis"))
    parser.add_argument("--normalize-manifests", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    if args.normalize_manifests:
        normalized = normalize_manifests(args.experiments)
        print(f"Normalized {len(normalized)} manifests from experiment directory names")
    rows = analyse_experiments(args.experiments, args.dataset_root)
    write_outputs(rows, args.output)
    print(f"Analysed {len(rows)} experiments; outputs written to {args.output}")
    if args.print_summary:
        print_summary(rows)


if __name__ == "__main__":
    main()
