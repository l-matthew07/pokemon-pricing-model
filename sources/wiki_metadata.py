"""Bulbapedia set metadata scraper.

Bulbapedia is a normal, unprotected MediaWiki site; its robots.txt asks
for a 5s crawl-delay between requests, which utils.http.DOMAIN_DELAYS
already respects. Every TCG set page publishes a structured infobox
with "Cards in set" and "Release date" rows, reliably extractable —
though the cell text takes two different shapes depending on whether
Bulbapedia documents a Japanese release separately:
  - single-language sets:  "180"
  - bilingual sets:        "English: 252 Japanese: -"
                           "English: June 9, 2023 Japanese: April 14, 2023"

Softer, more judgment-based fields (specialty-set flag, box art
Pokemon, chase-card list, new-mechanic flag) aren't reliably scrapable
from free-form prose, so those stay hand-entered in config.yaml —
config values always take precedence over anything scraped here, since
a small, hand-curated product list is more trustworthy than a brittle
prose-parsing heuristic.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from sources.base import Source, SourceUnavailable
from utils.logging_config import get_logger

log = get_logger(__name__)

DATE_FORMAT = "%B %d, %Y"


def _extract_lang_value(raw: str, lang: str) -> str | None:
    """Pull out the value for one language from a possibly-bilingual infobox cell."""
    if f"{lang}:" not in raw:
        # No language prefix at all: treat the whole cell as the (English) value.
        return raw.strip() or None if lang == "English" else None

    match = re.search(rf"{lang}:\s*(.*?)(?=\s+(?:English|Japanese):|$)", raw)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_date(value: str | None) -> "datetime.date | None":
    if not value or value == "N/A":
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        log.warning("Could not parse date %r", value)
        return None


def parse_set_infobox(html: str) -> dict:
    """Return whatever of {'release_date', 'jp_release_date', 'set_size'} can be found."""
    soup = BeautifulSoup(html, "lxml")
    info: dict[str, str] = {}
    for table in soup.find_all("table", class_="roundy"):
        for tr in table.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                label = th.get_text(" ", strip=True).replace("\xa0", " ")
                value = td.get_text(" ", strip=True).replace("\xa0", " ")
                info[label] = value
        if "Release date" in info or "Cards in set" in info:
            break

    result: dict = {}

    cards_value = _extract_lang_value(info.get("Cards in set", ""), "English")
    if cards_value:
        try:
            result["set_size"] = int(cards_value)
        except ValueError:
            log.warning("Could not parse set size %r", cards_value)

    release_date = _parse_date(_extract_lang_value(info.get("Release date", ""), "English"))
    if release_date:
        result["release_date"] = release_date

    jp_release_date = _parse_date(_extract_lang_value(info.get("Release date", ""), "Japanese"))
    if jp_release_date:
        result["jp_release_date"] = jp_release_date

    return result


class WikiMetadataSource(Source):
    name = "wiki_metadata"
    target_collection = "products"

    def fetch(self, product: dict) -> list[dict]:
        url = product.get("source_urls", {}).get("bulbapedia")
        if not url:
            raise SourceUnavailable(f"no bulbapedia URL configured for {product.get('id')}")

        html = self.http.get_text(url)
        scraped = parse_set_infobox(html)
        if not scraped:
            raise SourceUnavailable(f"could not find a set infobox on {url}")

        # config-provided fields always win; scraped values only fill in gaps.
        doc = {"_id": product["id"]}
        for field, scraped_value in scraped.items():
            doc[field] = product[field] if product.get(field) is not None else scraped_value

        return [doc]
