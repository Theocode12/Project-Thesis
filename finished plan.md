Yes. Throughout the design of your project, we eventually narrowed it down to a set of metrics that directly answer your research question.

Remember, your research isn't trying to prove that the classifier is the best model. It's trying to evaluate whether **separating anomaly detection (edge) from diagnosis (cloud)** is a better deployment strategy than traditional approaches.

So your comparisons are between:

1. **Cloud-only deployment**
2. **Edge-only deployment**
3. **Hybrid edge–cloud deployment (your proposed system)**

For each of these deployments, we agreed to collect the following metrics.

---

## 1. Latency ⭐⭐⭐⭐⭐ (Primary Metric)

This is the most important evaluation metric.

We wanted to measure:

* **Detection Latency**

  * Time from sensor generation to anomaly detection.

* **Diagnosis Latency**

  * Time from diagnosis request to diagnosis completion.

* **End-to-End Latency**

  * Time from sensor generation to final diagnosis result.

These are obtained from the timestamps collected by every service.

---

## 2. Resource Utilisation ⭐⭐⭐⭐⭐

For every service/container:

* CPU Usage (%)
* Memory Usage (MB)
* Processing Time (ms)

These come from the Docker/container metrics you're already publishing.

---

## 3. Cloud Communication ⭐⭐⭐⭐⭐

This was one of the motivations behind your architecture.

We wanted to compare:

* Number of diagnosis requests sent to the cloud.
* Total data transferred to the cloud.
* Average payload size.

The expectation is that the hybrid system sends **far fewer** requests than the cloud-only system.

---

## 4. Orchestrator Behaviour ⭐⭐⭐⭐☆

Since the orchestrator is your research contribution, we also wanted to measure:

* Number of anomaly events received.
* Number of cloud escalations.
* Current anomaly/risk state (Normal, Warning, High Risk).
* Decision time.

These explain **why** the cloud was invoked.

---

## 5. System Throughput ⭐⭐⭐⭐☆

To demonstrate that the system keeps up with the incoming data:

* Samples processed per second.
* Classifications processed per second.

---

## What goes into the dissertation?

If you remember, we eventually decided that the **main comparison table** would look something like this:

| Metric                   | Cloud-Only | Edge-Only | Hybrid (Proposed System) |
| ------------------------ | ---------: | --------: | -----------------------: |
| Detection Latency        |            |           |                          |
| Diagnosis Latency        |            |           |                          |
| End-to-End Latency       |            |           |                          |
| CPU Usage                |            |           |                          |
| Memory Usage             |            |           |                          |
| Data Sent to Cloud       |            |           |                          |
| Number of Cloud Requests |            |           |                          |
| Samples Processed/sec    |            |           |                          |

---

## The hypothesis we're trying to prove

Everything comes back to this single idea:

| Metric              | Expected Outcome                                                                        |
| ------------------- | --------------------------------------------------------------------------------------- |
| Detection Latency   | **Lower** in the hybrid system because detection happens at the edge.                   |
| End-to-End Latency  | **Lower** than cloud-only because only significant anomalies are escalated.             |
| CPU Usage           | **Distributed** between edge and cloud rather than concentrated in one environment.     |
| Memory Usage        | **Distributed** across services according to their responsibilities.                    |
| Cloud Communication | **Significantly reduced** because only anomalous windows are transmitted for diagnosis. |

That's the story your evaluation chapter is meant to tell.

One thing I would add now, based on how far your implementation has come, is another metric that wasn't originally on our list:

* **Average Diagnosis Processing Time (ms)**

Your classifier service is already publishing this (`avg_processing_time_ms`), and it's a valuable metric because it quantifies the computational cost of the diagnosis stage itself. It complements the overall diagnosis latency and gives you more insight into how efficiently the diagnosis service performs. I would include it alongside the other runtime metrics in your final evaluation.
