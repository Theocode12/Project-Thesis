import json
import os

import pytest

from local_storage import LocalStorage


class TestLocalStorageSave:

    def test_creates_directory(self, tmp_path):
        d = str(tmp_path / "cache")
        LocalStorage(cache_dir=d)
        assert os.path.isdir(d)

    def test_creates_data_file(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("batch_abc", [{"a": 1}])
        assert os.path.isfile(os.path.join(d, "batch_abc.json"))

    def test_writes_correct_content(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        data = [{"x": 1, "y": 2}, {"z": 3}]
        storage.save("batch_xyz", data)
        path = os.path.join(d, "batch_xyz.json")
        with open(path, "r") as f:
            assert json.load(f) == data

    def test_creates_index_file(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("batch_abc", [{"a": 1}])
        assert os.path.isfile(os.path.join(d, ".index.json"))

    def test_index_has_correct_entry(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("batch_abc", [{"a": 1}])
        path = os.path.join(d, ".index.json")
        with open(path, "r") as f:
            index = json.load(f)
        assert "batch_abc" in index
        assert index["batch_abc"]["state"] == "pending"
        assert index["batch_abc"]["count"] == 1

    def test_save_empty_list(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("empty", [])
        assert os.path.isfile(os.path.join(d, "empty.json"))


class TestLocalStorageRead:

    def test_read_returns_saved_data(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        data = [{"a": 1}, {"b": 2}]
        storage.save("batch_abc", data)
        assert storage.read("batch_abc") == data

    def test_read_missing_returns_none(self, tmp_path):
        storage = LocalStorage(cache_dir=str(tmp_path / "cache"))
        assert storage.read("nonexistent") is None

    def test_read_multiple_batches(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.save("b2", [{"b": 2}])
        assert storage.read("b1") == [{"a": 1}]
        assert storage.read("b2") == [{"b": 2}]


class TestLocalStorageMarkSynced:

    def test_mark_synced_updates_state(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("batch_abc", [{"a": 1}])
        storage.mark_synced("batch_abc")
        path = os.path.join(d, ".index.json")
        with open(path, "r") as f:
            index = json.load(f)
        assert index["batch_abc"]["state"] == "synced"

    def test_mark_synced_nonexistent_does_nothing(self, tmp_path):
        storage = LocalStorage(cache_dir=str(tmp_path / "cache"))
        storage.mark_synced("nonexistent")
        path = os.path.join(str(tmp_path / "cache"), ".index.json")
        assert not os.path.exists(path)


class TestLocalStorageGetPending:

    def test_all_pending_initially(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.save("b2", [{"b": 2}])
        pending = storage.get_pending_batches()
        assert set(pending.keys()) == {"b1", "b2"}

    def test_excludes_synced(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.save("b2", [{"b": 2}])
        storage.mark_synced("b1")
        pending = storage.get_pending_batches()
        assert "b1" not in pending
        assert "b2" in pending

    def test_returns_count(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.save("b2", [{"b": 2}])
        pending = storage.get_pending_batches()
        assert pending["b1"]["count"] == 1
        assert pending["b2"]["count"] == 1


class TestLocalStorageCleanup:

    def test_removes_old_synced_batches(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.mark_synced("b1")
        with open(os.path.join(d, ".index.json"), "r") as f:
            index = json.load(f)
        index["b1"]["timestamp"] = "2000-01-01T00:00:00+00:00"
        with open(os.path.join(d, ".index.json"), "w") as f:
            json.dump(index, f)
        storage._load_index()
        removed = storage.cleanup_synced(max_age_seconds=3600)
        assert removed == 1
        assert not os.path.isfile(os.path.join(d, "b1.json"))

    def test_preserves_recent_synced(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.mark_synced("b1")
        removed = storage.cleanup_synced(max_age_seconds=3600)
        assert removed == 0
        assert os.path.isfile(os.path.join(d, "b1.json"))

    def test_preserves_pending_batches(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.save("b2", [{"b": 2}])
        storage.mark_synced("b1")
        with open(os.path.join(d, ".index.json"), "r") as f:
            index = json.load(f)
        index["b1"]["timestamp"] = "2000-01-01T00:00:00+00:00"
        with open(os.path.join(d, ".index.json"), "w") as f:
            json.dump(index, f)
        storage._load_index()
        removed = storage.cleanup_synced(max_age_seconds=3600)
        assert removed == 1
        assert os.path.isfile(os.path.join(d, "b2.json"))

    def test_no_synced_batches(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        removed = storage.cleanup_synced(max_age_seconds=3600)
        assert removed == 0

    def test_empty_cache(self, tmp_path):
        storage = LocalStorage(cache_dir=str(tmp_path / "cache"))
        removed = storage.cleanup_synced(max_age_seconds=3600)
        assert removed == 0

    def test_removes_index_entry(self, tmp_path):
        d = str(tmp_path / "cache")
        storage = LocalStorage(cache_dir=d)
        storage.save("b1", [{"a": 1}])
        storage.mark_synced("b1")
        with open(os.path.join(d, ".index.json"), "r") as f:
            index = json.load(f)
        index["b1"]["timestamp"] = "2000-01-01T00:00:00+00:00"
        with open(os.path.join(d, ".index.json"), "w") as f:
            json.dump(index, f)
        storage._load_index()
        storage.cleanup_synced(max_age_seconds=3600)
        with open(os.path.join(d, ".index.json"), "r") as f:
            index = json.load(f)
        assert "b1" not in index


class TestLocalStorageIndexPersistence:

    def test_index_loaded_on_reinit(self, tmp_path):
        d = str(tmp_path / "cache")
        storage1 = LocalStorage(cache_dir=d)
        storage1.save("b1", [{"a": 1}])
        storage2 = LocalStorage(cache_dir=d)
        pending = storage2.get_pending_batches()
        assert "b1" in pending

    def test_state_persists_across_instances(self, tmp_path):
        d = str(tmp_path / "cache")
        storage1 = LocalStorage(cache_dir=d)
        storage1.save("b1", [{"a": 1}])
        storage1.mark_synced("b1")
        storage2 = LocalStorage(cache_dir=d)
        assert "b1" not in storage2.get_pending_batches()
