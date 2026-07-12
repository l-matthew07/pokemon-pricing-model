"""Tests for db.mongo: idempotent upserts and index creation, using mongomock."""
from datetime import date, datetime

import mongomock
import pytest

from db.mongo import (
    ensure_indexes,
    upsert_price_snapshot,
    upsert_product,
    upsert_scarcity_signal,
)


@pytest.fixture
def db():
    client = mongomock.MongoClient()
    database = client["test_db"]
    ensure_indexes(database)
    return database


def test_upsert_product_inserts_then_updates(db):
    upsert_product(db, {"_id": "prismatic-evolutions-etb", "set_name": "Prismatic Evolutions", "msrp": 79.99})
    assert db.products.count_documents({}) == 1

    upsert_product(db, {"_id": "prismatic-evolutions-etb", "set_name": "Prismatic Evolutions", "msrp": 84.99})
    assert db.products.count_documents({}) == 1
    doc = db.products.find_one({"_id": "prismatic-evolutions-etb"})
    assert doc["msrp"] == 84.99


def test_upsert_price_snapshot_idempotent_on_natural_key(db):
    snapshot = {
        "product_id": "prismatic-evolutions-etb",
        "date": date(2026, 7, 12),
        "price_type": "etb_sealed",
        "source": "pricecharting",
        "price": 89.99,
        "currency": "USD",
        "raw_payload": {"html_snippet": "..."},
    }
    upsert_price_snapshot(db, snapshot)
    upsert_price_snapshot(db, {**snapshot, "price": 91.50})

    assert db.price_snapshots.count_documents({}) == 1
    doc = db.price_snapshots.find_one({})
    assert doc["price"] == 91.50
    assert doc["date"] == datetime(2026, 7, 12)


def test_upsert_price_snapshot_distinguishes_by_source_and_type(db):
    base = {
        "product_id": "prismatic-evolutions-etb",
        "date": date(2026, 7, 12),
        "currency": "USD",
        "raw_payload": {},
    }
    upsert_price_snapshot(db, {**base, "price_type": "etb_sealed", "source": "pricecharting", "price": 89.99})
    upsert_price_snapshot(db, {**base, "price_type": "etb_sealed", "source": "tcgplayer", "price": 92.00})
    upsert_price_snapshot(db, {**base, "price_type": "promo_psa10", "source": "pricecharting", "price": 250.00})

    assert db.price_snapshots.count_documents({}) == 3


def test_upsert_scarcity_signal_idempotent_on_natural_key(db):
    signal = {
        "product_id": "prismatic-evolutions-etb",
        "date": date(2026, 7, 12),
        "signal_type": "google_trends_index",
        "value": 73,
        "source": "google_trends",
    }
    upsert_scarcity_signal(db, signal)
    upsert_scarcity_signal(db, {**signal, "value": 80})

    assert db.scarcity_signals.count_documents({}) == 1
    assert db.scarcity_signals.find_one({})["value"] == 80


def test_unique_index_prevents_duplicate_natural_keys(db):
    key_fields = {
        "product_id": "prismatic-evolutions-etb",
        "date": datetime(2026, 7, 12),
        "price_type": "etb_sealed",
        "source": "pricecharting",
    }
    db.price_snapshots.insert_one({**key_fields, "price": 89.99, "currency": "USD", "raw_payload": {}})

    with pytest.raises(Exception):
        db.price_snapshots.insert_one({**key_fields, "price": 99.99, "currency": "USD", "raw_payload": {}})
