"""Tests for bot.utils module — atomic JSON write utility."""

import json
import os
import tempfile

from bot.utils import atomic_json_write


class TestAtomicJsonWrite:
    def test_writes_valid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            data = {"key": "value", "number": 42}
            atomic_json_write(path, data)
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            os.unlink(path)

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "test.json")
            atomic_json_write(path, [1, 2, 3])
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == [1, 2, 3]

    def test_passes_kwargs_to_json_dump(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            data = {"中文": "测试"}
            atomic_json_write(path, data, ensure_ascii=False, indent=2)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "中文" in content  # not escaped
            assert "  " in content   # indented
        finally:
            os.unlink(path)

    def test_overwrites_existing_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"old": True}, f)
            path = f.name
        try:
            atomic_json_write(path, {"new": True})
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == {"new": True}
        finally:
            os.unlink(path)

    def test_no_tmp_file_left_on_success(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            atomic_json_write(path, {"ok": True})
            assert not os.path.exists(path + ".tmp")
        finally:
            os.unlink(path)
