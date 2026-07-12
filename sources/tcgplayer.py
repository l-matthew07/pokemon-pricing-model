"""TCGplayer Marketplace API source.

Uses the official API only (never scrapes tcgplayer.com). Requires an
app key: set TCGPLAYER_CLIENT_ID and TCGPLAYER_CLIENT_SECRET in the
environment. Until both are set, is_configured() returns False and the
orchestrator skips this source cleanly without blocking the rest of the
pipeline — see README.md for how to request a key and apply for one.

API reference (public docs, no key needed to read):
  https://docs.tcgplayer.com/docs/getting-started
  - POST https://api.tcgplayer.com/token           (client_credentials grant -> bearer token)
  - GET  https://api.tcgplayer.com/pricing/product/{productIds}  (marketplace pricing per product)
"""
from __future__ import annotations

import os
import time
from datetime import date

from sources.base import Source, SourceUnavailable
from utils.logging_config import get_logger

log = get_logger(__name__)

TOKEN_URL = "https://api.tcgplayer.com/token"
PRICING_URL = "https://api.tcgplayer.com/pricing/product/{product_ids}"


class TcgplayerSource(Source):
    name = "tcgplayer"
    target_collection = "price_snapshots"

    def __init__(self, http_client=None):
        super().__init__(http_client)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(os.environ.get("TCGPLAYER_CLIENT_ID") and os.environ.get("TCGPLAYER_CLIENT_SECRET"))

    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        client_id = os.environ["TCGPLAYER_CLIENT_ID"]
        client_secret = os.environ["TCGPLAYER_CLIENT_SECRET"]
        response = self.http.post_json(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        self._token = response["access_token"]
        # TCGplayer app tokens are typically valid ~14 days; refresh a bit early to be safe.
        self._token_expires_at = time.monotonic() + int(response.get("expires_in", 3600)) - 60
        return self._token

    def fetch(self, product: dict) -> list[dict]:
        if not self.is_configured():
            raise SourceUnavailable(
                "TCGPLAYER_CLIENT_ID / TCGPLAYER_CLIENT_SECRET not set; get an app key at "
                "https://docs.tcgplayer.com/docs/getting-started"
            )

        targets = product.get("source_urls", {}).get("tcgplayer")
        if not targets:
            raise SourceUnavailable(f"no tcgplayer product IDs configured for {product.get('id')}")

        token = self._ensure_token()
        today = date.today()
        results = []

        for price_type, spec in targets.items():
            product_id = spec.get("product_id")
            if not product_id:
                log.warning("Missing product_id for %s/%s, skipping", product.get("id"), price_type)
                continue

            url = PRICING_URL.format(product_ids=product_id)
            payload = self.http.get_json(url, headers={"Authorization": f"Bearer {token}"})
            rows = payload.get("results", [])
            if not rows:
                log.info("No pricing rows returned for %s/%s (product_id=%s)", product.get("id"), price_type, product_id)
                continue

            # A product can have multiple subTypeName rows (e.g. Normal/Foil); take the first
            # (Normal) result, which is what we want for sealed product / packs.
            row = rows[0]
            market_price = row.get("marketPrice")
            if market_price is None:
                log.info("No marketPrice for %s/%s (product_id=%s)", product.get("id"), price_type, product_id)
                continue

            results.append({
                "product_id": product["id"],
                "date": today,
                "price_type": price_type,
                "source": self.name,
                "price": market_price,
                "currency": "USD",
                "raw_payload": row,
            })

        return results
