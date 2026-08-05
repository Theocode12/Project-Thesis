from mqtt_client import ActionLog


class TestActionLog:

    def test_log_records_most_recent_first(self):
        log = ActionLog()
        log.log("state", "first")
        log.log("fault", "second")

        events = log.recent()
        assert events[0]["text"] == "second"
        assert events[1]["text"] == "first"

    def test_log_caps_ring_buffer(self):
        log = ActionLog(max_events=3)
        for i in range(5):
            log.log("state", f"event-{i}")

        events = log.recent()
        assert len(events) == 3
        assert events[0]["text"] == "event-4"
        assert events[-1]["text"] == "event-2"

    def test_recent_returns_copy(self):
        log = ActionLog()
        log.log("state", "x")

        events = log.recent()
        events.pop()

        assert len(log.recent()) == 1

    def test_empty_log(self):
        log = ActionLog()
        assert log.recent() == []

    def test_entries_carry_kind_and_timestamp(self):
        log = ActionLog()
        log.log("mqtt", "connected")

        entry = log.recent()[0]
        assert entry["kind"] == "mqtt"
        assert "ts" in entry
