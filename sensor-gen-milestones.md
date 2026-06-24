Good idea. At this stage we should stop designing and create a concrete implementation backlog.

I would break the Sensor Generator into **7 milestones**, where each milestone produces something runnable and testable.

# Milestone 1 — Dataset Access Layer

Goal:

```text
Load TEP data reliably
Load only the requested fault/run
Minimize memory usage
```

Tasks:

* [ ] Create `data_loader.py`
* [ ] Load `.RData` files using `pyreadr`
* [ ] Verify fault numbers (0-20)
* [ ] Verify run numbers (1-500)
* [ ] Implement:

```python
load_fault_run(
    fault_number,
    run_number
)
```

returns:

```python
pd.DataFrame
```

* [ ] Test memory consumption
* [ ] Test loading speed

Deliverable:

```python
df = load_fault_run(7, 42)
```

works.

---

# Milestone 2 — Stream Catalog

Goal:

```text
Know what streams exist
Without loading them
```

Tasks:

* [ ] Create `catalog_builder.py`
* [ ] Scan datasets
* [ ] Generate:

```json
{
  "0": [1,2,3,...500],
  "1": [1,2,3,...500],
  ...
}
```

* [ ] Save:

```text
catalog.json
```

Deliverable:

```python
catalog.get_random_run(7)
```

returns:

```text
384
```

---

# Milestone 3 — Replay Engine

Goal:

```text
Turn dataset rows into a live stream
```

Tasks:

* [ ] Create `replay_engine.py`
* [ ] Maintain state:

```python
current_fault
current_run
current_position
running
```

* [ ] Implement:

```python
next_sample()
```

* [ ] Implement:

```python
reset()
```

* [ ] Implement:

```python
set_fault()
```

* [ ] Auto-load new random run when current run finishes

Deliverable:

```python
sample = replay.next_sample()
```

returns next row.

---

# Milestone 4 — Shared MQTT Layer

Goal:

```text
Reusable by every service
```

Tasks:

* [ ] Create:

```text
shared/
    mqtt_service.py
```

* [ ] Connect to broker
* [ ] Publish JSON
* [ ] Subscribe topics
* [ ] Reconnect automatically
* [ ] Logging

Interface:

```python
mqtt.publish()
mqtt.subscribe()
```

Deliverable:

Can publish and receive test messages.

---

# Milestone 5 — Sensor Generator Service

Goal:

```text
Replay engine + MQTT
```

Tasks:

* [ ] Create `sensor_generator.py`
* [ ] Publish every 100 ms
* [ ] Topic:

```text
sensor/raw
```

* [ ] Convert dataframe row to JSON

Deliverable:

MQTT receives live TEP data.

---

# Milestone 6 — Command Handling

Goal:

```text
Control generator remotely
```

Topic:

```text
system/control
```

Tasks:

* [ ] Implement:

```json
{
  "action": "start"
}
```

* [ ] Implement:

```json
{
  "action": "stop"
}
```

* [ ] Implement:

```json
{
  "action": "set_fault",
  "fault": 7
}
```

* [ ] Implement:

```json
{
  "action": "set_stream",
  "fault": 7,
  "run": 384
}
```

* [ ] Implement:

```json
{
  "action": "reset"
}
```

Deliverable:

Dashboard can control generator.

---

# Milestone 7 — Status Reporting

Goal:

```text
Know what generator is doing
```

Topic:

```text
sensor/status
```

Tasks:

* [ ] Publish every 5 seconds

Example:

```json
{
  "running": true,
  "fault": 7,
  "run": 384,
  "sample": 512,
  "rate_ms": 100
}
```

Deliverable:

Dashboard can display generator state.

---

# Recommended Project Structure

```text
sensor-generator/

├── main.py
│
├── generator/
│   ├── replay_engine.py
│   ├── data_loader.py
│   └── catalog.py
│
├── shared/
│   ├── mqtt_service.py
│   └── models.py
│
├── config.py
│
├── data/
│   ├── TEP_FaultFree_Testing.RData
│   ├── TEP_Faulty_Testing.RData
│   └── catalog.json
│
└── tests/
```

# What We Should Do Next

The order I would follow is:

```text
✓ Dataset inspection

Next:
1. Data Loader
2. Catalog Builder
3. Replay Engine
4. MQTT Layer
5. Sensor Generator Service
6. Command Handling
7. Status Reporting
```

So the very next coding task is:

**Implement `data_loader.py` with a function that can load exactly one `(fault, run)` pair from the TEP dataset and nothing else.**

Once that works, everything else becomes much easier to build.
