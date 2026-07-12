"""Tests for the manual-CSV-import fallback (sources.manual_import,
sources.onepthirty, sources.psa_pop). No network access."""
import csv

import pytest

from sources.base import SourceUnavailable
from sources.onepthirty import OnePThirtySource
from sources.psa_pop import PsaPopSource


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_manual_source_raises_when_csv_missing(tmp_path, monkeypatch):
    import sources.manual_import as mi
    monkeypatch.setattr(mi, "MANUAL_DATA_DIR", tmp_path)

    source = OnePThirtySource()
    with pytest.raises(SourceUnavailable, match="empty or missing"):
        source.fetch({"id": "some-etb"})


def test_manual_source_raises_when_no_rows_for_product(tmp_path, monkeypatch):
    import sources.manual_import as mi
    monkeypatch.setattr(mi, "MANUAL_DATA_DIR", tmp_path)
    _write_csv(
        tmp_path / "onepthirty.csv",
        ["product_id", "date", "price_type", "price", "currency"],
        [{"product_id": "other-etb", "date": "2026-07-01", "price_type": "promo_psa10", "price": "250", "currency": "USD"}],
    )

    source = OnePThirtySource()
    with pytest.raises(SourceUnavailable, match="no rows for product_id"):
        source.fetch({"id": "some-etb"})


def test_onepthirty_returns_docs_for_matching_product(tmp_path, monkeypatch):
    import sources.manual_import as mi
    monkeypatch.setattr(mi, "MANUAL_DATA_DIR", tmp_path)
    _write_csv(
        tmp_path / "onepthirty.csv",
        ["product_id", "date", "price_type", "price", "currency"],
        [
            {"product_id": "prismatic-evolutions-etb", "date": "2026-07-01", "price_type": "promo_psa10", "price": "250.00", "currency": "USD"},
            {"product_id": "other-etb", "date": "2026-07-01", "price_type": "promo_psa10", "price": "99.00", "currency": "USD"},
        ],
    )

    source = OnePThirtySource()
    results = source.fetch({"id": "prismatic-evolutions-etb"})

    assert len(results) == 1
    doc = results[0]
    assert doc["product_id"] == "prismatic-evolutions-etb"
    assert doc["price_type"] == "promo_psa10"
    assert doc["price"] == 250.00
    assert doc["source"] == "onepthirty"


def test_onepthirty_skips_malformed_row(tmp_path, monkeypatch):
    import sources.manual_import as mi
    monkeypatch.setattr(mi, "MANUAL_DATA_DIR", tmp_path)
    _write_csv(
        tmp_path / "onepthirty.csv",
        ["product_id", "date", "price_type", "price", "currency"],
        [
            {"product_id": "prismatic-evolutions-etb", "date": "2026-07-01", "price_type": "promo_psa10", "price": "not-a-number", "currency": "USD"},
        ],
    )

    source = OnePThirtySource()
    results = source.fetch({"id": "prismatic-evolutions-etb"})
    assert results == []


def test_psa_pop_returns_scarcity_signal(tmp_path, monkeypatch):
    import sources.manual_import as mi
    monkeypatch.setattr(mi, "MANUAL_DATA_DIR", tmp_path)
    _write_csv(
        tmp_path / "psa_pop.csv",
        ["product_id", "date", "value"],
        [{"product_id": "prismatic-evolutions-etb", "date": "2026-07-01", "value": "412"}],
    )

    source = PsaPopSource()
    results = source.fetch({"id": "prismatic-evolutions-etb"})

    assert len(results) == 1
    doc = results[0]
    assert doc["signal_type"] == "psa_pop_count"
    assert doc["value"] == 412.0
    assert doc["source"] == "psa_pop"
