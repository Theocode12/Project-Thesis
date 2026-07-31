import pytest

from decision_engine import DecisionEngine


def make_event(
    stream_interval=0.1,
    fault=0,
    sample=None,
):
    return {
        "payload": {
            "sample": (
                sample
                or {
                    "XMEAS_1": 1.0,
                    "faultNumber": fault,
                    "simulationRun": 1,
                }
            ),
            "sg_metrics": {
                "stream_interval": stream_interval,
            },
            "fault": fault,
            "ed_metrics": {},
        }
    }


@pytest.fixture
def engine():
    return DecisionEngine(
        window_seconds=10.0,
        high_ratio=0.5,
        low_ratio=0.1,
        fallback_stream_interval=0.1,
    )


class TestDecisionEngineBuffer:

    def test_add_anomaly_and_buffer_size(self, engine):
        engine.add_anomaly(make_event())
        assert engine.buffer_size() == 1

    def test_reset_clears_buffer(self, engine):
        engine.add_anomaly(make_event())
        engine.reset()
        assert engine.buffer_size() == 0


class TestDecisionEngineEvaluate:

    def test_empty_window_returns_normal(self, engine):
        decision = engine.evaluate()

        assert decision["decision"] == "normal"
        assert decision["anomaly_count"] == 0
        assert decision["batch"] == []
        assert decision["reported"] is False

    def test_evaluate_clears_window(self, engine):
        engine.add_anomaly(make_event())
        engine.evaluate()
        assert engine.buffer_size() == 0

    def test_anomaly_every_sample_is_real(self, engine):
        for _ in range(10):
            engine.add_anomaly(make_event(stream_interval=1.0))

        decision = engine.evaluate()

        assert decision["sensor_rate"] == 1.0
        assert decision["total_samples"] == 10.0
        assert decision["anomaly_ratio"] == 1.0
        assert decision["decision"] == "anomaly"

    def test_anomaly_every_five_seconds_is_uncertain(self, engine):
        for _ in range(2):
            engine.add_anomaly(make_event(stream_interval=1.0))

        decision = engine.evaluate()

        assert decision["anomaly_ratio"] == pytest.approx(0.2)
        assert decision["decision"] == "uncertain"

    def test_anomaly_every_ten_seconds_is_false_positive(self, engine):
        engine.add_anomaly(make_event(stream_interval=1.0))

        decision = engine.evaluate()

        assert decision["anomaly_ratio"] == pytest.approx(0.1)
        assert decision["decision"] == "normal"

    def test_ratio_clamped_to_one(self, engine):
        for _ in range(50):
            engine.add_anomaly(make_event(stream_interval=1.0))

        decision = engine.evaluate()

        assert decision["anomaly_ratio"] == 1.0

    def test_falls_back_when_metrics_missing(self, engine):
        event = make_event()
        event["payload"]["sg_metrics"] = {}

        engine.add_anomaly(event)
        decision = engine.evaluate()

        assert decision["sensor_rate"] == pytest.approx(10.0)
        assert decision["anomaly_ratio"] == pytest.approx(0.01)

    def test_batch_contains_anomalous_samples(self, engine):
        for fault in (1, 1, 2):
            engine.add_anomaly(make_event(fault=fault))

        decision = engine.evaluate()

        assert decision["batch_size"] == 3
        assert all(s["faultNumber"] in (1, 2) for s in decision["batch"])

    def test_anomaly_rate_computed(self, engine):
        for _ in range(5):
            engine.add_anomaly(make_event(stream_interval=0.1))

        decision = engine.evaluate()

        assert decision["anomaly_rate"] == pytest.approx(0.5)

    def test_sg_metrics_carried_into_decision(self, engine):
        engine.add_anomaly(make_event(stream_interval=0.1))

        decision = engine.evaluate()

        assert decision["sg_metrics"]["stream_interval"] == 0.1

    def test_sg_metrics_uses_latest_event(self, engine):
        engine.add_anomaly(make_event(stream_interval=0.1))
        engine.add_anomaly(make_event(stream_interval=0.5))

        decision = engine.evaluate()

        assert decision["sg_metrics"]["stream_interval"] == 0.5

    def test_sg_metrics_empty_for_empty_window(self, engine):
        decision = engine.evaluate()

        assert decision["sg_metrics"] == {}
