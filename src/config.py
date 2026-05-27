"""Environment-driven configuration for the bug tracker."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class SmartsheetConfig:
    access_token: str
    sheet_id: int

    @classmethod
    def from_env(cls) -> "SmartsheetConfig":
        token = os.getenv("SMARTSHEET_ACCESS_TOKEN", "").strip()
        sheet_id_raw = os.getenv("SMARTSHEET_SHEET_ID", "").strip()
        if not token:
            raise RuntimeError("SMARTSHEET_ACCESS_TOKEN is required")
        if not sheet_id_raw:
            raise RuntimeError("SMARTSHEET_SHEET_ID is required")
        try:
            sheet_id = int(sheet_id_raw)
        except ValueError as exc:
            raise RuntimeError("SMARTSHEET_SHEET_ID must be an integer") from exc
        return cls(access_token=token, sheet_id=sheet_id)


@dataclass
class SentryConfig:
    auth_token: str = ""
    org_slug: str = ""
    project_slugs: List[str] = field(default_factory=list)
    host: str = "https://sentry.io"
    query: str = "is:unresolved"

    @property
    def enabled(self) -> bool:
        return bool(self.auth_token and self.org_slug)

    @classmethod
    def from_env(cls) -> "SentryConfig":
        return cls(
            auth_token=os.getenv("SENTRY_AUTH_TOKEN", "").strip(),
            org_slug=os.getenv("SENTRY_ORG_SLUG", "").strip(),
            project_slugs=_split_csv(os.getenv("SENTRY_PROJECT_SLUGS")),
            host=os.getenv("SENTRY_HOST", "https://sentry.io").strip().rstrip("/"),
            query=os.getenv("SENTRY_QUERY", "is:unresolved").strip() or "is:unresolved",
        )


@dataclass
class GitHubConfig:
    token: str = ""
    repos: List[str] = field(default_factory=list)
    bug_label: str = "bug"

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repos)

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        return cls(
            token=os.getenv("GITHUB_TOKEN", "").strip(),
            repos=_split_csv(os.getenv("GITHUB_REPOS")),
            bug_label=os.getenv("GITHUB_BUG_LABEL", "bug").strip() or "bug",
        )


@dataclass
class LinearConfig:
    api_key: str = ""
    bug_label: str = "Bug"
    team_keys: List[str] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "LinearConfig":
        return cls(
            api_key=os.getenv("LINEAR_API_KEY", "").strip(),
            bug_label=os.getenv("LINEAR_BUG_LABEL", "Bug").strip(),
            team_keys=_split_csv(os.getenv("LINEAR_TEAM_KEYS")),
        )


@dataclass
class ContextConfig:
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def use_openai(self) -> bool:
        return bool(self.openai_api_key)

    @classmethod
    def from_env(cls) -> "ContextConfig":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        )


@dataclass
class AppConfig:
    smartsheet: SmartsheetConfig
    sentry: SentryConfig
    github: GitHubConfig
    linear: LinearConfig
    context: ContextConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            smartsheet=SmartsheetConfig.from_env(),
            sentry=SentryConfig.from_env(),
            github=GitHubConfig.from_env(),
            linear=LinearConfig.from_env(),
            context=ContextConfig.from_env(),
        )
