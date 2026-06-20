These are exactly the right questions. They show we're moving from architecture diagrams to an actual experimental design.

---

# Question 1: How Do We Test Cloud-Only, Edge-Only, and Hybrid?

The trick is:

> We do **not** build three completely different systems.

We build **one system** with a deployment mode switch.

Think of it like this:

```text
Mode A = Cloud Only

Mode B = Edge Only

Mode C = Hybrid
```

The Streamlit UI can contain:

```text
Deployment Mode:

○ Cloud Only
○ Edge Only
○ Hybrid
```

When you press Start, the orchestrator reads the selected mode.

---

## Cloud-Only Mode

Data flow:

```text
Generator
    ↓
MQTT
    ↓
Cloud Detector
    ↓
Cloud Classifier
```

No edge detection.

No edge diagnosis.

Everything runs inside cloud containers.

---

Metrics:

```text
Latency
Bandwidth
CPU
Memory
Detection Accuracy
```

---

Expected:

```text
High Accuracy
High Bandwidth
Higher Latency
```

---

# Edge-Only Mode

Data flow:

```text
Generator
    ↓
MQTT
    ↓
Edge Detector
    ↓
Edge Classifier
```

Nothing sent to cloud.

No diagnosis requests.

No batch uploads.

---

Expected:

```text
Lowest Bandwidth
Lowest Latency
Lower Resource Availability
```

---

# Hybrid Mode (Your Contribution)

Data flow:

```text
Generator
    ↓
MQTT
    ↓
Edge Detector
    ↓

Normal?
   │
   └─────► Continue

Anomaly?
   │
   ▼

Cloud Classifier
```

Plus:

```text
Batch Upload
```

running continuously.

---

Expected:

```text
Near Edge Latency

+
Much Lower Bandwidth

+
Cloud-Level Diagnosis
```

---

# The Beautiful Part

You can use the SAME:

```text
Autoencoder
LSTM
Dataset
```

for all three experiments.

Only the deployment changes.

That makes your comparison much stronger.

---

# Question 2: How Can Streamlit Control The Generator?

This is actually very easy.

Containers can communicate.

Docker containers are not isolated islands.

Inside a Docker network:

```text
streamlit-ui
        │
        ▼
stream-generator
```

can talk using:

```text
REST API
HTTP
MQTT
Redis
WebSocket
```

---

# Option 1 (My Recommendation)

REST API

Inside:

```text
stream-generator
```

run:

```python
FastAPI
```

Example:

```python
POST /fault/7

POST /normal

POST /pause

POST /start
```

---

Then Streamlit simply calls:

```python
requests.post(
    "http://stream-generator:8000/fault/7"
)
```

Docker automatically resolves:

```text
stream-generator
```

to the correct container.

---

# Then Your Demo Looks Like This

Streamlit:

```text
Dataset Control

Current Mode:
NORMAL

[Switch To Fault 3]

[Switch To Fault 7]

[Switch To Fault 15]
```

---

When you click:

```text
Fault 7
```

Streamlit sends:

```http
POST /fault/7
```

to stream-generator.

---

Generator changes source:

From:

```text
faultNumber = 0
```

to:

```text
faultNumber = 7
```

and starts streaming fault samples.

---

Five seconds later:

```text
Anomaly Detected
```

appears.

---

# Even Better

You already have Tennessee Eastman labels.

So the UI could show:

```text
Inject Fault:

[Fault 1]
[Fault 2]
[Fault 3]
...
[Fault 20]
```

instead of manually editing files.

---

# How The Generator Should Work

I would not have one giant CSV.

I would load:

```text
Normal Dataset

Fault Dataset 1

Fault Dataset 2

...
Fault Dataset 20
```

into memory.

---

Generator state:

```python
current_mode = "normal"
```

---

UI:

```text
Inject Fault 5
```

changes:

```python
current_mode = "fault_5"
```

---

Next published rows come from:

```text
Fault 5 stream
```

instead.

---

# What the Final Experiment UI Could Look Like

```text
------------------------------------------------

Deployment Mode

(*) Cloud Only
( ) Edge Only
( ) Hybrid

------------------------------------------------

Data Source

Current:
NORMAL

[Fault 1]
[Fault 2]
[Fault 3]
...
[Fault 20]

------------------------------------------------

Metrics

Latency: 42 ms

Bandwidth: 0.8 MB/s

Edge CPU: 27%

Cloud CPU: 8%

------------------------------------------------

System Status

✓ Normal

or

⚠ Anomaly Detected

or

🚨 Fault Class 7 Detected

------------------------------------------------
```

---

# One More Important Architecture Decision

After thinking about your project, I would actually modify the architecture slightly.

Instead of:

```text
Edge Detector
      ↓
Orchestrator
      ↓
Cloud Classifier
```

I would use:

```text
Edge Detector
      ↓
Event Bus
      ↓
Orchestrator
      ↓
Cloud Classifier
```

because then:

```text
anomaly/event
```

becomes just another MQTT topic.

Everything becomes loosely coupled.

The detector doesn't know the cloud exists.

The cloud doesn't know the detector exists.

The orchestrator coordinates everything.

That's closer to how real industrial systems are built and will make your Docker architecture cleaner.

At this point, I think we are very close to a complete system design. The next thing I would do is draw the **final container diagram** and the **experimental deployment diagram** (Cloud-Only, Edge-Only, Hybrid) before writing a single line of code. Those two diagrams will likely end up almost unchanged in your dissertation methodology chapter.
