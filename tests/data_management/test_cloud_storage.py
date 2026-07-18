import json
import os
from unittest.mock import patch

import pytest

from cloud_storage import LocalDirectoryCloudStorage


class TestLocalDirectoryCloudStorage:

    def test_creates_directory(self, tmp_path):
        d = str(tmp_path / "uploads")
        LocalDirectoryCloudStorage(directory=d)
        assert os.path.isdir(d)

    def test_store_creates_file(self, tmp_path):
        d = str(tmp_path / "uploads")
        storage = LocalDirectoryCloudStorage(directory=d)
        result = storage.store("batch_abc", [{"a": 1}, {"b": 2}])
        assert result is True
        assert os.path.isfile(os.path.join(d, "batch_abc.json"))

    def test_store_writes_correct_content(self, tmp_path):
        d = str(tmp_path / "uploads")
        storage = LocalDirectoryCloudStorage(directory=d)
        data = [{"x": 1}, {"y": 2}]
        storage.store("batch_xyz", data)
        path = os.path.join(d, "batch_xyz.json")
        with open(path, "r") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_store_returns_true_on_success(self, tmp_path):
        storage = LocalDirectoryCloudStorage(directory=str(tmp_path / "uploads"))
        assert storage.store("b1", [{"a": 1}]) is True

    def test_is_available_returns_true(self, tmp_path):
        storage = LocalDirectoryCloudStorage(directory=str(tmp_path / "uploads"))
        assert storage.is_available() is True

    def test_is_available_returns_false_for_unwritable(self):
        with patch("os.access", return_value=False):
            storage = LocalDirectoryCloudStorage(directory="/nonexistent")
            assert storage.is_available() is False

    def test_multiple_batches(self, tmp_path):
        d = str(tmp_path / "uploads")
        storage = LocalDirectoryCloudStorage(directory=d)
        storage.store("b1", [{"a": 1}])
        storage.store("b2", [{"b": 2}])
        assert os.path.isfile(os.path.join(d, "b1.json"))
        assert os.path.isfile(os.path.join(d, "b2.json"))

    def test_existing_directory(self, tmp_path):
        d = str(tmp_path / "existing")
        os.makedirs(d)
        storage = LocalDirectoryCloudStorage(directory=d)
        assert storage.is_available() is True
        assert storage.store("b1", [{"a": 1}]) is True

    def test_store_empty_list(self, tmp_path):
        d = str(tmp_path / "uploads")
        storage = LocalDirectoryCloudStorage(directory=d)
        assert storage.store("empty", []) is True
        path = os.path.join(d, "empty.json")
        with open(path, "r") as f:
            assert json.load(f) == []
