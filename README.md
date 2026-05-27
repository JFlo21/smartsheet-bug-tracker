# smartsheet-bug-tracker

Aggregate bugs from **Sentry**, **GitHub** (issues labeled `bug`), and **Linear**
into a single **Smartsheet** sheet — including an automatically-generated
**Context** column that explains each bug and suggests a first step toward
fixing it.

The tool is idempotent: rows are keyed by `Source:ExternalID` so re-running
the pipeline updates existing rows in place instead of duplicating them.

## How it works

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│  Sentry  │   │  GitHub  │   │  Linear  │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │
     └──────┬───────┴──────┬───────┘
            ▼              ▼
       Normalize        Context
       to BugItem    (OpenAI/rules)
            └──────┬───────┘
                   ▼
            ┌────────────┐
            │ Smartsheet │  (upsert by Key column)
            └────────────┘
```

* Each source has its own connector (`src/sentry_source.py`,
  `src/github_source.py`, `src/linear_source.py`) that returns a list of
  `BugItem` records.
* `src/context_generator.py` enriches each item with a `Context` value. If
  `OPENAI_API_KEY` is set it uses an OpenAI chat model; otherwise it falls
  back to a deterministic rule-based summary so the pipeline still works
  offline.
* `src/smartsheet_client.py` wraps the official `smartsheet-python-sdk`,
  ensures the required columns exist on the target sheet, and upserts rows
  keyed by the `Key` column.

## Sheet columns

The first run will automatically create any of these columns that are not
already present on the target sheet (in this order):

| Column        | Notes                                                   |
| ------------- | ------------------------------------------------------- |
| Key           | Primary column — `Sentry:ABC-1`, `GitHub:owner/repo#42`, `Linear:ENG-7` |
| Source        | `Sentry` / `GitHub` / `Linear`                          |
| External ID   | Provider-native id                                      |
| Title         | Bug title                                               |
| Status        | Open / unresolved / etc.                                |
| Severity      | Sentry level, Linear priority label, or `bug` for GH    |
| Project       | Sentry project, `owner/repo`, or Linear team key        |
| Assignee      | Display name / email if available                       |
| Labels        | Comma-separated                                         |
| URL           | Deep link to the original issue                         |
| Created At    | ISO-8601                                                |
| Updated At    | ISO-8601                                                |
| Context       | What the bug is and how to start fixing it              |

## Setup

```bash
git clone https://github.com/JFlo21/smartsheet-bug-tracker.git
cd smartsheet-bug-tracker

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env with your tokens and IDs
```

### Required configuration

See `.env.example` for the full list. At minimum you need:

* `SMARTSHEET_ACCESS_TOKEN` — Smartsheet API token
* `SMARTSHEET_SHEET_ID` — the numeric ID of the target sheet (visible in the
  sheet's URL or via *File → Properties*)

Then enable any subset of:

* **Sentry** — `SENTRY_AUTH_TOKEN`, `SENTRY_ORG_SLUG`, optionally
  `SENTRY_PROJECT_SLUGS` and `SENTRY_QUERY`
* **GitHub** — `GITHUB_TOKEN`, `GITHUB_REPOS` (comma-separated `owner/repo`),
  optional `GITHUB_BUG_LABEL` (default `bug`)
* **Linear** — `LINEAR_API_KEY`, optional `LINEAR_BUG_LABEL` (default `Bug`)
  and `LINEAR_TEAM_KEYS`

A source is automatically skipped if its credentials are not configured —
you can run the tool with just one provider configured if that's all you
need.

## Run

```bash
# Dry run – fetch + annotate, print JSON, do NOT touch Smartsheet
python -m src.main --dry-run

# Real run – fetch, annotate, and upsert into Smartsheet
python -m src.main
```

A typical setup runs this on a schedule (cron, GitHub Actions, etc.) so the
Smartsheet sheet always reflects the current state of open bugs.

## Tests

```bash
pip install pytest
pytest
```

The unit tests cover the data model and the offline (rule-based) context
generator so they run without any external API access.

## References

* Smartsheet API: <https://smartsheet.redoc.ly/>
* Smartsheet Python SDK: <https://github.com/smartsheet/smartsheet-python-sdk>
* Sentry API – list project issues: <https://docs.sentry.io/api/events/list-a-projects-issues/>
* GitHub Issues (via PyGithub): <https://pygithub.readthedocs.io/>
* Linear GraphQL API: <https://developers.linear.app/docs/graphql/working-with-the-graphql-api>
