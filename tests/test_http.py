"""Tests for utils.http: rate limiting and disk caching, without hitting the network."""
import time
from unittest.mock import MagicMock, patch

import pytest

import requests

import utils.http as http_module
from utils.http import HttpClient, RateLimiter


def _fake_response(text="<html>ok</html>", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if status_code >= 400:
        resp.raise_for_status = MagicMock(side_effect=requests.HTTPError(response=resp))
    else:
        resp.raise_for_status = MagicMock()
    return resp


def test_rate_limiter_enforces_minimum_delay(monkeypatch):
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "example.com", 0.2)
    limiter = RateLimiter()

    t0 = time.monotonic()
    limiter.wait("example.com")
    limiter.wait("example.com")
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.2


def test_rate_limiter_different_domains_dont_block_each_other(monkeypatch):
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "a.com", 5.0)
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "b.com", 5.0)
    limiter = RateLimiter()

    limiter.wait("a.com")
    t0 = time.monotonic()
    limiter.wait("b.com")  # different domain, should not wait for a.com's delay
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0


def test_get_text_uses_cache_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setattr(http_module, "CACHE_DIR", tmp_path)
    client = HttpClient()
    client.rate_limiter = RateLimiter()
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "example.com", 0)

    mock_get = MagicMock(return_value=_fake_response("<html>hello</html>"))
    client.session.get = mock_get

    url = "https://example.com/page"
    first = client.get_text(url)
    second = client.get_text(url)

    assert first == second == "<html>hello</html>"
    assert mock_get.call_count == 1  # second call served from disk cache


def test_get_text_bypasses_cache_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(http_module, "CACHE_DIR", tmp_path)
    client = HttpClient()
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "example.com", 0)

    mock_get = MagicMock(return_value=_fake_response("<html>hello</html>"))
    client.session.get = mock_get

    url = "https://example.com/page"
    client.get_text(url, use_cache=False)
    client.get_text(url, use_cache=False)

    assert mock_get.call_count == 2


def test_get_text_retries_on_server_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(http_module, "CACHE_DIR", tmp_path)
    client = HttpClient()
    monkeypatch.setitem(http_module.DOMAIN_DELAYS, "example.com", 0)

    fail_response = _fake_response("", status_code=503)
    ok_response = _fake_response("<html>recovered</html>", status_code=200)
    mock_get = MagicMock(side_effect=[fail_response, ok_response])
    client.session.get = mock_get

    result = client.get_text("https://example.com/flaky", use_cache=False)

    assert result == "<html>recovered</html>"
    assert mock_get.call_count == 2
