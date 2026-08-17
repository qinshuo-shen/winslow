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
single-command ethos (`streamlit run app.py`, `focus start`). The mount is
added *after* all `/api/*` routers are registered below, since StaticFiles
would otherwise shadow them -- FastAPI matches routes in registration
order, so the routers registered first take precedence for `/api/*` paths
and the static mount only ever handles what's left.

2026-08 page-split redesign: the frontend gained React Router (Tasks/
Projects/Focus/Evaluation each a real bookmarkable route) -- no longer true
that this is "a single dashboard page, not a multi-route SPA." That broke
StaticFiles(html=True)'s fallback: it only serves index.html for a path
resolving to an existing *directory* on disk, not for an arbitrary client
route (verified directly against Starlette's staticfiles.py), so a hard
refresh on e.g. `/projects` in production would 404 with no client-side
router able to catch it. SPA_ROUTES below registers each of those paths as
an explicit small route returning index.html -- placed *before* the
StaticFiles mount for the same registration-order reason as the /api/*
routers (a mount at "/" would otherwise shadow anything registered after
it).

Phase 5 adds a `lifespan` background task that calls
focus_session_manager.manager.tick() once a second for as long as the
process is up. This is what guarantees a running session actually
auto-completes (and a paused one auto-fails) on schedule with its
notification/DB-log side effects, even if no browser tab happens to
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

Third same-day follow-up: `character`/`gear` (the RPG Runes/stats/gear
system) are no longer registered -- the user doesn't want gamification.
Focus sessions no longer award Runes (see focus_timer.finalize_session()).
`routers/character.py`, `routers/gear.py`, and the underlying
`procrastination_tool/character.py`/`bloodstain.py`/`questlines.py`/
`gear.py` are left on disk, unused, same convention as this project's
other retired modules.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from procrastination_tool import device_lock
from procrastination_tool.focus_session_manager import manager as focus_manager

from .routers import (
    backlog, calendar, evaluation, focus, now, projects, push,
    retro, sessions, standup, tags,
)

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
app.include_router(focus.router, prefix="/api")
# 2026-08-11 redesign: native task backlog (replaces Notion) -- see
# procrastination_tool/tasks.py. `now` stays registered but inert (see the
# module docstring above -- proactive_scheduler no longer ticks).
app.include_router(backlog.router, prefix="/api")
app.include_router(now.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
# End-of-day evaluation + mood tracker (same-day follow-up).
app.include_router(evaluation.router, prefix="/api")
# Scrum-lite: weekly retro (sprint/velocity feature set).
app.include_router(retro.router, prefix="/api")
# Scrum-lite: AI PM-agent (suggest-only backlog review) -- no longer
# registered, its job absorbed into the standup Q&A box (see standup.py's
# module docstring). procrastination_tool/pm_agent.py and
# api/routers/pm_agent.py are left on disk, unused, same convention as
# this project's other retired modules (spin_wheel.py, character.py).
# Web Push notifications for the focus timer.
app.include_router(push.router, prefix="/api")
# Scrum-lite: virtual daily standup (forward-looking, on-demand note).
app.include_router(standup.router, prefix="/api")
# 2026-08 page-split redesign: Project tracking -- see procrastination_tool/projects.py.
app.include_router(projects.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# 2026-08 page-split redesign: explicit SPA-fallback routes, one per React
# Router path, each just serving the built index.html so the client-side
# router can take over from there -- see the module docstring above for why
# StaticFiles(html=True) alone can't cover this. Must be registered before
# the StaticFiles mount below (same registration-order reasoning as the
# /api/* routers above).
SPA_ROUTES = ["/tasks", "/projects", "/focus", "/evaluation"]
if FRONTEND_DIST.is_dir():
    for _path in SPA_ROUTES:
        app.add_api_route(
            _path,
            lambda: FileResponse(FRONTEND_DIST / "index.html"),
            methods=["GET"],
            include_in_schema=False,
        )

# Registered last so it never shadows an /api/* router or an SPA-fallback
# route above -- see the module docstring for why registration order is
# what makes this safe. html=True makes StaticFiles serve dist/index.html
# for `/` itself and for any directory-shaped path; the explicit routes
# above cover the non-directory client routes StaticFiles can't.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
