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
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from procrastination_tool.focus_session_manager import manager as focus_manager

from .routers import calendar, character, focus, gear, planner, sessions, tasks

# frontend/dist relative to this file (api/main.py -> api/ -> repo root -> frontend/dist)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
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


app = FastAPI(title="Procrastination Tool API", lifespan=lifespan)

app.include_router(tasks.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(character.router, prefix="/api")
app.include_router(gear.router, prefix="/api")
app.include_router(focus.router, prefix="/api")


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
