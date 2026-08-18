Yes. You're now asking the exact question that determines whether this becomes a good MSc dissertation or just a software demo.

And I think there is a subtle mistake we should avoid.

---

# What Many Students Do

They build:

```text id="56s4jr"
System A
```

then

```text id="ms90tr"
System B
```

then

```text id="m1h0li"
System C
```

Three separate implementations.

This becomes a nightmare.

---

# What We Should Do

Build:

```text id="j0swdj"
ONE SYSTEM
```

with:

```text id="vnjdqm"
THREE DEPLOYMENT MODES
```

---

# The Key Insight

The difference between:

```text id="ccftj8"
Edge
```

and

```text id="1e6r4q"
Cloud
```

is NOT the code.

The code should be identical.

The difference is:

```text id="kgxqul"
Where it executes

and

What resources it receives
```

---

# Think About Paper 9

Remember the RL orchestration paper?

They simulated:

```text id="0ikjbh"
End Device
1 CPU

Edge
2 CPU

Cloud
4 CPU
```

Same software.

Different resources.

Different placement.

---

# What Makes Something "Edge"?

For your dissertation:

```text id="gt8ryh"
1 CPU

512 MB RAM
```

could be your edge profile.

Docker:

```yaml id="h9gn0d"
cpus: 1
memory: 512m
```

---

# What Makes Something "Cloud"?

```text id="g8h2ot"
4 CPUs

8 GB RAM
```

Docker:

```yaml id="kccxzc"
cpus: 4
memory: 8g
```

---

Same application.

Different constraints.

---

# So What Does The Deployment Switch Actually Do?

Not:

```text id="zgvyrk"
Change the code
```

Instead:

```text id="ytl5c5"
Change where models run
```

and

```text id="kq5myl"
Change container resources
```

---

# Cloud-Only

When user selects:

```text id="ttt6or"
Cloud Only
```

the system behaves as:

```text id="8d2l1l"
Generator
      ↓
Cloud Detector
      ↓
Cloud Classifier
```

---

Edge detector disabled.

Edge classifier disabled.

---

Resources:

```text id="9pp3zx"
Cloud Detector
4 CPU

Cloud Classifier
4 CPU
```

---

# Edge-Only

When selected:

```text id="js6s8m"
Edge Only
```

---

System becomes:

```text id="8a8k6l"
Generator
      ↓
Edge Detector
      ↓
Edge Classifier
```

---

Cloud services disabled.

---

Resources:

```text id="6qz9gu"
Edge Detector
1 CPU

Edge Classifier
1 CPU
```

---

# Hybrid

Your actual proposal.

```text id="r2u4in"
Generator
      ↓
Edge Detector
      ↓

Anomaly?

No
↓
Ignore

Yes
↓
Cloud Classifier
```

---

Resources:

```text id="4glqnh"
Edge Detector
1 CPU

Cloud Classifier
4 CPU
```

---

# This Is Actually Very Important

Notice:

The deployment switch is not really changing architecture.

It is changing:

```text id="drf53y"
Placement
```

---

And your thesis title contains:

> Inference Orchestration

Inference orchestration literally means:

```text id="xxv0hl"
Where inference runs
```

---

# What We Are Really Measuring

For every mode:

---

## Cloud-Only

Measure:

```text id="2l41sx"
Latency

Bandwidth

CPU

Memory

Accuracy
```

---

## Edge-Only

Measure:

```text id="qqkwfd"
Latency

Bandwidth

CPU

Memory

Accuracy
```

---

## Hybrid

Measure:

```text id="kglq6x"
Latency

Bandwidth

CPU

Memory

Accuracy
```

---

Then compare.

---

# The Most Elegant Implementation

I would actually use environment variables.

Example:

```env id="0k78lt"
DEPLOYMENT_MODE=cloud
```

or

```env id="lf9t0u"
DEPLOYMENT_MODE=edge
```

or

```env id="s0s8fw"
DEPLOYMENT_MODE=hybrid
```

---

Then inside orchestrator:

```python id="q7ghsv"
if mode == "cloud":
    run_detector_cloud()
    run_classifier_cloud()

elif mode == "edge":
    run_detector_edge()
    run_classifier_edge()

elif mode == "hybrid":
    run_detector_edge()
    run_classifier_cloud()
```

Same codebase.

Same Docker network.

Same dataset.

Same UI.

---

# What I Would Personally Do

If I were building this thesis today:

I would create three logical machines:

```text id="miv7cl"
EDGE NODE

CLOUD NODE

CONTROL NODE
```

---

### EDGE NODE

Containers:

```text id="hgwj0j"
detector

edge-storage

batch-sync
```

Resource limited.

---

### CLOUD NODE

Containers:

```text id="rbhjtb"
classifier

cloud-storage
```

High resources.

---

### CONTROL NODE

Containers:

```text id="15g8eo"
stream-generator

mqtt

streamlit

orchestrator
```

---

Then the deployment mode simply determines:

```text id="4w6r4f"
which node executes detector

which node executes classifier
```

---

That's actually much closer to how the experiments will eventually appear in your methodology chapter:

```text id="w7dttq"
Scenario 1:
Cloud Detector + Cloud Classifier

Scenario 2:
Edge Detector + Edge Classifier

Scenario 3:
Edge Detector + Cloud Classifier
```

And that, in my opinion, is the cleanest and most defensible experimental design for your dissertation.
