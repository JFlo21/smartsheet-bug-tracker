"""Common data model for bug/issue records pulled from any source."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List


@dataclass
class BugItem:
    """Normalized representation of a single bug/issue across sources.

    The combination of ``source`` and ``external_id`` is the stable upsert key
    used when reconciling rows on the Smartsheet sheet.
    """

    source: str  # "Sentry" | "GitHub" | "Linear"
    external_id: str  # provider-native stable id (e.g. Sentry short id, GH issue number, Linear identifier)
    title: str
    status: str = ""
    severity: str = ""  # e.g. error/warning/fatal, or priority label
    url: str = ""
    assignee: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    description: str = ""
    labels: List[str] = field(default_factory=list)
    project: str = ""  # Sentry project slug, GH "owner/repo", Linear team key
    context: str = ""  # populated by ContextGenerator before upsert
    # Raw payload kept for debugging / future column additions
    raw: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """Stable composite key used to match rows on the sheet."""
        return f"{self.source}:{self.external_id}"

    def to_row_values(self) -> Dict[str, str]:
        """Return a dict of column-name -> cell value strings.

        Keys here MUST match the column titles created by
        :class:`SmartsheetClient.ensure_columns`.
        """
        return {
            "Key": self.key(),
            "Source": self.source,
            "External ID": self.external_id,
            "Title": self.title,
            "Status": self.status,
            "Severity": self.severity,
            "Project": self.project,
            "Assignee": self.assignee,
            "Labels": ", ".join(self.labels),
            "URL": self.url,
            "Created At": self.created_at.isoformat() if self.created_at else "",
            "Updated At": self.updated_at.isoformat() if self.updated_at else "",
            "Context": self.context,
        }

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.created_at:
            d["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            d["updated_at"] = self.updated_at.isoformat()
        return d


# Column titles, in the order they should appear on the Smartsheet sheet.
# "Key" is the primary column (text/number primary in Smartsheet).
SHEET_COLUMNS: List[str] = [
    "Key",
    "Source",
    "External ID",
    "Title",
    "Status",
    "Severity",
    "Project",
    "Assignee",
    "Labels",
    "URL",
    "Created At",
    "Updated At",
    "Context",
]
