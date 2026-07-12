"""Tests for sources.google_trends. Uses a fake pytrends client (no network access) —
Google Trends itself is verified live separately, but the test suite shouldn't
depend on its network availability or rate limits."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from sources.base import SourceUnavailable
from sources.google_trends import GoogleTrendsSource


def _fake_pytrends(df: pd.DataFrame) -> MagicMock:
    client = MagicMock()
    client.interest_over_time.return_value = df
    return client


def test_fetch_raises_when_no_query_configured():
    source = GoogleTrendsSource(pytrends_client=MagicMock())
    with pytest.raises(SourceUnavailable, match="no google_trends_query"):
        source.fetch({"id": "some-etb"})


def test_fetch_raises_when_no_data_returned():
    empty_df = pd.DataFrame()
    source = GoogleTrendsSource(pytrends_client=_fake_pytrends(empty_df))
    with pytest.raises(SourceUnavailable, match="no Google Trends data"):
        source.fetch({"id": "some-etb", "set_name": "Some Set"})


def test_fetch_uses_last_complete_week_not_partial_current_week():
    df = pd.DataFrame(
        {
            "Some Set": [79, 76, 50, 43, 36],
            "isPartial": [False, False, False, False, True],
        },
        index=pd.to_datetime(["2026-06-14", "2026-06-21", "2026-06-28", "2026-07-05", "2026-07-12"]),
    )
    source = GoogleTrendsSource(pytrends_client=_fake_pytrends(df))

    results = source.fetch({"id": "some-etb", "set_name": "Some Set"})

    assert len(results) == 1
    doc = results[0]
    assert doc["value"] == 43.0
    assert str(doc["date"]) == "2026-07-05"
    assert doc["signal_type"] == "google_trends_index"
    assert doc["raw_payload"]["isPartial"] is False


def test_fetch_falls_back_to_last_row_if_all_partial():
    df = pd.DataFrame(
        {"Some Set": [10], "isPartial": [True]},
        index=pd.to_datetime(["2026-07-12"]),
    )
    source = GoogleTrendsSource(pytrends_client=_fake_pytrends(df))

    results = source.fetch({"id": "some-etb", "set_name": "Some Set"})
    assert results[0]["value"] == 10.0


def test_fetch_prefers_explicit_trends_query_over_set_name():
    df = pd.DataFrame(
        {"Custom Query": [55], "isPartial": [False]},
        index=pd.to_datetime(["2026-07-05"]),
    )
    client = _fake_pytrends(df)
    source = GoogleTrendsSource(pytrends_client=client)

    source.fetch({"id": "some-etb", "set_name": "Some Set", "google_trends_query": "Custom Query"})

    client.build_payload.assert_called_once_with(["Custom Query"], timeframe="today 12-m", geo="")
