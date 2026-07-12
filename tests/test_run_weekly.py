"""Tests for run_weekly's orchestration logic: stats counting, skip/fail
handling, and dry-run vs write dispatch. Sources and Mongo are faked/mocked
so this doesn't depend on live network access or a real database."""
import json
from datetime import date
from unittest.mock import MagicMock, patch

import mongomock
import pytest

import run_weekly
from sources.base import Source, SourceUnavailable


class FakePriceSource(Source):
    name = "fake_price"
    target_collection = "price_snapshots"

    def __init__(self, http_client=None):
        super().__init__(http_client)
        self.configured = True

    def is_configured(self):
        return self.configured

    def fetch(self, product):
        if product["id"] == "unavailable-etb":
            raise SourceUnavailable("no url configured")
        if product["id"] == "broken-etb":
            raise RuntimeError("boom")
        return [{
            "product_id": product["id"],
            "date": date(2026, 7, 12),
            "price_type": "etb_sealed",
            "source": self.name,
            "price": 42.0,
            "currency": "USD",
            "raw_payload": {},
        }]


class FakeUnconfiguredSource(Source):
    name = "fake_unconfigured"
    target_collection = "price_snapshots"

    def is_configured(self):
        return False

    def fetch(self, product):
        raise AssertionError("should never be called when not configured")


@pytest.fixture
def products():
    return [
        {"id": "prismatic-evolutions-etb", "set_name": "Prismatic Evolutions"},
        {"id": "unavailable-etb", "set_name": "Unavailable"},
        {"id": "broken-etb", "set_name": "Broken"},
    ]


@pytest.fixture
def config_file(tmp_path, products):
    import yaml
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump({"products": products}))
    return str(path)


def test_run_dry_run_does_not_touch_mongo(config_file, capsys, monkeypatch):
    monkeypatch.setattr(run_weekly, "build_sources", lambda http_client: [FakePriceSource()])
    with patch("run_weekly.get_client") as mock_get_client:
        stats = run_weekly.run(config_file, dry_run=True)
        mock_get_client.assert_not_called()

    assert stats == {"fetched": 1, "skipped": 1, "failed": 1}
    out = capsys.readouterr().out
    printed = json.loads(out.strip())
    assert printed["product_id"] == "prismatic-evolutions-etb"


def test_run_writes_to_mongo_when_not_dry_run(config_file, monkeypatch):
    monkeypatch.setattr(run_weekly, "build_sources", lambda http_client: [FakePriceSource()])
    fake_client = mongomock.MongoClient()
    monkeypatch.setattr(run_weekly, "get_client", lambda: fake_client)

    stats = run_weekly.run(config_file, dry_run=False)

    assert stats == {"fetched": 1, "skipped": 1, "failed": 1}
    db = fake_client["pokemon_etb"]
    assert db.price_snapshots.count_documents({}) == 1
    doc = db.price_snapshots.find_one({})
    assert doc["product_id"] == "prismatic-evolutions-etb"
    assert doc["price"] == 42.0


def test_run_skips_unconfigured_source_for_all_products(config_file, monkeypatch):
    monkeypatch.setattr(run_weekly, "build_sources", lambda http_client: [FakeUnconfiguredSource()])

    stats = run_weekly.run(config_file, dry_run=True)

    assert stats == {"fetched": 0, "skipped": 3, "failed": 0}


def test_run_with_no_products_is_a_noop(tmp_path):
    import yaml
    path = tmp_path / "empty.yaml"
    path.write_text(yaml.dump({"products": []}))

    stats = run_weekly.run(str(path), dry_run=True)

    assert stats == {"fetched": 0, "skipped": 0, "failed": 0}


def test_run_is_idempotent_when_writing_twice(config_file, monkeypatch):
    monkeypatch.setattr(run_weekly, "build_sources", lambda http_client: [FakePriceSource()])
    fake_client = mongomock.MongoClient()
    monkeypatch.setattr(run_weekly, "get_client", lambda: fake_client)

    run_weekly.run(config_file, dry_run=False)
    run_weekly.run(config_file, dry_run=False)

    db = fake_client["pokemon_etb"]
    assert db.price_snapshots.count_documents({}) == 1
