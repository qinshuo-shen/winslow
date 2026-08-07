"""
In-process cache for notion_tasks.fetch_actionable_tasks().

Same anti-pattern, same fix, as calendar_cache.py: fetch_actionable_tasks()
does two live Notion network round trips (client.databases.retrieve() to
resolve data_source_id, then client.data_sources.query()), and was being
called fresh, uncached, on every GET /api/tasks *and* on every drag-and-drop
action via planner.py's _find_task() (which re-runs the entire query just to
find one task by page_id). At realistic Notion API latency (150-500ms/call,
more under any rate-limiting), that's meaningful avoidable network time
stacked onto every task-list load and every drag.

This module is the fix: the one read path for actionable tasks in the API
layer. A short TTL bounds staleness from changes made directly in Notion;
explicit invalidate() after this app's own Notion writes (currently just
tasks.py's complete_task()) means those are never stale regardless of TTL.
"""
import time
from threading import Lock
from typing import List, Optional

from procrastination_tool import notion_tasks

_TTL_SECONDS = 30

_lock = Lock()
_cache: Optional[List[notion_tasks.Task]] = None
_cached_at: float = 0.0


def get_tasks(force_refresh: bool = False) -> List[notion_tasks.Task]:
    global _cache, _cached_at
    with _lock:
        stale = _cache is None or (time.monotonic() - _cached_at) > _TTL_SECONDS
        if force_refresh or stale:
            _cache = notion_tasks.fetch_actionable_tasks()
            _cached_at = time.monotonic()
        return _cache


def invalidate() -> None:
    """Call after any write to Notion this app itself makes (currently
    mark_task_completed(), via sync.complete_task_and_cleanup()) so the
    next read reflects it immediately rather than waiting out the TTL."""
    global _cache
    with _lock:
        _cache = None
