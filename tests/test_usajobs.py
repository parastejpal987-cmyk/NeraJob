"""Tests for USAJOBS Search API scraper adapter.

Run with: pytest tests/test_usajobs.py
"""

from __future__ import annotations

import os

from nerajob.scrapers.registry import available_scrapers, get_scraper


def test_usajobs_registered() -> None:
    """Scraper should be registered under name 'usajobs'."""
    scrapers = available_scrapers()
    assert "usajobs" in scrapers
    scraper = get_scraper("usajobs")
    assert scraper.name == "usajobs"


def test_usajobs_offline(monkeypatch) -> None:
    """Offline mode returns sample job postings."""
    monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
    jobs = get_scraper("usajobs").search(query="computer", limit=5)
    assert len(jobs) > 0, "Should return at least one sample job"
    assert all(j.source == "usajobs" for j in jobs), "All jobs should have source='usajobs'"


def test_usajobs_offline_no_query(monkeypatch) -> None:
    """Offline mode returns all samples when no query given."""
    monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
    jobs = get_scraper("usajobs").search(query="", limit=20)
    assert len(jobs) >= 3, "Should return all offline samples"


def test_usajobs_offline_query_filter(monkeypatch) -> None:
    """Offline mode should filter by query."""
    monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
    jobs = get_scraper("usajobs").search(query="infosec", limit=20)
    assert len(jobs) >= 1, "Should find InfoSec-related job"
    titles = [j.title.lower() for j in jobs]
    assert any("infosec" in t for t in titles)


def test_usajobs_offline_location_filter(monkeypatch) -> None:
    """Offline mode filters by location context."""
    monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
    jobs = get_scraper("usajobs").search(query="", location="Washington", limit=20)
    assert len(jobs) >= 1, "Should find Washington-located job"
    locations = [j.location.lower() for j in jobs]
    assert any("washington" in loc for loc in locations)


def test_usajobs_offline_limit(monkeypatch) -> None:
    """Offline mode respects the limit parameter."""
    monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
    jobs = get_scraper("usajobs").search(query="", limit=2)
    assert len(jobs) <= 2, "Should return at most 2 jobs"


def test_usajobs_fallback_when_no_creds() -> None:
    """When USAJOBS_API_KEY/EMAIL are not set, should fall back to offline."""
    if "USAJOBS_API_KEY" in os.environ:
        del os.environ["USAJOBS_API_KEY"]
    if "USAJOBS_EMAIL" in os.environ:
        del os.environ["USAJOBS_EMAIL"]
    jobs = get_scraper("usajobs").search(query="computer", limit=3)
    assert len(jobs) > 0, "Should fall back to offline mode"
