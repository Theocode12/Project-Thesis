# Thesis Results Data

This document records the current results from the 45 collected experiments:
five repetitions for each deployment mode and scenario.

The deployment modes are:

- `edge_only`: detector, orchestrator, and classifier run at the edge.
- `cloud_only`: processing runs in the cloud.
- `hybrid`: detector and orchestrator run at the edge; diagnosis runs in the cloud.

The scenarios are:

- `fault_free`: normal fault-free operation.
- `fault_sustained`: normal operation followed by a sustained fault.
- `fault_alternate`: repeated normal/fault transitions.

Values in the tables are group-level averages across the five runs. For
latency and anomaly-ratio columns, each run is first summarised and the group
value is then calculated from the five run summaries. `N/A` means that no
diagnosis was produced, so the latency statistic is not applicable.

## Latency

### Detection Latency

Detection latency is the time from sensor publication to anomaly-detector
inference completion. It includes sensor-to-detector delivery time and the
detector inference interval; it is not classifier-only processing time. The
recorded anomaly-event data contains this measurement for anomalous samples,
not every sensor sample.

| Deployment | Scenario | Mean (ms) | Median (ms) | Std (ms) | P95 (ms) |
|---|---|---:|---:|---:|---:|
| Cloud-only | Fault-free | 3.49 | 3.44 | 0.28 | 3.81 |
| Cloud-only | Sustained fault | 3.59 | 3.45 | 1.07 | 3.93 |
| Cloud-only | Multiple transitions | 3.43 | 3.36 | 0.56 | 3.84 |
| Edge-only | Fault-free | 4.80 | 4.02 | 2.32 | 9.55 |
| Edge-only | Sustained fault | 4.78 | 4.01 | 4.50 | 6.86 |
| Edge-only | Multiple transitions | 4.65 | 4.02 | 4.06 | 6.17 |
| Hybrid | Fault-free | 4.01 | 3.92 | 0.36 | 4.49 |
| Hybrid | Sustained fault | 4.10 | 3.98 | 0.91 | 4.35 |
| Hybrid | Multiple transitions | 5.07 | 4.23 | 4.08 | 7.30 |

### Diagnosis Latency

Diagnosis latency is the time from diagnosis reporting/request start until the
classification result is published. It includes diagnosis-stage overhead such
as queueing, communication, inference, and result publication.

| Deployment | Scenario | Mean (ms) | Median (ms) | Std (ms) | P95 (ms) |
|---|---|---:|---:|---:|---:|
| Cloud-only | Fault-free | N/A | N/A | N/A | N/A |
| Cloud-only | Sustained fault | 13.84 | 13.54 | 1.85 | 15.62 |
| Cloud-only | Multiple transitions | 12.22 | 12.06 | 1.49 | 14.95 |
| Edge-only | Fault-free | N/A | N/A | N/A | N/A |
| Edge-only | Sustained fault | 28.99 | 20.54 | 33.11 | 46.71 |
| Edge-only | Multiple transitions | 30.18 | 20.44 | 33.39 | 72.13 |
| Hybrid | Fault-free | N/A | N/A | N/A | N/A |
| Hybrid | Sustained fault | 16.62 | 16.60 | 1.64 | 18.22 |
| Hybrid | Multiple transitions | 17.31 | 16.28 | 3.80 | 23.25 |

### Classifier Inference Processing Time

This is the classifier computation interval only:

```text
inference_ended_at - inference_started_at
```

It excludes network transfer, queue waiting before processing, and result
publication. It is the most precise label for this metric.

| Deployment | Scenario | Mean (ms) | Median (ms) | Std (ms) | P95 (ms) |
|---|---|---:|---:|---:|---:|
| Cloud-only | Fault-free | N/A | N/A | N/A | N/A |
| Cloud-only | Sustained fault | 5.10 | 4.81 | 1.20 | 6.03 |
| Cloud-only | Multiple transitions | 4.39 | 4.21 | 0.67 | 5.51 |
| Edge-only | Fault-free | N/A | N/A | N/A | N/A |
| Edge-only | Sustained fault | 11.51 | 7.27 | 16.92 | 20.01 |
| Edge-only | Multiple transitions | 11.40 | 7.38 | 13.52 | 31.01 |
| Hybrid | Fault-free | N/A | N/A | N/A | N/A |
| Hybrid | Sustained fault | 4.51 | 4.43 | 0.63 | 4.65 |
| Hybrid | Multiple transitions | 4.42 | 4.23 | 1.00 | 5.19 |

