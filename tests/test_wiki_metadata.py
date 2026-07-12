"""Tests for sources.wiki_metadata, using real captured Bulbapedia infobox
fixtures (no network access needed)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sources.base import SourceUnavailable
from sources.wiki_metadata import WikiMetadataSource, parse_set_infobox

FIXTURES = Path(__file__).parent / "fixtures"
PRISMATIC_HTML = (FIXTURES / "bulbapedia_prismatic_evolutions.html").read_text()
PALDEA_HTML = (FIXTURES / "bulbapedia_paldea_evolved.html").read_text()


def test_parse_single_language_set():
    result = parse_set_infobox(PRISMATIC_HTML)
    assert result == {"set_size": 180, "release_date": __import__("datetime").date(2025, 1, 17)}


def test_parse_bilingual_set_includes_jp_release_date():
    result = parse_set_infobox(PALDEA_HTML)
    import datetime as dt
    assert result["set_size"] == 279
    assert result["release_date"] == dt.date(2023, 6, 9)
    assert result["jp_release_date"] == dt.date(2023, 4, 14)


def test_parse_returns_empty_dict_when_no_infobox_found():
    assert parse_set_infobox("<html><body>no infobox here</body></html>") == {}


def test_fetch_raises_when_no_bulbapedia_url():
    source = WikiMetadataSource(http_client=MagicMock())
    with pytest.raises(SourceUnavailable, match="no bulbapedia URL"):
        source.fetch({"id": "some-etb", "source_urls": {}})


def test_fetch_raises_when_page_has_no_infobox():
    mock_http = MagicMock()
    mock_http.get_text.return_value = "<html><body>nothing here</body></html>"
    source = WikiMetadataSource(http_client=mock_http)
    with pytest.raises(SourceUnavailable, match="could not find a set infobox"):
        source.fetch({"id": "some-etb", "source_urls": {"bulbapedia": "https://example.com/x"}})


def test_fetch_uses_scraped_values_when_config_omits_them():
    mock_http = MagicMock()
    mock_http.get_text.return_value = PRISMATIC_HTML
    source = WikiMetadataSource(http_client=mock_http)

    product = {
        "id": "prismatic-evolutions-etb",
        "source_urls": {"bulbapedia": "https://bulbapedia.bulbagarden.net/wiki/Prismatic_Evolutions_(TCG)"},
    }

    results = source.fetch(product)
    assert len(results) == 1
    doc = results[0]
    assert doc["_id"] == "prismatic-evolutions-etb"
    assert doc["set_size"] == 180


def test_fetch_lets_config_value_override_scraped_value():
    mock_http = MagicMock()
    mock_http.get_text.return_value = PRISMATIC_HTML
    source = WikiMetadataSource(http_client=mock_http)

    product = {
        "id": "prismatic-evolutions-etb",
        "set_size": 999,  # hand-curated override
        "source_urls": {"bulbapedia": "https://bulbapedia.bulbagarden.net/wiki/Prismatic_Evolutions_(TCG)"},
    }

    results = source.fetch(product)
    assert results[0]["set_size"] == 999
