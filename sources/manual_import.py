"""Generic manual-CSV-import source.

Fallback for sites that can't be scraped respectfully. Right now that's
130point.com and psacard.com/pop — both sit behind Cloudflare's managed
JS challenge, which blocks plain HTTP requests outright (confirmed by
hand: a bare GET returns a "Just a moment..." challenge page, not
content). Automating past that would mean evading bot detection, which
this project won't do.

Instead: the user views the site in their own browser, copies the
relevant numbers into a CSV under manual_data/, and the corresponding
source module reads that file in on the next pipeline run. This keeps
those two data points flowing into Mongo without scraping a site that
is actively trying to block automated access.
"""
from __future__ import annotations

import csv
from pathlib import Path

from sources.base import Source, SourceUnavailable
from utils.logging_config import get_logger

log = get_logger(__name__)

MANUAL_DATA_DIR = Path(__file__).resolve().parent.parent / "manual_data"


def read_csv_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ManualCsvSource(Source):
    """Base class for sources backed by a hand-maintained CSV instead of a live scrape.

    Subclasses set `csv_filename` (relative to manual_data/) and implement
    `_row_to_doc` to turn one CSV row into a schema-shaped document.
    """
    csv_filename: str

    def _row_to_doc(self, row: dict) -> dict:
        raise NotImplementedError

    def fetch(self, product: dict) -> list[dict]:
        csv_path = MANUAL_DATA_DIR / self.csv_filename
        rows = read_csv_rows(csv_path)
        if not rows:
            raise SourceUnavailable(
                f"manual_data/{self.csv_filename} is empty or missing — "
                f"see README.md for the expected columns"
            )

        product_rows = [r for r in rows if r.get("product_id") == product.get("id")]
        if not product_rows:
            raise SourceUnavailable(
                f"no rows for product_id={product.get('id')!r} in manual_data/{self.csv_filename} yet"
            )

        docs = []
        for row in product_rows:
            try:
                docs.append(self._row_to_doc(row))
            except (KeyError, ValueError) as e:
                log.warning("Skipping malformed row in %s: %s (%s)", self.csv_filename, row, e)
        return docs
