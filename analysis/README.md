# Experiment Analysis

`experiment_analysis.py` converts the recorded experiment directories into
flat files suitable for Pandas and visualisation.

Run it from the repository root:

```text
.venv\Scripts\python.exe -m analysis.experiment_analysis --normalize-manifests --print-summary
```

Outputs are written to `results/analysis`:

- `run_metrics.csv` and `run_metrics.json`: one row per experiment
- `group_metrics.csv` and `group_metrics.json`: long-form statistics grouped by deployment mode and scenario

Cloud communication is application-data volume only. The estimator serializes
sensor samples as compact UTF-8 JSON and excludes MQTT, HTTP, envelope,
metrics, and transport overhead. Edge-only volume is zero. Hybrid volume is
the estimated sample size multiplied by escalated batch sample counts. Cloud-
only volume is the estimated sample size multiplied by the continuous sample
count derived from the recorded measurement duration and stream interval.

Manifest normalization preserves previous values as `original_*` fields and
records that directory names were the metadata source. Malformed JSONL records
are skipped with a warning so one damaged telemetry record does not invalidate
the complete experiment set.
