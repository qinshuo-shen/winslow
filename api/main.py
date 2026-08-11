"""
FastAPI app instance -- new read-only API layer over the existing
`procrastination_tool` package (Phase 1 of the Streamlit -> React+FastAPI
migration). No CORS middleware: the Vite dev server proxies `/api/*` to
this backend (same-origin from the browser's perspective), and in
production this backend serves the built frontend itself (Phase 6, see the
StaticFiles mount below).

Phase 6 mounts `frontend/dist/` (the Vite build output, produced by
`cd frontend && npm run build`) at `/` via StaticFiles(html=True), which
serves `index.html` for `/` and hashed assets for everything under
`/assets/*` -- `uvicorn api.main:app` then becomes the one command that
serves both the API and the dashboard UI, matching this project's existing
single-command ethos (`streamlit run app.py`, `focus start`). This is a
single dashboard page, not a multi-route SPA (no React Router in
frontend/src -- confirmed by grep, matching the original plan's "no
routing library needed" call), so a plain static mount is sufficient; no
catch-all history-mode fallback route is needed. The mount is added *after*
all `/api/*` routers are registered below, since StaticFiles would
otherwise shadow them -- FastAPI matches routes in registration order, so
the routers registered first take precedence for `/api/*` paths and the
static mount only ever handles what's left.

Phase 5 adds a `lifespan` background task that calls
focus_session_manager.manager.tick() once a second for as long as the
process is up. This is what guarantees a running session actually
auto-completes (and a paused one auto-fails) on schedule with its Rune
award/notification/DB-log side effects, even if no browser tab happens to
be polling GET /api/focus/state at that exact moment -- the router's own
GET handler also calls tick() inline (see focus.py) for freshness between
this loop's once-a-second ticks, but the two calls serve different
purposes: the router's tick keeps a *polling* client's snapshot fresh,
this loop guarantees the transition fires even with *no* client polling.

2026-08-11 redesign, retired same day: the push-based "Now" nudge
(proactive_scheduler.tick()) was tried in this loop and pulled back out --
the user wants a browsable Notion-style board instead of a one-task-at-a-
time push surface (see procrastination_tool/tasks.py's Board work). The
engine itself has real side effects (desktop notifications, auto-starting
sessions), so it's not enough to just stop calling it from the frontend --
it has to stop ticking here too, or it'd keep firing with no UI to react
to it. `proactive_scheduler.py`/`api/routers/now.py` are left on disk,
unused, same as the other retired modules (Planner/Character/Armory).

Same-day follow-up: the legacy Notion-backed `/api/tasks` router (routers/
tasks.py) AND `/api/planner/*` (routers/planner.py -- its assign/move/
refresh endpoints call notion_cache/sync just as directly) are no longer
registered, now that procrastination_tool/migrate_notion_tasks.py has
pulled every task out of Notion into the native `tasks` table (see
routers/backlog.py, the Board's data source) -- the app no longer talks to
Notion at all. `routers/tasks.py`, `routers/planner.py`, `notion_tasks.py`,
`api/notion_cache.py`, and `sync.py` are left on disk, unused, same
convention as the other retired modules (Planner's frontend was already
unused before this).

Second same-day follow-up: the user chose to run this app independently on
two Macs (this one + a Mac mini) with `data/sessions.db` synced between
them via Syncthing, rather than one machine acting as a shared server --
see README.md's "Running independently on two Macs" section. That means
two processes CAN end up writing to copies of the same file with no shared
lock between them at the OS level, since they never actually run against
the same file at the same instant, only synced-after-the-fact copies of
it. `procrastination_tool.device_lock` guards the one common real mistake
(forgetting to fully quit on one machine before starting on the other) by
checking a hostname+timestamp marker stored inside the DB file itself
before anything else touches it -- see that module's docstring for what it
can and can't catch. `PROCRASTINATION_TOOL_FORCE_UNLOCK=1` overrides it for
one startup, for the "the other machine crashed, I've confirmed it's not
running" case.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from procrastination_tool import device_lock
from procrastination_tool.focus_session_manager import manager as focus_manager

from .routers import backlog, calendar, character, evaluation, focus, gear, now, sessions, tags

# frontend/dist relative to this file (api/main.py -> api/ -> repo root -> frontend/dist)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Raises device_lock.DeviceLockError (aborting startup) if it looks
    # unsafe to proceed -- deliberately BEFORE the tick loop starts, so a
    # locked-out startup never gets the chance to touch the DB at all.
    device_lock.acquire(force=os.environ.get("PROCRASTINATION_TOOL_FORCE_UNLOCK") == "1")

    async def _tick_loop():
        while True:
            await asyncio.to_thread(focus_manager.tick)
            await asyncio.sleep(1)

    task = asyncio.create_task(_tick_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        device_lock.release()


app = FastAPI(title="Procrastination Tool API", lifespan=lifespan)

app.include_router(calendar.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(character.router, prefix="/api")
app.include_router(gear.router, prefix="/api")
app.include_router(focus.router, prefix="/api")
# 2026-08-11 redesign: native task backlog (replaces Notion) -- see
# procrastination_tool/tasks.py. `now` stays registered but inert (see the
# module docstring above -- proactive_scheduler no longer ticks).
app.include_router(backlog.router, prefix="/api")
app.include_router(now.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
# End-of-day evaluation + mood tracker (same-day follow-up).
app.include_router(evaluation.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Registered last so it never shadows an /api/* router above -- see the
# module docstring for why registration order is what makes this safe.
# html=True makes StaticFiles serve dist/index.html for `/` (and for any
# other unmatched path, which is harmless here since there's no client-side
# router to hand those off to).
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
