"""Shared HTTP client for all scraper sources.

Provides three things every source needs so we're respectful of the sites
we scrape and resilient to flaky networks:
  - per-domain rate limiting (a minimum delay between requests to the same host)
  - retry with exponential backoff on transient failures
  - on-disk HTML/response caching so re-running the pipeline (or a --dry-run)
    doesn't hammer a site for content we already fetched recently
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.logging_config import get_logger

log = get_logger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
DEFAULT_USER_AGENT = "pokemon-etb-pricing-research-bot/1.0 (contact: limatthew68@gmail.com)"

# Minimum seconds between requests to a given domain. Bulbapedia's robots.txt
# explicitly asks for a 5s crawl-delay; everything else defaults to 2s.
DOMAIN_DELAYS = {
    "bulbapedia.bulbagarden.net": 5.0,
    "www.serebii.net": 3.0,
    "serebii.net": 3.0,
    "www.pricecharting.com": 2.0,
    "pricecharting.com": 2.0,
}
DEFAULT_DELAY = 2.0


class RateLimiter:
    """Tracks last-request time per domain and sleeps as needed before the next one."""

    def __init__(self) -> None:
        self._last_request: dict[str, float] = {}

    def wait(self, domain: str) -> None:
        delay = DOMAIN_DELAYS.get(domain, DEFAULT_DELAY)
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            remaining = delay - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[domain] = time.monotonic()


class HttpClient:
    """A requests.Session wrapper with rate limiting, retries, and disk caching.

    One instance is meant to be shared across a whole pipeline run (see
    run_weekly.py), so the rate limiter's per-domain state actually has
    effect across multiple source modules hitting the same host.
    """

    def __init__(self, cache_ttl_seconds: int = 6 * 3600, user_agent: str = DEFAULT_USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.rate_limiter = RateLimiter()
        self.cache_ttl_seconds = cache_ttl_seconds
        CACHE_DIR.mkdir(exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        domain = urlparse(url).netloc
        digest = hashlib.sha256(url.encode()).hexdigest()
        domain_dir = CACHE_DIR / domain
        domain_dir.mkdir(exist_ok=True)
        return domain_dir / f"{digest}.html"

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl_seconds:
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, url: str, text: str) -> None:
        self._cache_path(url).write_text(text, encoding="utf-8")

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, requests.HTTPError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, url: str, **kwargs) -> requests.Response:
        domain = urlparse(url).netloc
        self.rate_limiter.wait(domain)
        response = self.session.get(url, timeout=15, **kwargs)
        if response.status_code >= 500 or response.status_code == 429:
            log.warning("Retryable status %s from %s", response.status_code, url)
            response.raise_for_status()
        return response

    def get_text(self, url: str, use_cache: bool = True, **kwargs) -> str:
        """GET a URL and return response text, transparently using the disk cache."""
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                log.debug("Cache hit for %s", url)
                return cached

        response = self._get(url, **kwargs)
        response.raise_for_status()
        if use_cache:
            self._write_cache(url, response.text)
        return response.text

    def get_json(self, url: str, **kwargs) -> dict:
        domain = urlparse(url).netloc
        self.rate_limiter.wait(domain)
        response = self._get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def post_json(self, url: str, **kwargs) -> dict:
        domain = urlparse(url).netloc
        self.rate_limiter.wait(domain)
        response = self.session.post(url, timeout=15, **kwargs)
        response.raise_for_status()
        return response.json()
