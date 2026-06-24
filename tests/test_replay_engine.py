from unittest.mock import MagicMock

import pandas as pd
import pytest

from replay_engine import ReplayEngine


@pytest.fixture
def mock_dataframe():
    return pd.DataFrame({
        "col1": [1.0, 2.0, 3.0],
        "col2": [10.0, 20.0, 30.0],
    })


@pytest.fixture
def mock_loader(mock_dataframe):
    loader = MagicMock()
    loader.load_fault_run.return_value = mock_dataframe
    return loader


@pytest.fixture
def mock_catalog():
    catalog = MagicMock()
    catalog.fault_exists.return_value = True
    catalog.get_runs.return_value = [1, 2, 3]
    return catalog


@pytest.fixture
def engine(mock_loader, mock_catalog):
    return ReplayEngine(loader=mock_loader, catalog=mock_catalog)


class TestReplayEngineInit:
    def test_initial_state(self, engine):
        assert engine.running is False
        assert engine.current_fault is None
        assert engine.current_run is None
        assert engine.current_position == 0
        assert engine.current_dataframe is None

    def test_start(self, engine):
        engine.start()
        assert engine.running is True

    def test_stop(self, engine):
        engine.start()
        engine.stop()
        assert engine.running is False

    def test_reset(self, engine):
        engine.current_position = 10
        engine.reset()
        assert engine.current_position == 0


class TestReplayEngineSetFault:
    def test_set_fault_valid(self, engine, mock_loader, mock_dataframe):
        engine.set_fault(fault=5)

        assert engine.current_fault == 5
        assert engine.current_run in [1, 2, 3]
        assert engine.current_position == 0
        pd.testing.assert_frame_equal(
            engine.current_dataframe, mock_dataframe
        )
        mock_loader.load_fault_run.assert_called_once_with(
            fault=5, run=engine.current_run
        )

    def test_set_fault_invalid(self, engine, mock_catalog):
        mock_catalog.fault_exists.return_value = False

        with pytest.raises(ValueError, match="Unknown fault: 99"):
            engine.set_fault(fault=99)


class TestReplayEngineSetStream:
    def test_set_stream(self, engine, mock_loader, mock_dataframe):
        engine.set_stream(fault=3, run=7)

        assert engine.current_fault == 3
        assert engine.current_run == 7
        assert engine.current_position == 0
        pd.testing.assert_frame_equal(
            engine.current_dataframe, mock_dataframe
        )
        mock_loader.load_fault_run.assert_called_once_with(
            fault=3, run=7
        )


class TestReplayEngineNextSample:
    def test_next_sample_not_running(self, engine):
        result = engine.next_sample()
        assert result is None

    def test_next_sample_no_dataframe(self, engine):
        engine.start()
        result = engine.next_sample()
        assert result is None

    def test_next_sample_returns_row(self, engine):
        engine.start()
        engine.set_stream(fault=1, run=5)

        sample = engine.next_sample()

        assert sample is not None
        assert sample["col1"] == 1.0
        assert sample["col2"] == 10.0
        assert sample["_stream"] == {"fault": 1, "run": 5}
        assert engine.current_position == 1

    def test_next_sample_advances_position(self, engine):
        engine.start()
        engine.set_stream(fault=1, run=5)

        sample1 = engine.next_sample()
        sample2 = engine.next_sample()

        assert sample1["col1"] == 1.0
        assert sample2["col1"] == 2.0
        assert engine.current_position == 2

    def test_next_sample_end_of_run_wraps(
        self, engine, mock_catalog, mock_loader, mock_dataframe
    ):
        mock_catalog.get_runs.return_value = [42]
        mock_dataframe2 = pd.DataFrame({
            "col1": [9.0, 8.0],
            "col2": [90.0, 80.0],
        })
        mock_loader.load_fault_run.side_effect = [
            mock_dataframe,
            mock_dataframe2,
        ]

        engine.start()
        engine.set_stream(fault=1, run=5)

        engine.next_sample()
        engine.next_sample()
        engine.next_sample()

        sample = engine.next_sample()

        assert sample["col1"] == 9.0
        assert sample["_stream"] == {"fault": 1, "run": 42}
        assert engine.current_position == 1


class TestReplayEngineGetStatus:
    def test_get_status_default(self, engine):
        status = engine.get_status()

        assert status["running"] is False
        assert status["fault"] is None
        assert status["run"] is None
        assert status["position"] == 0
        assert status["loaded"] is False

    def test_get_status_after_setup(self, engine):
        engine.start()
        engine.set_stream(fault=2, run=4)

        status = engine.get_status()

        assert status["running"] is True
        assert status["fault"] == 2
        assert status["run"] == 4
        assert status["loaded"] is True
