# smartsheet-bug-tracker

Sync bugs from Sentry and GitHub into a Smartsheet sheet.

## What it does

- Pulls issues from a single Sentry project
- Pulls issues from a single GitHub repository
- Upserts rows in Smartsheet using `Source + External ID` as a unique key

## Required sheet columns

The target Smartsheet must have these column titles:

- `Source`
- `External ID`
- `Title`
- `URL`
- `Status`
- `Priority`
- `Created At`
- `Updated At`
- `Assignee`
- `Project`

## Configuration

Set environment variables:

- `SMARKSHEET_ACCESS_TOKEN` **(deprecated typo; supported for backward compatibility)**
- `SMARTSHEET_ACCESS_TOKEN`
- `SMARTSHEET_SHEET_ID`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG_SLUG`
- `SENTRY_PROJECT_SLUG`
- `GITHUB_REPO` (format: `owner/repo`)
- `GITHUB_TOKEN` (optional, but recommended to avoid low rate limits)

Optional overrides:

- `SENTRY_API_URL` (default: `https://sentry.io/api/0`)
- `GITHUB_API_URL` (default: `https://api.github.com`)
- `SMARTSHEET_API_URL` (default: `https://api.smartsheet.com/2.0`)

## Run

```bash
python /tmp/workspace/JFlo21/smartsheet-bug-tracker/sync_bug_tracker.py
```

## Test

```bash
python -m unittest discover -s /tmp/workspace/JFlo21/smartsheet-bug-tracker/tests -p "test_*.py"
```
