#!/usr/bin/env python3
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError


@dataclass
class BugIssue:
    source: str
    external_id: str
    title: str
    url: str
    status: str
    priority: str
    created_at: str
    updated_at: str
    assignee: str
    project: str


def parse_link_header(link_header: Optional[str]) -> Dict[str, str]:
    if not link_header:
        return {}
    results: Dict[str, str] = {}
    for part in link_header.split(","):
        item = part.strip()
        if ";" not in item or not item.startswith("<"):
            continue
        url_part, meta_part = item.split(";", 1)
        rel = None
        for meta in meta_part.split(";"):
            meta = meta.strip()
            if meta.startswith("rel="):
                rel = meta.split("=", 1)[1].strip('"')
                break
        if rel:
            results[rel] = url_part.strip()[1:-1]
    return results


class JsonApiClient:
    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url.rstrip("/") + "/"
        self.headers = headers or {}

    def request(self, method: str, path_or_url: str, query: Optional[Dict[str, str]] = None, payload=None):
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = urljoin(self.base_url, path_or_url.lstrip("/"))

        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(query)}"

        body = None
        headers = dict(self.headers)
        headers["Accept"] = "application/json"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url=url, method=method, headers=headers, data=body)
        try:
            with urlopen(req) as response:
                response_body = response.read().decode("utf-8")
                parsed = json.loads(response_body) if response_body else None
                return parsed, dict(response.headers)
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} failed ({exc.code}): {error_body}") from exc

    def get_paginated(self, path: str, query: Optional[Dict[str, str]] = None) -> List[dict]:
        items: List[dict] = []
        next_url = path
        next_query = query

        while next_url:
            payload, headers = self.request("GET", next_url, query=next_query)
            if isinstance(payload, list):
                items.extend(payload)
            else:
                items.extend(payload.get("data", []) if isinstance(payload, dict) else [])

            links = parse_link_header(headers.get("Link"))
            next_url = links.get("next")
            next_query = None

        return items


class SentryClient(JsonApiClient):
    def __init__(self, api_url: str, token: str):
        super().__init__(api_url, headers={"Authorization": f"Bearer {token}"})

    def list_project_issues(self, org_slug: str, project_slug: str) -> List[BugIssue]:
        raw = self.get_paginated(f"projects/{org_slug}/{project_slug}/issues/", query={"limit": "100"})
        issues: List[BugIssue] = []
        for issue in raw:
            assignee = issue.get("assignedTo") or {}
            issues.append(
                BugIssue(
                    source="Sentry",
                    external_id=str(issue.get("id", "")),
                    title=issue.get("title", ""),
                    url=issue.get("permalink", ""),
                    status=issue.get("status", ""),
                    priority=issue.get("level", ""),
                    created_at=issue.get("firstSeen", ""),
                    updated_at=issue.get("lastSeen", ""),
                    assignee=assignee.get("email") or assignee.get("name") or "",
                    project=project_slug,
                )
            )
        return issues


class GitHubClient(JsonApiClient):
    def __init__(self, api_url: str, token: Optional[str]):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        super().__init__(api_url, headers=headers)

    def list_repo_issues(self, owner: str, repo: str) -> List[BugIssue]:
        raw = self.get_paginated(f"repos/{owner}/{repo}/issues", query={"state": "all", "per_page": "100"})
        issues: List[BugIssue] = []
        for issue in raw:
            if "pull_request" in issue:
                continue
            assignee = issue.get("assignee") or {}
            labels = issue.get("labels") or []
            priority = ",".join([label.get("name", "") for label in labels if label.get("name")])
            issues.append(
                BugIssue(
                    source="GitHub",
                    external_id=str(issue.get("number", "")),
                    title=issue.get("title", ""),
                    url=issue.get("html_url", ""),
                    status=issue.get("state", ""),
                    priority=priority,
                    created_at=issue.get("created_at", ""),
                    updated_at=issue.get("updated_at", ""),
                    assignee=assignee.get("login", ""),
                    project=f"{owner}/{repo}",
                )
            )
        return issues


