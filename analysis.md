Yes. The thesis metrics are:

1. **Detection latency**
   - Sensor publication to anomaly detection completion.

2. **Diagnosis latency**
   - Diagnosis request/reporting start to classification result.

3. **End-to-end latency**
   - Sensor publication to final diagnosis result.

4. **Resource utilization**
   - CPU usage
   - Actual CPU cores used
   - Memory used in bytes/MB
   - Memory-limit utilization
   - Service processing time

5. **Cloud communication**
   - Number of cloud escalations
   - Diagnosis requests
   - Payload bytes transferred
   - Average payload size

6. **Orchestrator behavior**
   - Anomaly events received
   - Normal, uncertain, and anomaly decisions
   - Number of suppressed anomalies
   - Number of escalations
   - Anomaly ratio
   - Decision time

7. **System throughput**
   - Samples processed per second
   - Classifications processed per second
   - Queue depth/backlog

8. **Classifier results**
   - Diagnosis output
   - Confidence
   - Accuracy where ground truth is available
   - Average diagnosis processing time

The main comparison is:

```text
Cloud-only vs Edge-only vs Hybrid
```

with latency, resource distribution, throughput, and cloud communication as the core evaluation categories.