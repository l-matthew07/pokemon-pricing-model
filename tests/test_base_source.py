"""Tests for the shared Source interface (sources/base.py)."""
import pytest

from sources.base import Source, SourceUnavailable


def test_source_cannot_be_instantiated_without_fetch():
    with pytest.raises(TypeError):
        Source()  # abstract: fetch() not implemented


def test_concrete_source_defaults_to_configured():
    class DummySource(Source):
        name = "dummy"
        target_collection = "price_snapshots"

        def fetch(self, product):
            return [{"product_id": product["id"], "price": 1.0}]

    src = DummySource()
    assert src.is_configured() is True
    assert src.fetch({"id": "some-etb"}) == [{"product_id": "some-etb", "price": 1.0}]


def test_source_can_signal_unavailable_for_a_product():
    class NoUrlSource(Source):
        name = "no_url"
        target_collection = "price_snapshots"

        def fetch(self, product):
            if "no_url" not in product.get("source_urls", {}):
                raise SourceUnavailable("no_url URL not configured for this product")
            return []

    src = NoUrlSource()
    with pytest.raises(SourceUnavailable):
        src.fetch({"id": "some-etb", "source_urls": {}})
