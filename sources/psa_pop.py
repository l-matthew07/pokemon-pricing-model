"""PSA population report (psacard.com/pop) — scarcity proxy for graded promos.

psacard.com sits behind a Cloudflare managed JS challenge that blocks
plain HTTP scraping outright (confirmed by hand: even robots.txt itself
returns a "Just a moment..." challenge page instead of content).
Automating past that would mean evading bot detection, which this
project won't do. Instead: look up the population count yourself at
https://www.psacard.com/pop and record it in manual_data/psa_pop.csv.

Expected CSV columns: product_id, date (YYYY-MM-DD), value (the PSA 10
population count for that date).
"""
from __future__ import annotations

from datetime import datetime

from sources.manual_import import ManualCsvSource


class PsaPopSource(ManualCsvSource):
    name = "psa_pop"
    target_collection = "scarcity_signals"
    csv_filename = "psa_pop.csv"

    def _row_to_doc(self, row: dict) -> dict:
        return {
            "product_id": row["product_id"],
            "date": datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
            "signal_type": "psa_pop_count",
            "value": float(row["value"]),
            "source": self.name,
        }
