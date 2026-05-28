from datetime import datetime, timezone

from src.config import ContextConfig
from src.context_generator import ContextGenerator
from src.models import BugItem, SHEET_COLUMNS


def _make_item(**overrides) -> BugItem:
    defaults = dict(
        source="Sentry",
        external_id="ABC-1",
        title="NullPointerException in UserService",
        status="unresolved",
        severity="error",
        url="https://example/sentry/ABC-1",
        assignee="alice",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        description="java.lang.NullPointerException at UserService.load(UserService.java:42)",
        labels=["error"],
        project="api",
    )
    defaults.update(overrides)
    return BugItem(**defaults)


def test_bug_item_key_is_stable():
    item = _make_item()
    assert item.key() == "Sentry:ABC-1"


def test_to_row_values_covers_all_sheet_columns():
    item = _make_item()
    values = item.to_row_values()
    # Every column we tell Smartsheet to create should have a value mapping.
    for column in SHEET_COLUMNS:
        assert column in values, f"missing column mapping: {column}"


def test_context_fallback_runs_without_openai():
    gen = ContextGenerator(ContextConfig(openai_api_key=""))
    item = _make_item()
    gen.annotate([item])
    assert item.context
    # The rule-based summary should pick up on the null-pointer pattern.
    assert "null" in item.context.lower() or "undefined" in item.context.lower()


def test_context_fallback_handles_empty_description():
    gen = ContextGenerator(ContextConfig(openai_api_key=""))
    item = _make_item(description="", labels=[], title="Mystery failure")
    gen.annotate([item])
    assert item.context
    assert "Suggested next step" in item.context


def test_to_row_values_truncates_nothing_short_of_4000():
    item = _make_item(description="x" * 100)
    values = item.to_row_values()
    # Title/description still fit in the limits used by the client wrapper.
    assert len(values["Title"]) < 4000
