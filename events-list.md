For your dissertation, keep MQTT as simple as possible initially. You don't need TLS, authentication, ACLs, persistence tuning, or clustering yet.

I would use **Mosquitto 2.x** (current standard) with a minimal but modern configuration.

## `mqtt/mosquitto.conf`

```conf
# ==========================
# Mosquitto 2.x Configuration
# ==========================

# Listen on standard MQTT port
listener 1883

# Allow Docker containers to connect
allow_anonymous true

# Persistence
persistence true
persistence_location /mosquitto/data/

# Logging
log_dest stdout

# Useful during development
connection_messages true
log_timestamp true

# Retain queued messages for offline subscribers
persistence_file mosquitto.db
```

---

## `mqtt/Dockerfile`

Honestly, I would not create a custom Dockerfile unless you have a special requirement.

Use the official image.

Create:

### `docker-compose.yml`

```yaml
services:

  mqtt-broker:
    image: eclipse-mosquitto:2.0
    container_name: mqtt-broker

    ports:
      - "1883:1883"

    volumes:
      - ./mqtt/mosquitto.conf:/mosquitto/config/mosquitto.conf
      - mosquitto_data:/mosquitto/data
      - mosquitto_log:/mosquitto/log

    restart: unless-stopped

volumes:
  mosquitto_data:
  mosquitto_log:
```

This is how most people deploy Mosquitto today.

---

## If You Really Want a Dockerfile

### `mqtt/Dockerfile`

```dockerfile
FROM eclipse-mosquitto:2.0

COPY mosquitto.conf /mosquitto/config/mosquitto.conf
```

Then in compose:

```yaml
mqtt-broker:
  build:
    context: ./mqtt

  container_name: mqtt-broker

  ports:
    - "1883:1883"

  restart: unless-stopped
```

But I would still use the official image directly.

---

## MQTT Topics We Should Standardize Now

Let's agree on them before writing code.

### Raw Sensor Stream

```text
sensor/raw
```

Published by:

```text
sensor-generator
```

Subscribed by:

```text
edge-detector
dashboard
```

---

### Anomaly Event

```text
anomaly/detected
```

Published by:

```text
edge-detector
```

Subscribed by:

```text
orchestrator
dashboard
```

---

### Classification Request

```text
classification/request
```

Published by:

```text
orchestrator
```

Subscribed by:

```text
edge-classifier
cloud-classifier
```

---

### Classification Result

```text
classification/result
```

Published by:

```text
edge-classifier
cloud-classifier
```

Subscribed by:

```text
dashboard
```

---

### Orchestrator Decision

```text
orchestrator/decision
```

Published by:

```text
orchestrator
```

Subscribed by:

```text
dashboard
```

---

### System Control

For your Streamlit buttons:

```text
system/control
```

Messages:

```json
{
  "action": "sg_set_fault",
  "fault": 1
}
```

or

```json
{
  "action": "sg_set_fault",
  "fault": 0
}
```

or

```json
{
  "action": "sg_start"
}
```

or

```json
{
  "action": "sg_stop"
}
```

Published by:

```text
dashboard
```

Subscribed by:

```text
sensor-generator
```

Actions are namespaced per service to avoid cross-triggering on the shared
topic: `sg_*` for the sensor generator, `ed_*` for the edge detector.

Edge detector control messages:

```json
{
  "action": "ed_start"
}
```

```json
{
  "action": "ed_stop"
}
```

Subscribed by:

```text
edge-detector
```

---

One thing I'd actually change from my earlier recommendation:

Since you're already building an MQTT-centric architecture, I would **also use MQTT for the UI control messages** (`system/control`) instead of HTTP. That way the entire system becomes event-driven and you only have one communication mechanism to maintain. For a dissertation prototype, that's cleaner and easier to debug.
