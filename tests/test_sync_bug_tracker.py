import unittest

from sync_bug_tracker import BugIssue, SmartsheetClient, parse_link_header


class ParseLinkHeaderTests(unittest.TestCase):
    def test_extracts_next_and_prev(self):
        header = '<https://example.com?page=2>; rel="next", <https://example.com?page=1>; rel="prev"'
        parsed = parse_link_header(header)
        self.assertEqual("https://example.com?page=2", parsed["next"])
        self.assertEqual("https://example.com?page=1", parsed["prev"])


class SmartsheetPayloadTests(unittest.TestCase):
    def test_build_row_payload_contains_expected_cells(self):
        issue = BugIssue(
            source="GitHub",
            external_id="123",
            title="Broken route",
            url="https://example.com/123",
            status="open",
            priority="bug,high",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-02T00:00:00+00:00",
            assignee="jdoe",
            project="org/repo",
        )
        col_map = {
            "Source": 1,
            "External ID": 2,
            "Title": 3,
            "URL": 4,
            "Status": 5,
            "Priority": 6,
            "Created At": 7,
            "Updated At": 8,
            "Assignee": 9,
            "Project": 10,
        }
        payload = SmartsheetClient.build_row_payload(issue, col_map)
        self.assertTrue(payload["toBottom"])
        self.assertEqual(10, len(payload["cells"]))
        by_col = {c["columnId"]: c["value"] for c in payload["cells"]}
        self.assertEqual("GitHub", by_col[1])
        self.assertEqual("123", by_col[2])
        self.assertEqual("Broken route", by_col[3])

    def test_existing_issue_keys_uses_source_and_external_id(self):
        client = SmartsheetClient("https://api.smartsheet.com/2.0", "token")
        sheet = {
            "columns": [
                {"id": 1, "title": "Source"},
                {"id": 2, "title": "External ID"},
            ],
            "rows": [
                {"cells": [{"columnId": 1, "value": "Sentry"}, {"columnId": 2, "displayValue": "abc"}]},
                {"cells": [{"columnId": 1, "value": "GitHub"}, {"columnId": 2, "value": 55}]},
            ],
        }
        keys = client._existing_issue_keys(sheet, {"Source": 1, "External ID": 2})
        self.assertIn(("Sentry", "abc"), keys)
        self.assertIn(("GitHub", "55"), keys)


if __name__ == "__main__":
    unittest.main()
