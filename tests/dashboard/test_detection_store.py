from detection_store import DetectionStore, MAX_DETECTIONS


def make_anomaly_envelope(
    metric="reconstruction_error",
    value=1.5,
    fault=3,
    run=4,
):
    return {
        "source": "edge-detector",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "anomaly": True,
            "reason": "threshold exceeded",
            "metric": metric,
            "value": value,
            "fault": fault,
            "simulationRun": run,
            "sample": {"xmeas_1": 1.5},
            "sg_metrics": {},
            "ed_metrics": {"container": {"cpu_percent": 5.0}},
        },
    }


class TestDetectionStore:

    def test_handle_anomaly_stores_detection(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope())

        detections = store.recent_detections()
        assert len(detections) == 1
        assert detections[0]["metric"] == "reconstruction_error"
        assert detections[0]["value"] == 1.5
        assert detections[0]["fault"] == 3
        assert detections[0]["run"] == 4
        assert detections[0]["anomaly"] is True

    def test_latest_detection_tracks_last(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(value=1.0))
        store.handle_anomaly(make_anomaly_envelope(value=2.0))

        assert store.latest_detection()["value"] == 2.0

    def test_recent_detections_ordered_oldest_first(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(value=1.0))
        store.handle_anomaly(make_anomaly_envelope(value=2.0))

        values = [d["value"] for d in store.recent_detections()]
        assert values == [1.0, 2.0]

    def test_detections_trim_to_max(self):
        store = DetectionStore()
        for _ in range(MAX_DETECTIONS + 10):
            store.handle_anomaly(make_anomaly_envelope())

        assert len(store.recent_detections()) == MAX_DETECTIONS

    def test_handle_anomaly_logs_action(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(metric="z_score", value=2.5))

        actions = store.recent_actions()
        assert actions[0]["kind"] == "detect"
        assert "z_score" in actions[0]["text"]

    def test_empty_store(self):
        store = DetectionStore()
        assert store.recent_detections() == []
        assert store.latest_detection() is None
        assert store.recent_actions() == []
