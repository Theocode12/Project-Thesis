from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_loader import DataLoader


class TestDataLoaderInit:

    def test_stores_runtime_directory(self, tmp_path):
        loader = DataLoader(str(tmp_path))
        assert loader.runtime_directory == Path(str(tmp_path))

    def test_non_existent_directory(self, tmp_path):
        loader = DataLoader(str(tmp_path / "nonexistent"))
        assert loader.runtime_directory.name == "nonexistent"


class TestDataLoaderLoadFaultRun:

    def test_loads_parquet_file(self, tmp_path):
        fault_dir = tmp_path / "fault_1"
        fault_dir.mkdir()
        file_path = fault_dir / "run_5.parquet"
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        df.to_parquet(str(file_path))

        loader = DataLoader(str(tmp_path))
        result = loader.load_fault_run(fault=1, run=5)
        pd.testing.assert_frame_equal(result, df)

    def test_raises_file_not_found(self, tmp_path):
        loader = DataLoader(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="Dataset not found"):
            loader.load_fault_run(fault=99, run=99)

    def test_constructs_correct_path(self, tmp_path):
        fault_dir = tmp_path / "fault_3"
        fault_dir.mkdir()
        file_path = fault_dir / "run_7.parquet"
        pd.DataFrame({"x": [1.0]}).to_parquet(str(file_path))

        loader = DataLoader(str(tmp_path))
        loader.load_fault_run(fault=3, run=7)
        assert (tmp_path / "fault_3" / "run_7.parquet").exists()

    def test_multiple_faults_and_runs(self, tmp_path):
        for fault in [1, 2]:
            fd = tmp_path / f"fault_{fault}"
            fd.mkdir()
            for run in [1, 2]:
                pd.DataFrame({"v": [float(fault * run)]}).to_parquet(
                    str(fd / f"run_{run}.parquet")
                )

        loader = DataLoader(str(tmp_path))
        r1 = loader.load_fault_run(fault=1, run=1)
        r2 = loader.load_fault_run(fault=2, run=2)
        assert r1.iloc[0]["v"] == 1.0
        assert r2.iloc[0]["v"] == 4.0
