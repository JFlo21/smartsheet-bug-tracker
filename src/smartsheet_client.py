"""Smartsheet client wrapper.

Responsibilities:
* Ensure the target sheet has all of the columns we expect (creating any
  that are missing).
* Upsert rows keyed by the composite "Key" column (Source:ExternalID) so
  re-running the pipeline updates existing rows instead of duplicating
  them.

Uses the official ``smartsheet-python-sdk``. Reference:
https://smartsheet.redoc.ly/  and  https://github.com/smartsheet/smartsheet-python-sdk
"""

from __future__ import annotations

import logging
from typing import Dict, List, Iterable

import smartsheet
from smartsheet.models import Column, Cell, Row

from .config import SmartsheetConfig
from .models import BugItem, SHEET_COLUMNS

log = logging.getLogger(__name__)

# Smartsheet API rejects requests with more than 500 rows at a time.
_BATCH_SIZE = 300
# Smartsheet text/number cells reject values longer than 4000 characters.
_MAX_CELL_LENGTH = 4000


class SmartsheetClient:
    def __init__(self, config: SmartsheetConfig):
        self.config = config
        self._client = smartsheet.Smartsheet(config.access_token)
        # Raise on any API error rather than returning a partial result.
        self._client.errors_as_exceptions(True)
        self._column_map: Dict[str, int] = {}

    # ------------------------------------------------------------------
    def ensure_columns(self) -> Dict[str, int]:
        """Ensure all required columns exist on the sheet.

        Returns a mapping of column title -> column id.
        """
        sheet = self._client.Sheets.get_sheet(self.config.sheet_id)
        existing = {col.title: col for col in sheet.columns}
        self._column_map = {title: col.id for title, col in existing.items()}

        # Smartsheet requires exactly one "primary" column. If the sheet is
        # empty (no columns at all), we have to add one as primary. If a
        # primary already exists, all added columns are non-primary.
        has_primary = any(getattr(c, "primary", False) for c in sheet.columns)

        # Index used to position newly added columns at the end of the sheet.
        next_index = len(sheet.columns)

        for title in SHEET_COLUMNS:
            if title in existing:
                continue
            new_col = Column({
                "title": title,
                "type": "TEXT_NUMBER",
                "index": next_index,
            })
            if title == "Key" and not has_primary:
                new_col.primary = True
                has_primary = True
            log.info("Adding missing column to Smartsheet: %s", title)
            resp = self._client.Sheets.add_columns(self.config.sheet_id, [new_col])
            for added in resp.result:
                self._column_map[added.title] = added.id
            next_index += 1
        return self._column_map

    # ------------------------------------------------------------------
    def _load_existing_keys(self) -> Dict[str, int]:
        """Return a mapping of Key cell value -> row id for rows already on the sheet."""
        if "Key" not in self._column_map:
            return {}
        key_col_id = self._column_map["Key"]
        sheet = self._client.Sheets.get_sheet(self.config.sheet_id)
        mapping: Dict[str, int] = {}
        for row in sheet.rows:
            for cell in row.cells:
                if cell.column_id == key_col_id and cell.value:
                    mapping[str(cell.value)] = row.id
                    break
        return mapping

    # ------------------------------------------------------------------
    def _row_from_item(self, item: BugItem, row_id: int | None = None) -> Row:
        row = Row()
        if row_id is not None:
            row.id = row_id
        else:
            row.to_bottom = True
        values = item.to_row_values()
        for title, value in values.items():
            col_id = self._column_map.get(title)
            if col_id is None:
                continue
            cell = Cell()
            cell.column_id = col_id
            # Smartsheet text cells reject values >4000 chars.
            text = "" if value is None else str(value)
            if len(text) > _MAX_CELL_LENGTH:
                text = text[:_MAX_CELL_LENGTH - 3] + "..."
            cell.value = text
            row.cells.append(cell)
        return row

    @staticmethod
    def _chunks(seq: List, size: int) -> Iterable[List]:
        for i in range(0, len(seq), size):
            yield seq[i:i + size]

    # ------------------------------------------------------------------
    def upsert(self, items: List[BugItem]) -> Dict[str, int]:
        """Add new rows and update existing ones in-place, keyed by ``BugItem.key()``.

        Returns a small stats dict.
        """
        self.ensure_columns()
        existing = self._load_existing_keys()

        to_add: List[Row] = []
        to_update: List[Row] = []
        seen_keys: set[str] = set()

        for item in items:
            key = item.key()
            if key in seen_keys:
                # Duplicate within this run (e.g. same GitHub issue if a repo is listed twice)
                continue
            seen_keys.add(key)
            if key in existing:
                to_update.append(self._row_from_item(item, row_id=existing[key]))
            else:
                to_add.append(self._row_from_item(item))

        added = updated = 0
        for batch in self._chunks(to_add, _BATCH_SIZE):
            resp = self._client.Sheets.add_rows(self.config.sheet_id, batch)
            added += len(resp.result)
        for batch in self._chunks(to_update, _BATCH_SIZE):
            resp = self._client.Sheets.update_rows(self.config.sheet_id, batch)
            updated += len(resp.result)

        log.info("Smartsheet upsert complete: added=%d updated=%d", added, updated)
        return {"added": added, "updated": updated, "total": len(seen_keys)}
