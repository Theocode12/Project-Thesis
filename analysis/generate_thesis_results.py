"""Generate the four principal Results and Evaluation figures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch

try:
    from .experiment_analysis import analyse_experiments, normalize_manifests, write_outputs
except ImportError:
    from experiment_analysis import analyse_experiments, normalize_manifests, write_outputs

SCENARIOS = ["fault_free", "fault_sustained", "fault_alternate"]
MODES = ["edge_only", "cloud_only", "hybrid"]
MODE_LABELS = {"edge_only": "Edge-only", "cloud_only": "Cloud-only", "hybrid": "Hybrid"}
SCENARIO_LABELS = {
    "fault_free": "Fault-free",
    "fault_sustained": "Normal to\nsustained fault",
    "fault_alternate": "Multiple fault\ntransitions",
}
COLORS = {"edge_only": "#2f80ed", "cloud_only": "#7b61ff", "hybrid": "#16a085"}


def _group_frame(frame: pd.DataFrame, value: str) -> pd.DataFrame:
    grouped = frame.groupby(["scenario", "deployment_mode"], as_index=False)[value].agg(["mean", "std"]).reset_index()
    return grouped


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_diagnosis_latency(frame: pd.DataFrame, output: Path) -> None:
    data = frame.dropna(subset=["diagnosis_latency_ms_mean"]).copy()
    data["scenario_label"] = data["scenario"].map(SCENARIO_LABELS)
    grouped = _group_frame(data, "diagnosis_latency_ms_mean")
    grouped["scenario_label"] = grouped["scenario"].map(SCENARIO_LABELS)

    fig, ax = plt.subplots(figsize=(10, 6))
    width = 0.24
    scenarios = ["fault_sustained", "fault_alternate"]
    positions = range(len(scenarios))
    for offset, mode in zip([-width, 0, width], MODES):
        subset = grouped[grouped["deployment_mode"] == mode].set_index("scenario")
        values = [subset.loc[s, "mean"] if s in subset.index else float("nan") for s in scenarios]
        errors = [subset.loc[s, "std"] if s in subset.index else 0 for s in scenarios]
        ax.bar([p + offset for p in positions], values, width, yerr=errors, capsize=4,
               label=MODE_LABELS[mode], color=COLORS[mode], edgecolor="white", linewidth=0.7)
    ax.set_xticks(list(positions), [SCENARIO_LABELS[s] for s in scenarios])
    ax.set_ylabel("Diagnosis latency (ms)")
    ax.legend(frameon=False, ncol=1, loc="lower right", bbox_to_anchor=(1.0, 1.02))
    ax.grid(axis="y", alpha=0.25)
    sns.despine(ax=ax)
    _save(fig, output / "diagnosis_latency.png")


def plot_resources(frame: pd.DataFrame, output: Path) -> None:
    resource_rows = []
    for _, row in frame.iterrows():
        for service, label in (("detector", "Detector"), ("classifier", "Classifier")):
            resource_rows.append({
                "deployment_mode": row["deployment_mode"],
                "scenario": row["scenario"],
                "service": label,
                "cpu": row.get(f"{service}_cpu_mean"),
                "memory": row.get(f"{service}_memory_mean", float("nan")) / (1024 * 1024),
            })
    data = pd.DataFrame(resource_rows)
    data = data[data["scenario"].isin(SCENARIOS)]
    grouped = data.groupby(["scenario", "deployment_mode", "service"], as_index=False)[["cpu", "memory"]].mean()

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    x = range(len(SCENARIOS))
    width = 0.22
    panels = (
        (axes[0, 0], "Detector", "cpu", "Detector CPU utilisation (%)"),
        (axes[0, 1], "Classifier", "cpu", "Classifier CPU utilisation (%)"),
        (axes[1, 0], "Detector", "memory", "Detector memory usage (MB)"),
        (axes[1, 1], "Classifier", "memory", "Classifier memory usage (MB)"),
    )
    for axis, service, metric, ylabel in panels:
        subset = grouped[grouped["service"] == service]
        for offset, mode in zip([-width, 0, width], MODES):
            values = []
            for scenario in SCENARIOS:
                match = subset[
                    (subset["scenario"] == scenario)
                    & (subset["deployment_mode"] == mode)
                ]
                values.append(match[metric].iloc[0] if not match.empty else float("nan"))
            axis.bar([p + offset for p in x], values, width,
                     color=COLORS[mode], label=MODE_LABELS[mode],
                     edgecolor="white", linewidth=0.7)
        axis.set_xticks(list(x), [SCENARIO_LABELS[s] for s in SCENARIOS])
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", alpha=0.25)
        sns.despine(ax=axis)
    handles = [Patch(facecolor=COLORS[mode], label=MODE_LABELS[mode]) for mode in MODES]
    fig.legend(handles=handles, frameon=False, loc="center left",
               bbox_to_anchor=(1.0, 0.5), ncol=1)
    _save(fig, output / "resource_utilisation.png")


def plot_cloud_communication(frame: pd.DataFrame, output: Path) -> None:
    grouped = _group_frame(frame, "estimated_cloud_data_bytes")
    fig, ax = plt.subplots(figsize=(10, 6))
    width = 0.24
    positions = range(len(SCENARIOS))
    for offset, mode in zip([-width, 0, width], MODES):
        subset = grouped[grouped["deployment_mode"] == mode].set_index("scenario")
        values = [(subset.loc[s, "mean"] / (1024 * 1024)) if s in subset.index else 0 for s in SCENARIOS]
        errors = [(subset.loc[s, "std"] / (1024 * 1024)) if s in subset.index else 0 for s in SCENARIOS]
        ax.bar([p + offset for p in positions], values, width, yerr=errors, capsize=4,
               label=MODE_LABELS[mode], color=COLORS[mode], edgecolor="white", linewidth=0.7)
    ax.set_xticks(list(positions), [SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.set_ylabel("Estimated application data transferred (MB)")
    ax.legend(frameon=False, ncol=1, loc="lower right", bbox_to_anchor=(1.0, 1.02))
    ax.grid(axis="y", alpha=0.25)
    sns.despine(ax=ax)
    _save(fig, output / "cloud_communication.png")


def plot_orchestration(experiments_root: Path, output: Path, experiment_id: str) -> None:
    path = experiments_root / "hybrid" / experiment_id / "orchestration_events.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    phases = manifest.get("phase_changes") or []
    start = pd.Timestamp(next(item["timestamp"] for item in phases if item.get("phase") != "warmup"))
    records = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload") or {}
            timestamp = pd.to_datetime(record.get("publisher_timestamp"), unit="s", utc=True)
            records.append({
                "elapsed_minutes": (timestamp - start).total_seconds() / 60,
                "ratio": payload.get("anomaly_ratio", 0),
                "reported": payload.get("reported", False),
            })
    data = pd.DataFrame(records).sort_values("elapsed_minutes")
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(data["elapsed_minutes"], data["ratio"], color=COLORS["hybrid"], marker="o", markersize=3,
            linewidth=1.5, label="Anomaly ratio")
    ax.axhline(0.5, color="#c0392b", linestyle="--", linewidth=1.3, label="Escalation threshold (0.50)")
    escalated = data[data["reported"] == True]
    ax.scatter(escalated["elapsed_minutes"], escalated["ratio"], color="#c0392b", marker="x", s=45,
               linewidths=1.5, label="Diagnosis escalation", zorder=4)
    ax.set_xlabel("Elapsed measurement time (minutes)")
    ax.set_ylabel("Anomaly ratio per assessment window")
    ax.set_ylim(bottom=0, top=1.05)
    ax.legend(frameon=False, ncol=1, loc="lower right", bbox_to_anchor=(1.0, 1.02))
    ax.grid(alpha=0.25)
    sns.despine(ax=ax)
    _save(fig, output / "orchestration_behaviour.png")


def write_thesis_summary(frame: pd.DataFrame, output: Path) -> None:
    """Write one compact, wide row per deployment/scenario combination."""
    metrics = {
        "detection_latency": "detection_latency_ms",
        "diagnosis_latency": "diagnosis_latency_ms",
        "diagnosis_processing": "diagnosis_processing_ms",
        "e2e_latency": "e2e_latency_ms",
        "anomaly_ratio": "anomaly_ratio",
    }
    columns: dict[str, str] = {
        "experiment_count": "experiment_id",
        "diagnosis_requests": "diagnosis_requests",
        "cloud_escalations": "cloud_escalations",
        "escalation_rate": "escalation_rate",
        "anomaly_events": "anomaly_events",
        "estimated_cloud_data_bytes": "estimated_cloud_data_bytes",
        "estimated_cloud_data_bytes_per_minute": "estimated_cloud_data_bytes_per_minute",
        "classifier_accuracy": "classifier_accuracy",
    }
    for prefix, source in metrics.items():
        for statistic in ("mean", "median", "std", "p95"):
            columns[f"{prefix}_{statistic}"] = f"{source}_{statistic}"
    for service in ("detector", "classifier"):
        columns[f"{service}_cpu_mean"] = f"{service}_cpu_mean"
        columns[f"{service}_peak_cpu"] = f"{service}_peak_cpu"
        columns[f"{service}_memory_mean_bytes"] = f"{service}_memory_mean"
        columns[f"{service}_peak_memory_bytes"] = f"{service}_peak_memory"

    rows = []
    for (mode, scenario), group in frame.groupby(["deployment_mode", "scenario"], sort=True):
        row = {"deployment_mode": mode, "scenario": scenario}
        for target, source in columns.items():
            if target == "experiment_count":
                row[target] = len(group)
                continue
            values = pd.to_numeric(group[source], errors="coerce") if source in group else pd.Series(dtype=float)
            row[target] = values.mean() if values.notna().any() else None
        for service in ("detector", "classifier"):
            row[f"{service}_memory_mean_mb"] = (
                row[f"{service}_memory_mean_bytes"] / (1024 * 1024)
                if row[f"{service}_memory_mean_bytes"] is not None else None
            )
            row[f"{service}_peak_memory_mb"] = (
                row[f"{service}_peak_memory_bytes"] / (1024 * 1024)
                if row[f"{service}_peak_memory_bytes"] is not None else None
            )
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "thesis_summary.csv", index=False)
    summary.to_json(output / "thesis_summary.json", orient="records", indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", type=Path, default=Path("experiments"))
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/runtime"))
    parser.add_argument("--output", type=Path, default=Path("results/analysis"))
    parser.add_argument("--figures", type=Path, default=Path("results/figures"))
    parser.add_argument("--representative-run", default="hfn-01")
    args = parser.parse_args()

    normalize_manifests(args.experiments)
    rows = analyse_experiments(args.experiments, args.dataset_root)
    write_outputs(rows, args.output)
    args.figures.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    write_thesis_summary(frame, args.output)
    plot_diagnosis_latency(frame, args.figures)
    plot_resources(frame, args.figures)
    plot_cloud_communication(frame, args.figures)
    plot_orchestration(args.experiments, args.figures, args.representative_run)
    print(f"Generated four thesis figures in {args.figures}")


if __name__ == "__main__":
    main()
