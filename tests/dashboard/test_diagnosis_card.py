import components as c


class TestConfidenceTone:

    def test_green_band(self):
        assert c.confidence_tone(1.0) == "run"
        assert c.confidence_tone(0.95) == "run"
        assert c.confidence_tone(0.90) == "run"

    def test_amber_band(self):
        assert c.confidence_tone(0.89) == "pause"
        assert c.confidence_tone(0.80) == "pause"
        assert c.confidence_tone(0.70) == "pause"

    def test_red_band(self):
        assert c.confidence_tone(0.69) == "stop"
        assert c.confidence_tone(0.0) == "stop"

    def test_none(self):
        assert c.confidence_tone(None) == "info"


class TestDiagnosisCard:

    def test_empty_state(self):
        html = c.diagnosis_card(None, None, None)

        assert "Awaiting diagnosis result" in html
        assert "edge-diagnosis--info" in html

    def test_renders_fault_and_diagnosis(self):
        html = c.diagnosis_card(4, "fault_4", 1.0)

        assert "Fault" in html
        assert "4" in html
        assert "fault_4" in html
        assert "100<small>%</small>" in html
        assert "edge-diagnosis--run" in html

    def test_confidence_colour_band(self):
        assert "edge-diagnosis--run" in c.diagnosis_card(1, "fault_1", 0.95)
        assert "edge-diagnosis--pause" in c.diagnosis_card(1, "fault_1", 0.80)
        assert "edge-diagnosis--stop" in c.diagnosis_card(1, "fault_1", 0.50)

    def test_fill_width_tracks_confidence(self):
        html = c.diagnosis_card(4, "fault_4", 0.75)

        assert 'style="width:75.0%"' in html

    def test_escapes_diagnosis_text(self):
        html = c.diagnosis_card(4, "<script>fault</script>", 0.9)

        assert "&lt;script&gt;" in html
        assert "<script>" not in html
