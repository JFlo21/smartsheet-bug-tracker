"""GitHub issue source.

Pulls all open issues labeled as bugs from one or more repositories using
PyGithub. Pull-requests are filtered out (the Issues API returns PRs as
issues too).
"""

from __future__ import annotations

import logging
from typing import List

from github import Github, Auth
from github.GithubException import GithubException

from .config import GitHubConfig
from .models import BugItem

log = logging.getLogger(__name__)


class GitHubSource:
    def __init__(self, config: GitHubConfig):
        self.config = config
        self._client = Github(auth=Auth.Token(config.token)) if config.token else None

    def fetch(self) -> List[BugItem]:
        if not self.config.enabled or self._client is None:
            log.info("GitHub source disabled (missing token or repos); skipping.")
            return []
        items: List[BugItem] = []
        for repo_full_name in self.config.repos:
            log.info("Fetching GitHub bug issues for repo=%s", repo_full_name)
            try:
                items.extend(self._fetch_repo(repo_full_name))
            except GithubException as exc:
                log.error("GitHub error for %s: %s", repo_full_name, exc)
        return items

    def _fetch_repo(self, repo_full_name: str) -> List[BugItem]:
        repo = self._client.get_repo(repo_full_name)
        # PyGithub's get_issues returns issues *and* pull requests; filter PRs out.
        issues = repo.get_issues(state="open", labels=[self.config.bug_label])
        results: List[BugItem] = []
        for issue in issues:
            if issue.pull_request is not None:
                continue
            assignee = issue.assignee.login if issue.assignee else ""
            results.append(
                BugItem(
                    source="GitHub",
                    external_id=f"{repo_full_name}#{issue.number}",
                    title=issue.title or "(untitled)",
                    status=issue.state or "",
                    severity=self.config.bug_label,
                    url=issue.html_url or "",
                    assignee=assignee,
                    created_at=issue.created_at,
                    updated_at=issue.updated_at,
                    description=(issue.body or "")[:4000],
                    labels=[label.name for label in issue.labels],
                    project=repo_full_name,
                    raw={
                        "number": issue.number,
                        "repo": repo_full_name,
                        "state": issue.state,
                    },
                )
            )
        return results
