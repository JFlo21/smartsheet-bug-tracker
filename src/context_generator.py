"""Generate the per-bug "Context" column text.

Strategy:
* If an OpenAI API key is configured, request a short structured
  explanation + fix-suggestion for each bug.
* Otherwise fall back to a deterministic rule-based summary derived from
  the bug's title, description, labels, and severity. This keeps the
  pipeline functional in environments without LLM access.
"""

from __future__ import annotations

import logging
import textwrap
from typing import List

from .config import ContextConfig
from .models import BugItem

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an experienced software engineer helping triage bugs. "
    "For each bug you are given, write a concise (3-5 sentence) explanation "
    "covering: (1) what the bug most likely is, (2) why it probably happens, "
    "and (3) a concrete first step a developer should take to investigate or "
    "fix it. Do not invent specifics that are not in the bug. Plain text, no markdown."
)


class ContextGenerator:
    def __init__(self, config: ContextConfig):
        self.config = config
        self._client = None
        if self.config.use_openai:
            try:
                from openai import OpenAI  # type: ignore
                self._client = OpenAI(api_key=self.config.openai_api_key)
            except Exception as exc:  # pragma: no cover - openai is optional
                log.warning("OpenAI client unavailable, falling back to rules: %s", exc)
                self._client = None

    # ------------------------------------------------------------------
    def annotate(self, items: List[BugItem]) -> None:
        """Mutate each item in-place, populating ``item.context``."""
        for item in items:
            try:
                item.context = self._for_item(item)
            except Exception as exc:  # one failure should not abort the batch
                log.warning("Context generation failed for %s: %s", item.key(), exc)
                item.context = self._rule_based(item)

    # ------------------------------------------------------------------
    def _for_item(self, item: BugItem) -> str:
        if self._client is not None:
            return self._llm(item)
        return self._rule_based(item)

    def _llm(self, item: BugItem) -> str:
        user_msg = textwrap.dedent(
            f"""
            Source: {item.source}
            Project: {item.project}
            Title: {item.title}
            Severity/Level: {item.severity}
            Status: {item.status}
            Labels: {', '.join(item.labels) or '(none)'}
            URL: {item.url}
            Description:
            {item.description[:2000] or '(none)'}
            """
        ).strip()
        resp = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()

    @staticmethod
    def _rule_based(item: BugItem) -> str:
        """Deterministic fallback summary.

        Surfaces the most useful triage info even when no LLM is available.
        """
        lines = []
        lines.append(
            f"{item.source} {item.severity or 'issue'} in '{item.project or 'n/a'}': {item.title}."
        )
        if item.description:
            snippet = " ".join(item.description.split())[:400]
            lines.append(f"Reported details: {snippet}")
        hints = []
        title_lower = (item.title or "").lower()
        desc_lower = (item.description or "").lower()
        haystack = f"{title_lower}\n{desc_lower}"
        if any(k in haystack for k in ("nullpointer", "none type", "nonetype", "null reference", "undefined is not")):
            hints.append(
                "Looks like a null/undefined reference — check that all required objects "
                "are initialized before use and add defensive guards on optional fields."
            )
        if any(k in haystack for k in ("timeout", "timed out", "deadline exceeded")):
            hints.append(
                "Timeout symptom — verify downstream service latency, retry/backoff policy, "
                "and connection pool sizing."
            )
        if any(k in haystack for k in ("permission", "forbidden", "401", "403", "unauthorized")):
            hints.append(
                "Authorization-related — confirm tokens/scopes, role mappings, and that the "
                "caller's identity is propagated end-to-end."
            )
        if any(k in haystack for k in ("memory", "oom", "out of memory")):
            hints.append(
                "Memory pressure — profile for leaks, check container limits, and inspect "
                "recent changes to caches or large in-memory collections."
            )
        if any(k in haystack for k in ("sql", "deadlock", "duplicate key", "constraint")):
            hints.append(
                "Database-related — review the failing query, transaction boundaries, and "
                "indexes/constraints on the affected table."
            )
        if not hints:
            hints.append(
                "Start by reproducing locally with the data referenced above, then bisect "
                "recent commits touching this area to isolate the regression."
            )
        lines.append("Suggested next step: " + " ".join(hints))
        return " ".join(lines)
