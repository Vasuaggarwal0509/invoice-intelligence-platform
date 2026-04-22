"""Tests for the JSONL pipeline cache."""

import json

import pytest

from extraction_layer.backend.app.cache import PipelineCache


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / "cache.jsonl"


@pytest.fixture
def cache(cache_path):
    return PipelineCache(cache_path)


class TestRoundTrip:
    def test_empty_cache_misses(self, cache):
        assert cache.get("nope") is None
        assert cache.contains("nope") is False

    def test_put_then_get(self, cache):
        cache.put("inv-1", {"ocr": "..."})
        assert cache.get("inv-1") == {"ocr": "..."}
        assert cache.contains("inv-1")

    def test_put_writes_to_disk(self, cache, cache_path):
        cache.put("inv-1", {"a": 1})
        contents = cache_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(contents) == 1
        record = json.loads(contents[0])
        assert record == {"id": "inv-1", "data": {"a": 1}}

    def test_keys_lists_cached_ids(self, cache):
        cache.put("a", {"x": 1})
        cache.put("b", {"x": 2})
        assert set(cache.keys()) == {"a", "b"}


class TestPersistence:
    def test_reload_after_restart(self, cache_path):
        first = PipelineCache(cache_path)
        first.put("inv-42", {"ocr": "yeah"})

        # Simulate server restart by building a fresh cache object.
        second = PipelineCache(cache_path)
        assert second.get("inv-42") == {"ocr": "yeah"}

    def test_overwrite_takes_last_value(self, cache_path):
        first = PipelineCache(cache_path)
        first.put("inv-1", {"v": 1})
        first.put("inv-1", {"v": 2})

        second = PipelineCache(cache_path)
        assert second.get("inv-1") == {"v": 2}


class TestMalformedInput:
    def test_empty_lines_are_skipped(self, cache_path):
        cache_path.write_text(
            '\n\n{"id": "a", "data": {"x": 1}}\n\n',
            encoding="utf-8",
        )
        cache = PipelineCache(cache_path)
        assert cache.get("a") == {"x": 1}

    def test_corrupt_lines_are_ignored_not_fatal(self, cache_path):
        cache_path.write_text(
            'not-json\n{"id": "ok", "data": {"n": 5}}\n',
            encoding="utf-8",
        )
        cache = PipelineCache(cache_path)
        assert cache.get("ok") == {"n": 5}

    def test_record_missing_id_or_data_is_ignored(self, cache_path):
        cache_path.write_text(
            '{"id": "a"}\n'                    # no data
            '{"data": {"x": 1}}\n'             # no id
            '{"id": "b", "data": {"x": 2}}\n'  # valid
            ,
            encoding="utf-8",
        )
        cache = PipelineCache(cache_path)
        assert cache.get("a") is None
        assert cache.get("b") == {"x": 2}


class TestThreadSafetyLight:
    """Basic check — multiple puts from the same thread should all persist."""

    def test_many_puts_roundtrip(self, cache, cache_path):
        for i in range(50):
            cache.put(f"inv-{i}", {"idx": i})
        fresh = PipelineCache(cache_path)
        for i in range(50):
            assert fresh.get(f"inv-{i}") == {"idx": i}