class SmartsheetClient(JsonApiClient):
    REQUIRED_COLUMNS = [
        "Source",
        "External ID",
        "Title",
        "URL",
        "Status",
        "Priority",
        "Created At",
        "Updated At",
        "Assignee",
        "Project",
    ]

    def __init__(self, api_url: str, token: str):
        super().__init__(api_url, headers={"Authorization": f"Bearer {token}"})

    def get_sheet(self, sheet_id: str) -> dict:
        sheet, _ = self.request("GET", f"sheets/{sheet_id}")
        return sheet

    def _column_mapping(self, sheet: dict) -> Dict[str, int]:
        mapping = {}
        for col in sheet.get("columns", []):
            title = col.get("title")
            if title:
                mapping[title] = col.get("id")
        missing = [name for name in self.REQUIRED_COLUMNS if name not in mapping]
        if missing:
            raise RuntimeError(f"Smartsheet is missing required columns: {', '.join(missing)}")
        return mapping

    @staticmethod
    def _read_cell_display(cell: dict) -> str:
        val = cell.get("displayValue")
        if val is None:
            val = cell.get("value")
        return "" if val is None else str(val)

    def _existing_issue_keys(self, sheet: dict, col_map: Dict[str, int]) -> set:
        by_id = {col.get("id"): col.get("title") for col in sheet.get("columns", [])}
        keys = set()
        for row in sheet.get("rows", []):
            row_data: Dict[str, str] = {}
            for cell in row.get("cells", []):
                title = by_id.get(cell.get("columnId"))
                if title in ("Source", "External ID"):
                    row_data[title] = self._read_cell_display(cell)
            if row_data.get("Source") and row_data.get("External ID"):
                keys.add((row_data["Source"], row_data["External ID"]))
        return keys

    @staticmethod
    def build_row_payload(issue: BugIssue, col_map: Dict[str, int]) -> dict:
        value_map = {
            "Source": issue.source,
            "External ID": issue.external_id,
            "Title": issue.title,
            "URL": issue.url,
            "Status": issue.status,
            "Priority": issue.priority,
            "Created At": issue.created_at,
            "Updated At": issue.updated_at,
            "Assignee": issue.assignee,
            "Project": issue.project,
        }
        cells = [{"columnId": col_map[name], "value": value_map[name], "strict": False} for name in value_map]
        return {"toBottom": True, "cells": cells}

    def upsert_issues(self, sheet_id: str, issues: Iterable[BugIssue]) -> int:
        sheet = self.get_sheet(sheet_id)
        col_map = self._column_mapping(sheet)
        existing = self._existing_issue_keys(sheet, col_map)
        new_rows = []
        for issue in issues:
            key = (issue.source, issue.external_id)
            if key in existing:
                continue
            new_rows.append(self.build_row_payload(issue, col_map))

        if not new_rows:
            return 0

        self.request("POST", f"sheets/{sheet_id}/rows", payload=new_rows)
        return len(new_rows)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _normalize_iso(value: str) -> str:
    if not value:
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def main() -> None:
    smartsheet_token = os.getenv("SMARTSHEET_ACCESS_TOKEN") or os.getenv("SMARKSHEET_ACCESS_TOKEN")
    if not smartsheet_token:
        raise RuntimeError("Missing required environment variable: SMARTSHEET_ACCESS_TOKEN")

    smartsheet_sheet_id = _require_env("SMARTSHEET_SHEET_ID")
    sentry_token = _require_env("SENTRY_AUTH_TOKEN")
    sentry_org = _require_env("SENTRY_ORG_SLUG")
    sentry_project = _require_env("SENTRY_PROJECT_SLUG")
    github_repo = _require_env("GITHUB_REPO")
    github_token = os.getenv("GITHUB_TOKEN")

    if "/" not in github_repo:
        raise RuntimeError("GITHUB_REPO must be in the format owner/repo")
    github_owner, github_name = github_repo.split("/", 1)

    sentry_api = os.getenv("SENTRY_API_URL", "https://sentry.io/api/0")
    github_api = os.getenv("GITHUB_API_URL", "https://api.github.com")
    smartsheet_api = os.getenv("SMARTSHEET_API_URL", "https://api.smartsheet.com/2.0")

    sentry_client = SentryClient(sentry_api, sentry_token)
    github_client = GitHubClient(github_api, github_token)
    smartsheet_client = SmartsheetClient(smartsheet_api, smartsheet_token)

    sentry_issues = sentry_client.list_project_issues(sentry_org, sentry_project)
    github_issues = github_client.list_repo_issues(github_owner, github_name)
    all_issues = sentry_issues + github_issues

    for issue in all_issues:
        issue.created_at = _normalize_iso(issue.created_at)
        issue.updated_at = _normalize_iso(issue.updated_at)

    inserted = smartsheet_client.upsert_issues(smartsheet_sheet_id, all_issues)
    print(f"Loaded {len(all_issues)} total issues; inserted {inserted} new Smartsheet rows.")


if __name__ == "__main__":
    main()
