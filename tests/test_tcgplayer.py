"""Tests for sources.tcgplayer. No real API key or network access used — everything
is mocked, since this module is meant to work correctly the moment a real key is added."""
from unittest.mock import MagicMock

import pytest

from sources.base import SourceUnavailable
from sources.tcgplayer import TcgplayerSource


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv("TCGPLAYER_CLIENT_ID", raising=False)
    monkeypatch.delenv("TCGPLAYER_CLIENT_SECRET", raising=False)


def test_is_configured_false_without_env_vars():
    source = TcgplayerSource(http_client=MagicMock())
    assert source.is_configured() is False


def test_is_configured_true_with_both_env_vars(monkeypatch):
    monkeypatch.setenv("TCGPLAYER_CLIENT_ID", "id")
    monkeypatch.setenv("TCGPLAYER_CLIENT_SECRET", "secret")
    source = TcgplayerSource(http_client=MagicMock())
    assert source.is_configured() is True


def test_fetch_raises_source_unavailable_when_not_configured():
    source = TcgplayerSource(http_client=MagicMock())
    with pytest.raises(SourceUnavailable, match="TCGPLAYER_CLIENT_ID"):
        source.fetch({"id": "some-etb", "source_urls": {"tcgplayer": {"etb_sealed": {"product_id": 123}}}})


def test_fetch_raises_when_no_product_ids_configured(monkeypatch):
    monkeypatch.setenv("TCGPLAYER_CLIENT_ID", "id")
    monkeypatch.setenv("TCGPLAYER_CLIENT_SECRET", "secret")
    source = TcgplayerSource(http_client=MagicMock())
    with pytest.raises(SourceUnavailable, match="no tcgplayer product IDs"):
        source.fetch({"id": "some-etb", "source_urls": {}})


def test_fetch_returns_snapshot_using_market_price(monkeypatch):
    monkeypatch.setenv("TCGPLAYER_CLIENT_ID", "id")
    monkeypatch.setenv("TCGPLAYER_CLIENT_SECRET", "secret")

    mock_http = MagicMock()
    mock_http.post_json.return_value = {"access_token": "tok123", "expires_in": 3600}
    mock_http.get_json.return_value = {"results": [{"marketPrice": 91.5, "subTypeName": "Normal"}]}

    source = TcgplayerSource(http_client=mock_http)
    product = {
        "id": "prismatic-evolutions-etb",
        "source_urls": {"tcgplayer": {"etb_sealed": {"product_id": 555555}}},
    }

    results = source.fetch(product)

    assert len(results) == 1
    doc = results[0]
    assert doc["product_id"] == "prismatic-evolutions-etb"
    assert doc["price_type"] == "etb_sealed"
    assert doc["source"] == "tcgplayer"
    assert doc["price"] == 91.5
    mock_http.post_json.assert_called_once()  # token requested once
    mock_http.get_json.assert_called_once()


def test_fetch_reuses_cached_token_across_calls(monkeypatch):
    monkeypatch.setenv("TCGPLAYER_CLIENT_ID", "id")
    monkeypatch.setenv("TCGPLAYER_CLIENT_SECRET", "secret")

    mock_http = MagicMock()
    mock_http.post_json.return_value = {"access_token": "tok123", "expires_in": 3600}
    mock_http.get_json.return_value = {"results": [{"marketPrice": 91.5}]}

    source = TcgplayerSource(http_client=mock_http)
    product = {
        "id": "prismatic-evolutions-etb",
        "source_urls": {"tcgplayer": {"etb_sealed": {"product_id": 555555}}},
    }

    source.fetch(product)
    source.fetch(product)

    assert mock_http.post_json.call_count == 1  # token cached, not refetched
    assert mock_http.get_json.call_count == 2


def test_fetch_skips_product_missing_market_price(monkeypatch):
    monkeypatch.setenv("TCGPLAYER_CLIENT_ID", "id")
    monkeypatch.setenv("TCGPLAYER_CLIENT_SECRET", "secret")

    mock_http = MagicMock()
    mock_http.post_json.return_value = {"access_token": "tok123", "expires_in": 3600}
    mock_http.get_json.return_value = {"results": [{"marketPrice": None}]}

    source = TcgplayerSource(http_client=mock_http)
    product = {
        "id": "prismatic-evolutions-etb",
        "source_urls": {"tcgplayer": {"etb_sealed": {"product_id": 555555}}},
    }

    results = source.fetch(product)
    assert results == []
