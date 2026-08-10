"""Tests for skills/amazon_cache.py — PROJ-172."""

import time

import pytest

from skills.amazon_cache import cache_key, TTLCache


# ── cache_key tests ───────────────────────────────────────────

def test_cache_key_is_case_insensitive():
    """AC: cache_key('Best Laptop') == cache_key('best laptop')."""
    assert cache_key("Best Laptop") == cache_key("best laptop")


def test_cache_key_strips_whitespace():
    assert cache_key("  laptop  ") == cache_key("laptop")


def test_cache_key_returns_md5_hex_string():
    key = cache_key("anything")
    assert isinstance(key, str)
    assert len(key) == 32
    assert all(c in "0123456789abcdef" for c in key)


def test_cache_key_different_queries_differ():
    assert cache_key("laptop") != cache_key("phone")


# ── TTLCache.get / set tests ──────────────────────────────────

def test_get_returns_none_for_missing_key():
    cache = TTLCache(ttl=10)
    assert cache.get("missing") is None


def test_set_then_get_returns_value():
    cache = TTLCache(ttl=10)
    cache.set("k", [1, 2, 3])
    assert cache.get("k") == [1, 2, 3]


def test_get_returns_none_after_ttl_expires():
    """AC: get() returns None after TTL expires."""
    cache = TTLCache(ttl=1)
    cache.set("k", ["value"])
    time.sleep(1.1)
    assert cache.get("k") is None


def test_get_returns_value_before_ttl_expires():
    cache = TTLCache(ttl=10)
    cache.set("k", ["value"])
    assert cache.get("k") == ["value"]


# ── TTLCache.clear_expired tests ──────────────────────────────

def test_clear_expired_removes_only_expired_entries():
    """AC: clear_expired() removes only expired entries."""
    cache = TTLCache(ttl=1)
    cache.set("old", ["expired-value"])
    time.sleep(1.1)
    cache.set("fresh", ["fresh-value"])

    cache.clear_expired()

    assert "old" not in cache
    assert "fresh" in cache
    assert cache.get("fresh") == ["fresh-value"]


def test_clear_expired_on_empty_cache_does_not_error():
    cache = TTLCache(ttl=10)
    cache.clear_expired()
    assert len(cache) == 0


# ── Default TTL test ──────────────────────────────────────────

def test_default_ttl_is_3600():
    cache = TTLCache()
    assert cache.ttl == 3600