### End-to-End Latency

End-to-end latency is measured from the earliest sensor sample represented in a
diagnosis batch to the published diagnosis result.

| Deployment | Scenario | Mean (ms) | Median (ms) | Std (ms) | P95 (ms) |
|---|---|---:|---:|---:|---:|
| Cloud-only | Fault-free | N/A | N/A | N/A | N/A |
| Cloud-only | Sustained fault | 9887.77 | 9997.18 | 365.00 | 10044.63 |
| Cloud-only | Multiple transitions | 9761.91 | 9987.82 | 679.41 | 10045.68 |
| Edge-only | Fault-free | N/A | N/A | N/A | N/A |
| Edge-only | Sustained fault | 9935.96 | 10015.21 | 354.45 | 10073.63 |
| Edge-only | Multiple transitions | 9775.05 | 10013.15 | 631.75 | 10098.55 |
| Hybrid | Fault-free | N/A | N/A | N/A | N/A |
| Hybrid | Sustained fault | 9935.44 | 9999.81 | 324.03 | 10047.65 |
| Hybrid | Multiple transitions | 9777.58 | 10001.37 | 578.63 | 10057.77 |

The approximately 10-second end-to-end values are largely explained by the
orchestrator's 10-second assessment window. They should not be interpreted as
10 seconds of classifier processing or network delay.

## Resource Utilisation

CPU values are derived from consecutive service-status heartbeats using cgroup
CPU-time deltas. This avoids short-interval artefacts caused by inference-event
and status sampling sharing the same collector.

Memory values are the maximum sampled cgroup memory usage. Memory is reported
in MB using 1 MB = 1,048,576 bytes. Peak values are the mean of each run's
maximum observed value.

| Deployment | Scenario | Detector CPU mean | Detector CPU peak | Classifier CPU mean | Classifier CPU peak | Detector memory mean (MB) | Detector memory peak (MB) | Classifier memory mean (MB) | Classifier memory peak (MB) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cloud-only | Fault-free | 1.58% | 2.74% | 0.48% | 2.11% | 210.6 | 212.0 | 230.4 | 236.2 |
| Cloud-only | Sustained fault | 1.82% | 2.72% | 0.53% | 2.28% | 211.9 | 213.8 | 234.6 | 242.9 |
| Cloud-only | Multiple transitions | 1.60% | 2.80% | 0.47% | 2.16% | 210.4 | 211.1 | 245.6 | 246.2 |
| Edge-only | Fault-free | 4.69% | 17.47% | 1.39% | 10.47% | 245.3 | 247.4 | 322.6 | 327.4 |
| Edge-only | Sustained fault | 5.42% | 22.71% | 1.62% | 17.62% | 246.0 | 247.8 | 334.8 | 342.7 |
| Edge-only | Multiple transitions | 5.17% | 19.36% | 1.56% | 13.51% | 232.6 | 233.5 | 253.0 | 259.4 |
| Hybrid | Fault-free | 4.14% | 6.51% | 0.48% | 2.22% | 277.3 | 278.9 | 230.1 | 233.8 |
| Hybrid | Sustained fault | 4.81% | 7.13% | 0.53% | 2.24% | 286.3 | 287.1 | 232.4 | 236.4 |
| Hybrid | Multiple transitions | 5.59% | 19.66% | 0.49% | 2.10% | 279.0 | 280.1 | 234.3 | 241.2 |

Memory is read from the container cgroup and includes runtime allocations and
cache. It is not limited to the neural-network model's memory.

## Communication and Orchestration

