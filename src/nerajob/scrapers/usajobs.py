"""USAJOBS Search API adapter with offline fallback."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from nerajob.config import http_timeout
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

_OFFLINE: list[dict[str, Any]] = [
    {
        "PositionID": "usajobs-demo-1",
        "PositionTitle": "IT Specialist (INFOSEC/NETWORK)",
        "OrganizationName": "Department of the Army",
        "PositionLocation": [
            {
                "LocationName": "Washington, District of Columbia",
            }
        ],
        "PositionURI": "https://www.usajobs.gov/GetJob/ViewDetails/usajobs-demo-1",
        "UserArea": {
            "Details": {
                "JobSummary": "Serves as an IT Specialist (INFOSEC/NETWORK) for cybersecurity operations.",
                "RemoteIndicator": False,
            }
        },
        "PositionRemuneration": [
            {
                "MinimumRange": "95000",
                "MaximumRange": "120000",
                "RateIntervalCode": "Per Year",
            }
        ]
    },
    {
        "PositionID": "usajobs-demo-2",
        "PositionTitle": "Computer Scientist",
        "OrganizationName": "National Science Foundation",
        "PositionLocation": [
            {
                "LocationName": "Remote, US",
            }
        ],
        "PositionURI": "https://www.usajobs.gov/GetJob/ViewDetails/usajobs-demo-2",
        "UserArea": {
            "Details": {
                "JobSummary": "Responsible for conducting computer science research and program direction.",
                "RemoteIndicator": True,
            }
        },
        "PositionRemuneration": [
            {
                "MinimumRange": "115000",
                "MaximumRange": "150000",
                "RateIntervalCode": "Per Year",
            }
        ]
    },
    {
        "PositionID": "usajobs-demo-3",
        "PositionTitle": "Data Analyst",
        "OrganizationName": "Department of Transportation",
        "PositionLocation": [
            {
                "LocationName": "Chicago, Illinois",
            }
        ],
        "PositionURI": "https://www.usajobs.gov/GetJob/ViewDetails/usajobs-demo-3",
        "UserArea": {
            "Details": {
                "JobSummary": "Performs data analysis and statistics for transit systems.",
                "RemoteIndicator": False,
            }
        },
        "PositionRemuneration": [
            {
                "MinimumRange": "80000",
                "MaximumRange": "98000",
                "RateIntervalCode": "Per Year",
            }
        ]
    }
]


class USAJobsScraper(BaseScraper):
    """Scraper for USAJOBS.gov Search API with offline fallback."""

    name = "usajobs"
    BASE_URL = "https://data.usajobs.gov/api/search"

    def search(
        self,
        query: str = "",
        location: str = "",
        limit: int = 20,
    ) -> list[JobPosting]:
        """Search USAJOBS for jobs matching *query* and *location*.

        Parameters
        ----------
        query : str
            Free-text search (job title, skill, keyword).
        location : str
            Where string (e.g. ``"Washington, DC"``).
        limit : int
            Max results to return.

        Returns
        -------
        list[JobPosting]
            Matched job postings, or offline fixtures on fallback/failure.
        """
        if os.getenv("NERAJOB_USAJOBS_OFFLINE", "").strip().lower() in {"1", "true", "yes"}:
            return self._offline(query, location, limit)

        api_key = os.getenv("USAJOBS_API_KEY", "").strip()
        email = os.getenv("USAJOBS_EMAIL", "").strip()

        if not api_key or not email:
            return self._offline(query, location, limit)

        params: dict[str, str | int] = {
            "ResultsPerPage": max(1, min(limit, 500)),
        }
        if query.strip():
            params["Keyword"] = query.strip()
        if location.strip():
            params["LocationName"] = location.strip()

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": email,
            "Authorization-Key": api_key,
            "Accept": "application/json",
        }

        try:
            with httpx.Client(
                timeout=http_timeout(),
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return self._offline(query, location, limit)

        search_result = payload.get("SearchResult", {}) or {}
        items = search_result.get("SearchResultItems", []) or []

        jobs: list[JobPosting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = item.get("MatchedObjectDescriptor", {}) or {}
            if not desc:
                continue
            posting = self._normalize(desc)
            if posting is None:
                continue

            q = query.strip().lower()
            loc = location.strip().lower()
            hay = (
                f"{posting.title} {posting.company} {posting.location} "
                f"{' '.join(posting.tags)} {posting.description}"
            ).lower()

            if q and q not in hay:
                continue
            if loc and loc not in posting.location.lower() and "remote" not in posting.location.lower():
                continue

            jobs.append(posting)
            if len(jobs) >= limit:
                break

        return jobs if jobs else self._offline(query, location, limit)

    def _normalize(self, desc: dict) -> JobPosting | None:
        title = desc.get("PositionTitle", "") or ""
        company = desc.get("OrganizationName", "") or ""
        url = desc.get("PositionURI", "") or ""

        # Extract locations
        loc_objs = desc.get("PositionLocation", []) or []
        loc_names = [loc.get("LocationName", "") for loc in loc_objs if loc.get("LocationName")]
        location = ", ".join(loc_names) if loc_names else "Remote"

        # Extract description
        user_area = desc.get("UserArea", {}) or {}
        details = user_area.get("Details", {}) or {}
        description = details.get("JobSummary", "") or ""

        # Remote check
        is_remote = False
        if details.get("RemoteIndicator") is True:
            is_remote = True
        elif "remote" in location.lower():
            is_remote = True

        # Extract salary
        remuns = desc.get("PositionRemuneration", []) or []
        salary_str = ""
        if remuns:
            remun = remuns[0]
            min_sal = remun.get("MinimumRange", "")
            max_sal = remun.get("MaximumRange", "")
            interval = remun.get("RateIntervalCode", "")
            if min_sal and max_sal:
                salary_str = f"USD {min_sal}-{max_sal} {interval}"
            elif min_sal:
                salary_str = f"USD {min_sal} {interval}"

        # Generate unique ID
        raw_id = desc.get("PositionID") or title
        digest = hashlib.sha1(f"{self.name}:{raw_id}".encode()).hexdigest()[:12]

        return JobPosting(
            id=f"usajobs-{digest}",
            source=self.name,
            title=title,
            company=company or "Unknown Agency",
            location=location,
            url=url,
            description=description,
            tags=["Government", "Federal"],
            salary=salary_str,
            remote=is_remote,
            raw={"usajobs_id": raw_id},
        )

    def _offline(self, query: str = "", location: str = "", limit: int = 20) -> list[JobPosting]:
        results: list[JobPosting] = []
        q = query.strip().lower()
        loc = location.strip().lower()

        for item in _OFFLINE:
            posting = self._normalize(item)
            if posting is None:
                continue

            hay = (
                f"{posting.title} {posting.company} {posting.location} "
                f"{' '.join(posting.tags)} {posting.description}"
            ).lower()

            if q and q not in hay:
                continue
            if loc and loc not in posting.location.lower() and "remote" not in posting.location.lower():
                continue

            results.append(posting)
            if len(results) >= limit:
                break

        return results
