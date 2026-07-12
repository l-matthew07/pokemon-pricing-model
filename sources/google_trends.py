"""Google Trends search-interest signal, via pytrends (no API key needed).

pytrends manages its own HTTP session/rate limiting against Google
Trends internally, so this source doesn't route through utils.http's
shared HttpClient/rate limiter — Google Trends has its own aggressive,
separately-managed rate limits.

Query text is config-driven: product["google_trends_query"] if set,
else product["set_name"]. Requesting a 12-month window returns
Google's weekly-resolution series; the most recent row is normally
`isPartial=True` (the current week isn't over yet), so we report the
last *complete* week instead of that partial one.
"""
from __future__ import annotations

from datetime import date

from sources.base import Source, SourceUnavailable
from utils.logging_config import get_logger

log = get_logger(__name__)

TIMEFRAME = "today 12-m"


class GoogleTrendsSource(Source):
    name = "google_trends"
    target_collection = "scarcity_signals"

    def __init__(self, http_client=None, pytrends_client=None):
        super().__init__(http_client)
        self._pytrends = pytrends_client

    def _get_pytrends(self):
        if self._pytrends is None:
            from pytrends.request import TrendReq
            self._pytrends = TrendReq(hl="en-US", tz=360)
        return self._pytrends

    def fetch(self, product: dict) -> list[dict]:
        query = product.get("google_trends_query") or product.get("set_name")
        if not query:
            raise SourceUnavailable(
                f"no google_trends_query or set_name configured for {product.get('id')}"
            )

        pytrends = self._get_pytrends()
        pytrends.build_payload([query], timeframe=TIMEFRAME, geo="")
        df = pytrends.interest_over_time()

        if df is None or df.empty:
            raise SourceUnavailable(f"no Google Trends data returned for query {query!r}")

        complete_rows = df[~df["isPartial"]] if "isPartial" in df.columns else df
        if complete_rows.empty:
            complete_rows = df
        row = complete_rows.iloc[-1]
        row_date: date = complete_rows.index[-1].date()

        return [{
            "product_id": product["id"],
            "date": row_date,
            "signal_type": "google_trends_index",
            "value": float(row[query]),
            "source": self.name,
            "raw_payload": {"query": query, "isPartial": bool(row.get("isPartial", False))},
        }]
