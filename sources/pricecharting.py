"""PriceCharting scraper.

PriceCharting has no free public API, so this scrapes product pages
(allowed by robots.txt: only /stripe-connect, /publish-offer, /buy are
disallowed). Every Pokemon product page — sealed ETB, single card,
booster pack — renders the same six price columns in a `#price_data`
table: td ids used_price/complete_price/new_price/graded_price/
box_only_price/manual_only_price, labeled by the `<th>` above them
(e.g. "Ungraded", "Grade 9", "PSA 10"). Which label maps to which of
our schema's price_type values isn't fixed by the site — it depends on
the product (a sealed ETB's real price shows up under "Ungraded" since
there's nothing to grade) — so config.yaml specifies, per product and
price_type, which URL to fetch and which column label to read.
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from sources.base import Source, SourceUnavailable
from utils.logging_config import get_logger

log = get_logger(__name__)

PRICE_TD_IDS = [
    "used_price",
    "complete_price",
    "new_price",
    "graded_price",
    "box_only_price",
    "manual_only_price",
]


def parse_price_table(html: str) -> dict[str, float | None]:
    """Return {header_label: price_or_None} for a PriceCharting product page.

    Raises SourceUnavailable if the page doesn't have the expected
    #price_data table (e.g. it 404'd or the site changed layout).
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="price_data")
    if table is None:
        raise SourceUnavailable("no #price_data table found on page (missing product or layout changed)")

    header_row = table.find("thead").find("tr")
    labels = [th.get_text(strip=True) for th in header_row.find_all("th")]

    body_row = table.find("tbody").find("tr")
    cells = [td for td in body_row.find_all("td") if td.get("id") in PRICE_TD_IDS]

    prices: dict[str, float | None] = {}
    for label, cell in zip(labels, cells):
        text = cell.get_text(strip=True)
        match = re.search(r"[\d,]+\.\d{2}", text)
        prices[label] = float(match.group().replace(",", "")) if match else None
    return prices


class PriceChartingSource(Source):
    name = "pricecharting"
    target_collection = "price_snapshots"

    def fetch(self, product: dict) -> list[dict]:
        targets = product.get("source_urls", {}).get("pricecharting")
        if not targets:
            raise SourceUnavailable(f"no pricecharting URLs configured for {product.get('id')}")

        today = date.today()
        results = []
        for price_type, spec in targets.items():
            url = spec.get("url")
            label = spec.get("label")
            if not url or not label:
                log.warning(
                    "Incomplete pricecharting config for %s/%s (need url and label), skipping",
                    product.get("id"), price_type,
                )
                continue

            try:
                html = self.http.get_text(url)
                prices = parse_price_table(html)
            except SourceUnavailable as e:
                log.warning("Skipping %s/%s: %s", product.get("id"), price_type, e)
                continue

            if label not in prices:
                log.warning(
                    "Label %r not found for %s/%s (page has: %s)",
                    label, product.get("id"), price_type, list(prices.keys()),
                )
                continue

            price = prices[label]
            if price is None:
                log.info("No price currently listed for %s/%s (label=%s)", product.get("id"), price_type, label)
                continue

            results.append({
                "product_id": product["id"],
                "date": today,
                "price_type": price_type,
                "source": self.name,
                "price": price,
                "currency": "USD",
                "raw_payload": {"url": url, "label": label, "all_labels_found": prices},
            })
        return results
