"""Command-line entrypoint for the bug-tracker pipeline.

Usage:
    python -m src.main           # collect + write to Smartsheet
    python -m src.main --dry-run # collect + print, do not write
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List

from .config import AppConfig
from .context_generator import ContextGenerator
from .github_source import GitHubSource
from .linear_source import LinearSource
from .models import BugItem
from .sentry_source import SentrySource
from .smartsheet_client import SmartsheetClient


def _collect(config: AppConfig) -> List[BugItem]:
    items: List[BugItem] = []
    items.extend(SentrySource(config.sentry).fetch())
    items.extend(GitHubSource(config.github).fetch())
    items.extend(LinearSource(config.linear).fetch())
    return items


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate Sentry/GitHub/Linear bugs into Smartsheet.")
    parser.add_argument("--dry-run", action="store_true", help="Collect and annotate items but do not write to Smartsheet.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bug-tracker")

    config = AppConfig.from_env()

    log.info("Collecting bugs from configured sources...")
    items = _collect(config)
    log.info("Collected %d bug items.", len(items))

    log.info("Generating context column...")
    ContextGenerator(config.context).annotate(items)

    if args.dry_run:
        json.dump([item.as_dict() for item in items], sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    client = SmartsheetClient(config.smartsheet)
    stats = client.upsert(items)
    log.info("Done. %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
