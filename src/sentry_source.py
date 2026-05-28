"""Sentry issue source.

Uses the Sentry REST API to fetch issues for one or more projects.
Docs: https://docs.sentry.io/api/events/list-a-projects-issues/
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Iterable, Optional

import requests

from .config import SentryConfig
from .models import BugItem

log = logging.getLogger(__name__)

# Sentry caps page sizes at 100 for issues endpoints.
_PAGE_SIZE = 100
_TIMEOUT = 30


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Sentry returns ISO 8601 with trailing 'Z'
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class SentrySource:
    def __init__(self, config: SentryConfig):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.auth_token}",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    def _projects(self) -> List[str]:
        if self.config.project_slugs:
            return self.config.project_slugs
        url = f"{self.config.host}/api/0/organizations/{self.config.org_slug}/projects/"
        slugs: List[str] = []
        while url:
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            for project in resp.json():
                slug = project.get("slug")
                if slug:
                    slugs.append(slug)
            url = self._next_link(resp)
        return slugs

    @staticmethod
    def _next_link(resp: requests.Response) -> Optional[str]:
        """Parse Sentry's RFC5988 Link header for cursor-based pagination."""
        link = resp.headers.get("Link")
        if not link:
            return None
        for part in link.split(","):
            segment = part.strip()
            if 'rel="next"' in segment and 'results="true"' in segment:
                # Format: <url>; rel="next"; results="true"; cursor="..."
                start = segment.find("<")
                end = segment.find(">")
                if start != -1 and end != -1:
                    return segment[start + 1:end]
        return None

    # ------------------------------------------------------------------
    def fetch(self) -> List[BugItem]:
        if not self.config.enabled:
            log.info("Sentry source disabled (missing token or org slug); skipping.")
            return []
        items: List[BugItem] = []
        for project in self._projects():
            log.info("Fetching Sentry issues for project=%s", project)
            items.extend(self._fetch_project(project))
        return items

    def _fetch_project(self, project_slug: str) -> Iterable[BugItem]:
        url = (
            f"{self.config.host}/api/0/projects/"
            f"{self.config.org_slug}/{project_slug}/issues/"
        )
        params = {"query": self.config.query, "limit": _PAGE_SIZE}
        results: List[BugItem] = []
        while url:
            resp = self._session.get(url, params=params if "?" not in url else None, timeout=_TIMEOUT)
            if resp.status_code == 404:
                log.warning("Sentry project not found: %s", project_slug)
                return results
            resp.raise_for_status()
            for issue in resp.json():
                results.append(self._to_bug_item(issue, project_slug))
            url = self._next_link(resp)
            params = None  # cursor URL already includes query string
        return results

    @staticmethod
    def _to_bug_item(issue: dict, project_slug: str) -> BugItem:
        assignee_obj = issue.get("assignedTo") or {}
        assignee = ""
        if isinstance(assignee_obj, dict):
            assignee = assignee_obj.get("name") or assignee_obj.get("email") or ""
        metadata = issue.get("metadata") or {}
        description = metadata.get("value") or issue.get("culprit") or ""
        return BugItem(
            source="Sentry",
            external_id=str(issue.get("shortId") or issue.get("id")),
            title=issue.get("title") or "(untitled)",
            status=issue.get("status") or "",
            severity=issue.get("level") or "",
            url=issue.get("permalink") or "",
            assignee=assignee,
            created_at=_parse_dt(issue.get("firstSeen")),
            updated_at=_parse_dt(issue.get("lastSeen")),
            description=description,
            labels=[issue.get("level")] if issue.get("level") else [],
            project=project_slug,
            raw=issue,
        )
