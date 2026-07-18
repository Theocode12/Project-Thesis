import json

import pytest

from catalog import Catalog


@pytest.fixture
def catalog_data():
    return {
        "fault_0": {"runs": [1, 2, 3], "run_count": 3},
        "fault_1": {"runs": [4, 5], "run_count": 2},
        "fault_2": {"runs": [6, 7, 8, 9], "run_count": 4},
    }


@pytest.fixture
def catalog_path(tmp_path, catalog_data):
    path = tmp_path / "catalog.json"
    with open(path, "w") as f:
        json.dump(catalog_data, f)
    return str(path)


@pytest.fixture
def catalog(catalog_path):
    return Catalog(catalog_path)


class TestCatalogInit:

    def test_loads_catalog(self, catalog, catalog_data):
        assert catalog.catalog == catalog_data

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Catalog(str(tmp_path / "nonexistent.json"))


class TestCatalogGetFaults:

    def test_returns_sorted_faults(self, catalog):
        assert catalog.get_faults() == [0, 1, 2]

    def test_single_fault(self, tmp_path):
        path = tmp_path / "c.json"
        with open(path, "w") as f:
            json.dump({"fault_5": {"runs": [1], "run_count": 1}}, f)
        c = Catalog(str(path))
        assert c.get_faults() == [5]

    def test_empty_catalog(self, tmp_path):
        path = tmp_path / "c.json"
        with open(path, "w") as f:
            json.dump({}, f)
        c = Catalog(str(path))
        assert c.get_faults() == []


class TestCatalogGetRuns:

    def test_returns_runs(self, catalog):
        assert catalog.get_runs(0) == [1, 2, 3]
        assert catalog.get_runs(1) == [4, 5]

    def test_raises_on_unknown_fault(self, catalog):
        with pytest.raises(ValueError, match="Unknown fault: 99"):
            catalog.get_runs(99)


class TestCatalogGetRunCount:

    def test_returns_count(self, catalog):
        assert catalog.get_run_count(0) == 3
        assert catalog.get_run_count(2) == 4

    def test_raises_on_unknown_fault(self, catalog):
        with pytest.raises(KeyError):
            catalog.get_run_count(99)


class TestCatalogFaultExists:

    def test_exists(self, catalog):
        assert catalog.fault_exists(0) is True
        assert catalog.fault_exists(2) is True

    def test_not_exists(self, catalog):
        assert catalog.fault_exists(99) is False
