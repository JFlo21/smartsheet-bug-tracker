"""Linear issue source (GraphQL API).

Docs: https://developers.linear.app/docs/graphql/working-with-the-graphql-api
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests

from .config import LinearConfig
from .models import BugItem

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.linear.app/graphql"
_TIMEOUT = 30
_PAGE_SIZE = 50

_QUERY = """
query Issues($after: String, $filter: IssueFilter) {
  issues(first: %d, after: $after, filter: $filter) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      identifier
      title
      description
      url
      createdAt
      updatedAt
      priorityLabel
      state { name type }
      assignee { name email }
      team { key name }
      labels { nodes { name } }
    }
  }
}
""" % _PAGE_SIZE


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class LinearSource:
    def __init__(self, config: LinearConfig):
        self.config = config

    # ------------------------------------------------------------------
    def _build_filter(self) -> Optional[Dict[str, Any]]:
        filter_obj: Dict[str, Any] = {}
        if self.config.bug_label:
            filter_obj["labels"] = {"name": {"eqIgnoreCase": self.config.bug_label}}
        if self.config.team_keys:
            filter_obj["team"] = {"key": {"in": self.config.team_keys}}
        # Exclude completed/canceled by default to mirror the spirit of "open bugs"
        filter_obj["state"] = {"type": {"nin": ["completed", "canceled"]}}
        return filter_obj or None

    # ------------------------------------------------------------------
    def fetch(self) -> List[BugItem]:
        if not self.config.enabled:
            log.info("Linear source disabled (missing API key); skipping.")
            return []

        headers = {
            # Linear accepts the raw API key in the Authorization header.
            "Authorization": self.config.api_key,
            "Content-Type": "application/json",
        }
        results: List[BugItem] = []
        cursor: Optional[str] = None
        filter_obj = self._build_filter()
        log.info("Fetching Linear issues (filter=%s)", filter_obj)
        while True:
            payload = {
                "query": _QUERY,
                "variables": {"after": cursor, "filter": filter_obj},
            }
            resp = requests.post(_ENDPOINT, json=payload, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data and data["errors"]:
                raise RuntimeError(f"Linear API error: {data['errors']}")
            issues_block = data["data"]["issues"]
            for node in issues_block["nodes"]:
                results.append(self._to_bug_item(node))
            page_info = issues_block["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]
        return results

    @staticmethod
    def _to_bug_item(node: Dict[str, Any]) -> BugItem:
        assignee_obj = node.get("assignee") or {}
        team_obj = node.get("team") or {}
        state_obj = node.get("state") or {}
        labels = [n["name"] for n in (node.get("labels") or {}).get("nodes", [])]
        return BugItem(
            source="Linear",
            external_id=node.get("identifier") or node.get("id") or "",
            title=node.get("title") or "(untitled)",
            status=state_obj.get("name") or "",
            severity=node.get("priorityLabel") or "",
            url=node.get("url") or "",
            assignee=assignee_obj.get("name") or assignee_obj.get("email") or "",
            created_at=_parse_dt(node.get("createdAt")),
            updated_at=_parse_dt(node.get("updatedAt")),
            description=(node.get("description") or "")[:4000],
            labels=labels,
            project=team_obj.get("key") or team_obj.get("name") or "",
            raw=node,
        )
