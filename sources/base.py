"""Shared interface every data source implements, so run_weekly.py can loop
over all of them uniformly regardless of what they scrape or call.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from utils.http import HttpClient


class SourceUnavailable(Exception):
    """Raised for an expected, clean skip: no API key configured, no URL set
    for this particular product, site unreachable in a known/documented way.

    The orchestrator logs these as "skipped: <reason>" rather than treating
    them as failures. Anything else raised by fetch() propagates and is
    logged as a real error with a traceback.
    """


class Source(ABC):
    #: short machine-friendly name, used as the `source` field in stored docs
    name: str
    #: which collection this source's documents belong in
    target_collection: str

    def __init__(self, http_client: HttpClient | None = None):
        self.http = http_client or HttpClient()

    def is_configured(self) -> bool:
        """Whether this source has what it needs to run at all (e.g. an API key).

        Checked once per pipeline run before iterating products. A source
        that's globally unconfigured should return False here rather than
        raising SourceUnavailable from every fetch() call.
        """
        return True

    @abstractmethod
    def fetch(self, product: dict) -> list[dict]:
        """Fetch records for `product`, ready to upsert into target_collection.

        Raise SourceUnavailable for an expected per-product skip (e.g. this
        product has no URL configured for this source). Let unexpected
        errors propagate so the orchestrator can log and count them as
        failures rather than silent skips.
        """
        raise NotImplementedError
