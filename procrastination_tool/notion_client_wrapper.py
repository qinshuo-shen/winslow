"""
Minimal Notion connectivity check for Phase 0. Phase 1 will add the real
task-query/filter/sort logic (priority + deadline, actionable-only) on top
of this same client.

Reminder (the Notion gotcha flagged in the project plan): a newly created
integration must be manually shared with the target database (Database ->
... -> Connections) or every query 404s in a way that looks like a bug
rather than a permissions issue.
"""
from notion_client import Client

from .config import NOTION_DATABASE_ID, NOTION_TOKEN


def is_configured() -> bool:
    return bool(NOTION_TOKEN and NOTION_DATABASE_ID)


def check_connection() -> str:
    """Query the configured database and return its title, or raise."""
    if not is_configured():
        raise RuntimeError("NOTION_TOKEN / NOTION_DATABASE_ID not set in .env")
    client = Client(auth=NOTION_TOKEN)
    db = client.databases.retrieve(database_id=NOTION_DATABASE_ID)
    title_parts = db.get("title", [])
    title = "".join(part.get("plain_text", "") for part in title_parts) or "(untitled database)"
    return title
