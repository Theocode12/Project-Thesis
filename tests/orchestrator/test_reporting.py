import json
from unittest.mock import MagicMock, patch

from reporting import DiagnosisReporter


class TestDiagnosisReporter:

    @staticmethod
    def response(status_code=202):
        response = MagicMock()
        response.status_code = status_code
        return response

    @patch("reporting.requests.post")
    def test_measures_complete_utf8_request_body(self, post):
        post.return_value = self.response()
        reporter = DiagnosisReporter(endpoint="http://classifier/diagnose")
        batch = [{"xmeas_1": 1.0}]
        meta = {
            "det_metrics": {"inference_ended_at": 1000.003},
            "event_audit": [{"det_metrics": {"value": "é"}}],
        }

        assert reporter.report(batch, meta) is True

        expected = json.dumps({"batch": batch, "meta": meta}).encode("utf-8")
        kwargs = post.call_args.kwargs
        assert kwargs["data"] == expected
        assert kwargs["headers"] == {"Content-Type": "application/json"}
        assert reporter.last_request_payload_bytes == len(expected)

    @patch("reporting.requests.post")
    def test_failed_request_is_not_successful_report(self, post):
        response = self.response()
        response.raise_for_status.side_effect = RuntimeError("failed")
        post.return_value = response
        reporter = DiagnosisReporter(endpoint="http://classifier/diagnose")

        assert reporter.report([{"x": 1}], {}) is False
        assert reporter.last_request_payload_bytes > 0

    def test_unconfigured_report_has_zero_bytes(self):
        reporter = DiagnosisReporter()

        assert reporter.report([{"x": 1}], {}) is False
        assert reporter.last_request_payload_bytes == 0