Cloud data is application sensor/process data only. It excludes HTTP headers,
MQTT overhead, envelopes, TCP/IP overhead, and other transport metadata.

For cloud-only, data is estimated from the continuous sensor stream. For
hybrid, data is estimated from the samples in escalated diagnosis windows.
Edge-only has no cloud processing boundary and therefore reports zero cloud
application data.

| Deployment | Scenario | Anomaly events | Anomaly windows | Diagnosis requests | Cloud escalations | Escalation rate | Estimated cloud data (MB) |
|---|---|---:|---:|---:|---:|---:|---:|
| Cloud-only | Fault-free | 34.0 | 0.0 | 0.0 | 0.0 | N/A | 2.96 |
| Cloud-only | Sustained fault | 2220.4 | 23.4 | 23.4 | 23.4 | 100% | 2.95 |
| Cloud-only | Multiple transitions | 1317.4 | 14.2 | 14.0 | 14.2 | 100% | 2.93 |
| Edge-only | Fault-free | 34.0 | 0.0 | 0.0 | 0.0 | N/A | 0.00 |
| Edge-only | Sustained fault | 2215.8 | 23.4 | 23.4 | 23.4 | 100% | 0.00 |
| Edge-only | Multiple transitions | 1618.6 | 17.2 | 17.2 | 17.2 | 100% | 0.00 |
| Hybrid | Fault-free | 34.0 | 0.0 | 0.0 | 0.0 | N/A | 0.00 |
| Hybrid | Sustained fault | 2215.8 | 23.4 | 23.4 | 23.4 | 100% | 2.11 |
| Hybrid | Multiple transitions | 1609.6 | 17.4 | 17.4 | 17.4 | 100% | 1.52 |

The `Diagnosis requests` column counts recorded classification results. The
`Cloud escalations` column counts orchestrator decisions marked as reported.
They may differ when a request does not produce a recorded result.

### Anomaly Ratio

Anomaly ratio is the number of anomaly events in an assessment window divided
by the estimated number of sensor samples in that window. The escalation
threshold is 0.50.

| Deployment | Scenario | Mean | Median | Std | P95 |
|---|---|---:|---:|---:|---:|
| Cloud-only | Fault-free | 0.011 | 0.000 | 0.026 | 0.058 |
| Cloud-only | Sustained fault | 0.681 | 0.923 | 0.417 | 0.997 |
| Cloud-only | Multiple transitions | 0.424 | 0.579 | 0.424 | 0.906 |
| Edge-only | Fault-free | 0.011 | 0.000 | 0.027 | 0.053 |
| Edge-only | Sustained fault | 0.688 | 0.935 | 0.416 | 1.000 |
| Edge-only | Multiple transitions | 0.500 | 0.751 | 0.455 | 0.987 |
| Hybrid | Fault-free | 0.011 | 0.000 | 0.027 | 0.060 |
| Hybrid | Sustained fault | 0.687 | 0.927 | 0.415 | 0.997 |
| Hybrid | Multiple transitions | 0.500 | 0.758 | 0.455 | 0.986 |

## Interpretation Notes

- Hybrid transferred approximately 2.02 MB in sustained-fault runs versus approximately 2.95 MB for cloud-only.
- Hybrid transferred approximately 1.52 MB in multiple-transition runs versus approximately 2.93 MB for cloud-only.
- Hybrid diagnosis latency was higher than cloud-only but lower than edge-only in the fault scenarios.
- Fault-free Hybrid runs produced no cloud escalations, while cloud-only still transferred the continuous sensor stream because processing was located in the cloud.
- The current data supports a trade-off interpretation. It does not prove that Hybrid is superior on every metric.

## Data Quality

One malformed JSONL record was skipped during analysis:

```text
experiments/cloud_only/cfn-01/service_metrics.jsonl:117
```

The record is a truncated telemetry line. All other valid records were retained.

The raw per-run data is available in `run_metrics.csv`. The compact table is
available in `thesis_summary.csv`, and the long-form statistics are available
in `thesis_metrics.csv`.
