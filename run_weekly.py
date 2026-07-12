#!/usr/bin/env python3
"""Weekly pipeline entrypoint: run every configured source against every
configured product in config.yaml and upsert the results into MongoDB.

Usage:
    python run_weekly.py                    # fetch + write to Mongo
    python run_weekly.py --dry-run          # fetch + print, don't touch Mongo
    python run_weekly.py --config other.yaml --log-level DEBUG
"""
from __future__ import annotations

import json
from datetime import date, datetime

import click
import yaml
from dotenv import load_dotenv

from db.mongo import (
    ensure_indexes,
    get_client,
    get_db,
    upsert_price_snapshot,
    upsert_product,
    upsert_scarcity_signal,
)
from sources.base import SourceUnavailable
from sources.google_trends import GoogleTrendsSource
from sources.onepthirty import OnePThirtySource
from sources.pricecharting import PriceChartingSource
from sources.psa_pop import PsaPopSource
from sources.tcgplayer import TcgplayerSource
from sources.wiki_metadata import WikiMetadataSource
from utils.http import HttpClient
from utils.logging_config import get_logger, setup_logging

log = get_logger("run_weekly")

UPSERTERS = {
    "products": upsert_product,
    "price_snapshots": upsert_price_snapshot,
    "scarcity_signals": upsert_scarcity_signal,
}


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def build_sources(http_client: HttpClient) -> list:
    return [
        WikiMetadataSource(http_client),
        PriceChartingSource(http_client),
        TcgplayerSource(http_client),
        OnePThirtySource(http_client),
        PsaPopSource(http_client),
        GoogleTrendsSource(),  # manages its own client; not routed through HttpClient
    ]


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def run(config_path: str, dry_run: bool) -> dict:
    config = load_config(config_path)
    products = config.get("products", [])
    if not products:
        log.warning("No products configured in %s; nothing to do", config_path)
        return {"fetched": 0, "skipped": 0, "failed": 0}

    http_client = HttpClient()
    sources = build_sources(http_client)

    db = None
    if not dry_run:
        db = get_db(get_client())
        ensure_indexes(db)

    stats = {"fetched": 0, "skipped": 0, "failed": 0}

    for source in sources:
        if not source.is_configured():
            log.warning("Skipping source '%s' entirely: not configured (see README.md)", source.name)
            stats["skipped"] += len(products)
            continue

        for product in products:
            product_id = product.get("id", "<unknown>")
            try:
                docs = source.fetch(product)
            except SourceUnavailable as e:
                log.info("Skipped %s/%s: %s", source.name, product_id, e)
                stats["skipped"] += 1
                continue
            except Exception:
                log.exception("Failed %s/%s", source.name, product_id)
                stats["failed"] += 1
                continue

            if not docs:
                log.info("No data returned for %s/%s", source.name, product_id)
                continue

            if dry_run:
                for doc in docs:
                    print(json.dumps(doc, indent=2, default=_json_default))
            else:
                upsert = UPSERTERS[source.target_collection]
                for doc in docs:
                    upsert(db, doc)

            stats["fetched"] += len(docs)
            log.info("Fetched %d doc(s) from %s for %s", len(docs), source.name, product_id)

    log.info("Run complete: %s", stats)
    return stats


@click.command()
@click.option("--config", "config_path", default="config.yaml", show_default=True, help="Path to config.yaml")
@click.option("--dry-run", is_flag=True, help="Fetch and print results; don't write to MongoDB")
@click.option("--log-level", default="INFO", show_default=True)
def main(config_path: str, dry_run: bool, log_level: str) -> None:
    load_dotenv()
    setup_logging(log_level)
    run(config_path, dry_run)


if __name__ == "__main__":
    main()
