This is exactly the right conversation to have now.

You've moved from:

```text
Research Idea
```

to

```text
System Design
```

And honestly, after everything you've described, I think we should start thinking like software architects rather than literature reviewers.

---

# First Observation

Looking at your Tennessee Eastman setup, I think you're making the right choice.

I would **not spend thesis time on preprocessing research**.

Your contribution is:

```text
Inference Orchestration
```

not

```text
Data Cleaning
Feature Engineering
Signal Processing
```

So we assume:

```text
Processed Sensor Stream
```

and start from there.

That's completely defensible.

---

# What I Think The Final System Looks Like

I currently see:

```text
                    Tennessee Eastman Dataset
                               │
                               ▼

                    Stream Generator Service
                               │
                               ▼

                   MQTT / Kafka Message Bus
                               │

      ┌────────────────────────┴────────────────────────┐
      │                                                 │
      ▼                                                 ▼

 Edge Storage Buffer                        Edge Detector Service
      │                                                 │
      │                                                 ▼
      │                                       Autoencoder
      │                                                 │
      │                                          Anomaly?
      │                                             │
      │                          ┌──────────────────┴───────────────┐
      │                          │                                  │
      ▼                          ▼                                  ▼

 Batch Upload Service      Normal Event                    Anomaly Event
      │                          │                                  │
      ▼                          ▼                                  ▼

 Cloud Storage            Continue Monitoring          Escalation Service
                                                            │
                                                            ▼

                                                Cloud Diagnostic Service
                                                            │
                                                            ▼

                                                   LSTM Classifier
                                                            │
                                                            ▼

                                                    Dashboard/UI
```

---

# Technology Stack

Let's break it down component by component.

---

# Option 1 (My Recommendation)

Python + MQTT + Docker

Simple.

Easy.

Industrial.

Thesis-friendly.

---

## Data Stream Generator

Purpose:

```text
Replay Tennessee Eastman data
```

Technology:

```text
Python
Pandas
MQTT Publisher
```

---

Service:

```text
stream-generator
```

Container:

```text
Docker
```

---

This service:

```python
read row
wait 100ms
publish
read row
wait 100ms
publish
```

Simulates real sensors.

---

# Why MQTT?

Because MQTT is literally made for IoT.

Most industrial papers use:

```text
MQTT
AMQP
Kafka
```

but for your scale:

```text
MQTT
```

wins.

---

Advantages:

```text
Lightweight
Easy
Industrial Standard
Low Latency
```

---

I would use:

```text
Mosquitto MQTT
```

Docker container.

---

# Edge Layer

Container:

```text
edge-detector
```

Technology:

```text
Python
PyTorch
TensorFlow
```

Model:

```text
Autoencoder
```

from Paper 8.

---

Responsibilities:

```text
Subscribe MQTT

Run Detection

Generate Score

Raise Alert
```

---

# Edge Buffer

Very important.

Container:

```text
edge-storage
```

Technology:

```text
SQLite
```

or

```text
InfluxDB
```

---

I recommend:

```text
InfluxDB
```

because:

```text
Time Series Database
```

which fits sensor data perfectly.

---

# Batch Upload Service

Container:

```text
batch-sync
```

Responsibilities:

```text
Every 60 seconds

Collect Local Data

Upload To Cloud
```

---

Technology:

```text
Python
APIs
```

Simple.

---

# Cloud Storage

Option 1:

```text
PostgreSQL
```

Option 2:

```text
InfluxDB
```

Option 3:

```text
AWS S3
```

---

My recommendation:

```text
InfluxDB
```

again.

Much easier for time-series queries.

---

# Escalation Service

This is actually your novelty.

Container:

```text
orchestrator
```

Responsibilities:

```text
Receive Alert

Trigger Diagnosis

Track Metrics
```

---

Initially:

```text
Rule-Based
```

not RL.

---

Example:

```python
if anomaly_score > threshold:
     trigger_cloud()
```

Simple.

Defensible.

Achievable.

---

# Cloud Diagnostic Service

Container:

```text
cloud-diagnosis
```

Technology:

```text
Python
PyTorch
```

Model:

```text
LSTM
```

from Paper 8.

---

Input:

```text
Recent Batch History

+
Current Event
```

Output:

```text
Fault Class
```

---

# Dashboard

This is where I think we should be clever.

---

Option 1

Grafana

Pros:

```text
Professional
Fast
Industrial Looking
```

Cons:

```text
Less Interactive
```

---

Option 2

Streamlit

Pros:

```text
Very Fast Development
Python
Interactive Controls
```

Cons:

```text
Less Industrial Looking
```

---

# I Recommend

```text
Streamlit
```

because you specifically said:

> "I want to inject faults manually."

---

Streamlit can easily provide:

```text
Start Stream

Stop Stream

Inject Fault 3

Inject Fault 7

Inject Fault 15
```

buttons.

---

Then:

```text
Fault 7 Selected
```

causes stream-generator to switch datasets.

---

# This Is Brilliant For Demonstrations

Imagine your dissertation demo.

You open:

```text
localhost:8501
```

Dashboard shows:

```text
System Healthy
```

green.

---

You click:

```text
Inject Fault 4
```

---

Five seconds later:

```text
Anomaly Detected
```

red.

---

Cloud classification starts.

---

Ten seconds later:

```text
Fault Type:
Condenser Cooling Failure
```

or whatever TEP label.

---

Examiners LOVE demonstrations like this.

---

# Docker Layout

I would actually deploy:

```text
docker-compose
```

with:

```yaml
stream-generator

mosquitto

edge-detector

edge-storage

batch-sync

orchestrator

cloud-diagnosis

streamlit-ui

influxdb
```

---

# Cloud Simulation

Now for your key requirement.

You said:

> simulate edge and cloud

Excellent.

---

## Cloud Only

```text
Cloud:
8 CPU
8 GB RAM
```

---

## Edge Only

```text
Edge:
1 CPU
512 MB RAM
```

---

## Hybrid

```text
Edge:
1 CPU

Cloud:
8 CPU
```

---

Docker lets us enforce:

```yaml
cpus: 1
memory: 512m
```

which is perfect for experimentation.

---

# What I Would Build

If this were my thesis, the stack would be:

```text
Dataset:
Tennessee Eastman

Streaming:
MQTT (Mosquitto)

Programming:
Python

Models:
Autoencoder
LSTM

Storage:
InfluxDB

Containers:
Docker Compose

Cloud:
AWS EC2

UI:
Streamlit

Metrics:
Prometheus + Grafana
(optional)
```

---

# The Most Important Architectural Decision

The thing that makes your thesis different is not:

```text
Autoencoder
```

and not:

```text
LSTM
```

Paper 8 already did that.

Your contribution is:

```text
Stream
      ↓
Edge Detection
      ↓
Event Trigger
      ↓
Cloud Diagnosis
```

combined with:

```text
Cloud Only
vs
Edge Only
vs
Hybrid
```

under controlled resource constraints.

That is the piece we should keep protecting as we design the software artifact, because that is where the novelty and evaluation value are concentrated.
