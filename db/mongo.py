"""MongoDB connection and idempotent upsert helpers.

Collections and their natural (idempotency) keys:
  - products:          _id (a user-assigned slug, e.g. "prismatic-evolutions-etb")
  - price_snapshots:   (product_id, date, price_type, source)
  - scarcity_signals:  (product_id, date, signal_type, source)

Re-running the pipeline for a date/product that's already been recorded
updates the existing document in place rather than inserting a duplicate.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from utils.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "pokemon_etb"


def get_client(uri: str | None = None) -> MongoClient:
    uri = uri or os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)
    return MongoClient(uri)


def get_db(client: MongoClient | None = None, db_name: str | None = None) -> Database:
    client = client or get_client()
    db_name = db_name or os.environ.get("MONGO_DB_NAME", DEFAULT_DB_NAME)
    return client[db_name]


def ensure_indexes(db: Database) -> None:
    """Create the compound/unique indexes the schema relies on. Safe to call every run."""
    db.price_snapshots.create_index(
        [("product_id", ASCENDING), ("date", ASCENDING)], name="product_date"
    )
    db.price_snapshots.create_index(
        [("product_id", ASCENDING), ("date", ASCENDING), ("price_type", ASCENDING), ("source", ASCENDING)],
        name="natural_key",
        unique=True,
    )

    db.scarcity_signals.create_index(
        [("product_id", ASCENDING), ("date", ASCENDING)], name="product_date"
    )
    db.scarcity_signals.create_index(
        [("product_id", ASCENDING), ("date", ASCENDING), ("signal_type", ASCENDING), ("source", ASCENDING)],
        name="natural_key",
        unique=True,
    )
    log.info("Indexes ensured on price_snapshots and scarcity_signals")


def _normalize_date(value: date | datetime) -> datetime:
    """Mongo has no native `date` type; store all dates as UTC midnight datetimes."""
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return datetime(value.year, value.month, value.day)


def upsert_product(db: Database, product: dict) -> None:
    """Upsert a products document, keyed on _id."""
    doc = dict(product)
    product_id = doc.pop("_id")
    db.products.update_one({"_id": product_id}, {"$set": doc}, upsert=True)
    log.debug("Upserted product %s", product_id)


def upsert_price_snapshot(db: Database, snapshot: dict) -> None:
    """Upsert a price_snapshots document, keyed on (product_id, date, price_type, source)."""
    doc = dict(snapshot)
    doc["date"] = _normalize_date(doc["date"])
    key = {
        "product_id": doc["product_id"],
        "date": doc["date"],
        "price_type": doc["price_type"],
        "source": doc["source"],
    }
    db.price_snapshots.update_one(key, {"$set": doc}, upsert=True)
    log.debug("Upserted price_snapshot %s", key)


def upsert_scarcity_signal(db: Database, signal: dict) -> None:
    """Upsert a scarcity_signals document, keyed on (product_id, date, signal_type, source)."""
    doc = dict(signal)
    doc["date"] = _normalize_date(doc["date"])
    key = {
        "product_id": doc["product_id"],
        "date": doc["date"],
        "signal_type": doc["signal_type"],
        "source": doc["source"],
    }
    db.scarcity_signals.update_one(key, {"$set": doc}, upsert=True)
    log.debug("Upserted scarcity_signal %s", key)
