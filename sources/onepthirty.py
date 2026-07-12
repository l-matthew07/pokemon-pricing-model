"""130point.com — eBay sold-listing data for graded promo cards.

130point.com's search results load client-side against their own /api/
endpoint, and their robots.txt explicitly disallows crawling it
(`Disallow: /api/`). The site itself also sits behind a Cloudflare
managed JS challenge that blocks plain HTTP scraping regardless. So
this isn't a live scraper: look up sold listings yourself at
https://130point.com/sales/ and record them in manual_data/onepthirty.csv.

Expected CSV columns: product_id, date (YYYY-MM-DD), price_type
(promo_psa10 or promo_raw), price, currency (optional, defaults USD).
"""
from __future__ import annotations

from datetime import datetime

from sources.manual_import import ManualCsvSource


class OnePThirtySource(ManualCsvSource):
    name = "onepthirty"
    target_collection = "price_snapshots"
    csv_filename = "onepthirty.csv"

    def _row_to_doc(self, row: dict) -> dict:
        return {
            "product_id": row["product_id"],
            "date": datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
            "price_type": row["price_type"].strip(),
            "source": self.name,
            "price": float(row["price"]),
            "currency": (row.get("currency") or "USD").strip(),
            "raw_payload": dict(row),
        }
