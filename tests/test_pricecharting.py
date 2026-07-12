"""Tests for sources.pricecharting, using a real captured PriceCharting page as a fixture
(no network access needed for these tests)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sources.base import SourceUnavailable
from sources.pricecharting import PriceChartingSource, parse_price_table

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "pricecharting_etb_page.html").read_text()


def test_parse_price_table_extracts_sealed_etb_price():
    prices = parse_price_table(FIXTURE_HTML)
    assert prices["Ungraded"] == 159.06
    assert prices["Grade 7"] is None
    assert prices["PSA 10"] is None


def test_parse_price_table_raises_when_no_price_table():
    with pytest.raises(SourceUnavailable):
        parse_price_table("<html><body>not a product page</body></html>")


def test_fetch_raises_when_no_urls_configured():
    source = PriceChartingSource(http_client=MagicMock())
    with pytest.raises(SourceUnavailable):
        source.fetch({"id": "some-etb", "source_urls": {}})


def test_fetch_returns_snapshot_for_configured_label():
    mock_http = MagicMock()
    mock_http.get_text.return_value = FIXTURE_HTML
    source = PriceChartingSource(http_client=mock_http)

    product = {
        "id": "ascended-heroes-etb",
        "source_urls": {
            "pricecharting": {
                "etb_sealed": {
                    "url": "https://www.pricecharting.com/game/pokemon-ascended-heroes/elite-trainer-box",
                    "label": "Ungraded",
                }
            }
        },
    }

    results = source.fetch(product)

    assert len(results) == 1
    doc = results[0]
    assert doc["product_id"] == "ascended-heroes-etb"
    assert doc["price_type"] == "etb_sealed"
    assert doc["source"] == "pricecharting"
    assert doc["price"] == 159.06
    assert doc["currency"] == "USD"
    assert doc["raw_payload"]["label"] == "Ungraded"


def test_fetch_skips_when_configured_label_has_no_price():
    mock_http = MagicMock()
    mock_http.get_text.return_value = FIXTURE_HTML
    source = PriceChartingSource(http_client=mock_http)

    product = {
        "id": "ascended-heroes-etb",
        "source_urls": {
            "pricecharting": {
                "promo_psa10": {
                    "url": "https://www.pricecharting.com/game/pokemon-ascended-heroes/elite-trainer-box",
                    "label": "PSA 10",
                }
            }
        },
    }

    results = source.fetch(product)

    assert results == []


def test_fetch_skips_target_with_unknown_label():
    mock_http = MagicMock()
    mock_http.get_text.return_value = FIXTURE_HTML
    source = PriceChartingSource(http_client=mock_http)

    product = {
        "id": "ascended-heroes-etb",
        "source_urls": {
            "pricecharting": {
                "etb_sealed": {
                    "url": "https://www.pricecharting.com/game/x",
                    "label": "Nonexistent Label",
                }
            }
        },
    }

    results = source.fetch(product)

    assert results == []
