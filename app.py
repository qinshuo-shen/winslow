"""
Phase 4: a thin Streamlit dashboard over the already-tested Phase 1-2
modules. No logic duplicated with the background automation -- this reads
and writes the exact same data (Notion, Calendar, spin_wheel_config.json,
sessions.db) via the same procrastination_tool package the LaunchAgents
and `focus` CLI use.

Superseded by the web dashboard (`api/` + `frontend/`, Phase 6) as of
2026-08-07 -- left on disk, disconnected from the new UI, same fallback
precedent as scheduler.py/sync.py's old auto-scheduler (see
block_grid.py's docstring) and spin_wheel.py.

Run with: streamlit run app.py
"""
from datetime import date, datetime, time, timedelta

import streamlit as st
from streamlit_sortables import sort_items

from procrastination_tool import block_grid, calendar_bridge, character, focus_timer, gear, notion_tasks, questlines, sync
from procrastination_tool.bloodstain import get_active_bloodstain
from procrastination_tool.config import (
    BLOCK_BREAK_MINUTES,
    BLOCK_WORK_MINUTES,
    BUSY_CALENDARS,
    CHARACTER_STATS,
    FOCUS_CALENDAR_NAME,
    stat_level_cost,
)

# Bumped whenever a drag/button interaction changes local grid state, and
# folded into every sortable widget's `key` (see "Plan your week" below) to
# force it to remount with freshly recomputed state. Community bidirectional
# components like streamlit-sortables generally only honor their `items`
# argument on first mount for a given key -- after that, the frontend keeps
# showing its own last-arranged state regardless of what Python re-passes,
# so a same-key rerun after some OTHER tab's edit would otherwise show a
# stale layout. Only bumping on confirmed edits (not every rerun) means an
# unrelated interaction elsewhere on the page doesn't reset an in-progress
# drag in a tab the user isn't touching.
st.session_state.setdefault("grid_generation", 0)

# A muted, theme-neutral hover color for sortable-grid boxes -- overrides
# streamlit-sortables' shipped default (`.sortable-item:hover { background:
# var(--primary-color) }`), which resolves to Streamlit's strong red/coral
# theme accent and reads as jarring, especially in dark mode. One constant,
# trivially retunable.
_GRID_CUSTOM_STYLE = """
.sortable-item:hover {
    background-color: #5b7a9d;
    color: #fff;
}
"""

st.set_page_config(page_title="Sheni's Procrastination Tool", page_icon="🎯", layout="centered")
st.title("🎯 Procrastination Tool")
st.caption(datetime.now().strftime("%A, %B %d, %Y"))

# --- Today's schedule -------------------------------------------------
st.header("Today's schedule")
try:
    todays_events = sorted(calendar_bridge.list_events(datetime.now()), key=lambda e: e.start)
except Exception as e:
    st.error(f"Couldn't read the {FOCUS_CALENDAR_NAME} calendar: {e}")
    todays_events = []

if todays_events:
    for ev in todays_events:
        st.markdown(f"**{ev.start.strftime('%H:%M')}–{ev.end.strftime('%H:%M')}**  {ev.summary}")
else:
    st.info("No blocks scheduled for today yet.")

# --- Plan your week (manual drag-and-drop grid, replaces the old automatic
# sync -- scheduler.py/sync.py's automatic scheduling stays on disk,
# disconnected, same precedent as spin_wheel.py from the RPG redesign) -----
#
# Local-first editing model (fixes "every drag is slow"): Calendar.app is
# only ever read ONCE per browser session (cached in st.session_state, not
# re-fetched on every script rerun -- Streamlit reruns the *whole* script on
# *any* widget interaction anywhere on the page, not just grid drags, so an
# unguarded fetch here was the real source of the slowness). Drags mutate
# only local session-state (pending_creates / pending_delete_uids) -- zero
# AppleScript calls. The Submit button, top-right of the header, is the only
# thing that actually writes to Calendar.app, in one batch.


@st.cache_data(ttl=120)
def _fetch_actionable_tasks_cached():
    return notion_tasks.fetch_actionable_tasks()


if "calendar_snapshot" not in st.session_state:
    st.session_state["calendar_snapshot"] = calendar_bridge.list_all_events()
st.session_state.setdefault("pending_creates", [])
st.session_state.setdefault("pending_delete_uids", set())
st.session_state.setdefault("pending_create_counter", 0)
extra_instances = st.session_state.setdefault("extra_task_instances", {})
busy_cache = st.session_state.setdefault("busy_conflict_cache", {})

n_pending = len(st.session_state["pending_creates"]) + len(st.session_state["pending_delete_uids"])

col_title, col_submit = st.columns([4, 1])
col_title.header("🗓️ Plan your week")
with col_submit:
    st.write("")  # vertical nudge so the button roughly aligns with the header text
    if st.button(f"✅ Submit ({n_pending})" if n_pending else "✅ Submit",
                 disabled=n_pending == 0, type="primary"):
        with st.spinner(f"Syncing {n_pending} change(s) to Calendar.app..."):
            for pc in st.session_state["pending_creates"]:
                calendar_bridge.create_event(pc["task_name"], pc["row_start"], pc["row_end"], notes=pc["notes"])
            for uid in st.session_state["pending_delete_uids"]:
                calendar_bridge.delete_event_by_uid(uid)
            st.session_state["calendar_snapshot"] = calendar_bridge.list_all_events()
            st.session_state["pending_creates"] = []
            st.session_state["pending_delete_uids"] = set()
        st.session_state["grid_generation"] += 1
        st.rerun()

st.caption(
    f"Drag task boxes onto the {BLOCK_WORK_MINUTES}-min blocks you want them in. A "
    f"{BLOCK_BREAK_MINUTES}-min break is implicit right after any filled block — it's "
    "never its own event, just time nothing else gets scheduled into. Nothing reaches "
    "your calendar until you hit Submit."
)

all_tasks = _fetch_actionable_tasks_cached()
tasks_by_id = {t.page_id: t for t in all_tasks}

refresh_caption = "🔄 Refresh (Notion + Calendar)"
if n_pending:
    st.caption(f"⚠️ Refreshing will discard {n_pending} unsubmitted change(s).")
if st.button(refresh_caption):
    with st.spinner("Refreshing..."):
        sync._reconcile_calendar_with_notion(lambda msg: None)
        st.session_state["calendar_snapshot"] = calendar_bridge.list_all_events()
        st.session_state["pending_creates"] = []
        st.session_state["pending_delete_uids"] = set()
        _fetch_actionable_tasks_cached.clear()
    st.session_state["grid_generation"] += 1
    st.rerun()

with st.expander(f"All actionable tasks ({len(all_tasks)})"):
    if not all_tasks:
        st.caption("Nothing actionable in Notion right now.")
    for t in all_tasks:
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{t.name}** — {t.priority or 'No priority'} — starts {t.start_date.isoformat()}")
        if col2.button("✓ Done", key=f"done_{t.page_id}"):
            notion_tasks.mark_task_completed(t.page_id)
            # Done is a deliberate, rare click -- not the repeated-drag path
            # the slowness complaint was about -- so it's fine (and avoids a
            # stale block lingering until the next Submit) to clean up
            # Calendar.app for this task immediately rather than deferring.
            st.session_state["pending_creates"] = [
                pc for pc in st.session_state["pending_creates"] if pc["page_id"] != t.page_id
            ]
            for ev in st.session_state["calendar_snapshot"]:
                if block_grid.parse_notion_id(ev.notes) == t.page_id:
                    calendar_bridge.delete_event_by_uid(ev.uid)
            st.session_state["calendar_snapshot"] = [
                ev for ev in st.session_state["calendar_snapshot"]
                if block_grid.parse_notion_id(ev.notes) != t.page_id
            ]
            _fetch_actionable_tasks_cached.clear()
            st.session_state["grid_generation"] += 1
            st.rerun()

if all_tasks:
    st.caption("Need a task in more than one block? Add another copy of its box:")
    plus_cols = st.columns(min(4, len(all_tasks)))
    for i, t in enumerate(all_tasks):
        if plus_cols[i % len(plus_cols)].button(f"+1 {t.name[:24]}", key=f"plus1_{t.page_id}"):
            extra_instances[t.page_id] = extra_instances.get(t.page_id, 0) + 1
            # The grid's sort_items() call only re-seeds its displayed items
            # on first mount for a given `key` -- without bumping
            # grid_generation (which is folded into that key), the widget
            # wouldn't remount and the new pool box wouldn't actually show
            # up, even though pool_items is correctly recomputed below.
            st.session_state["grid_generation"] += 1
            st.rerun()


def _working_events():
    """Full local working set: real committed events minus pending deletes,
    plus synthetic events for pending (unsubmitted) creates -- what
    Calendar.app *will* look like after Submit, computed with zero I/O."""
    events = [
        ev for ev in st.session_state["calendar_snapshot"]
        if ev.uid not in st.session_state["pending_delete_uids"]
    ]
    for pc in st.session_state["pending_creates"]:
        events.append(calendar_bridge.CalendarEvent(
            uid=f"pending:{pc['id']}", summary=pc["task_name"],
            start=pc["row_start"], end=pc["row_end"], notes=pc["notes"],
        ))
    return events


def _unique_label(name: str, seen: dict) -> str:
    """Labels must be unique within one sort_items() call (the library
    round-trips plain strings, not objects) -- but only add a disambiguator
    when a real collision happens (e.g. the same task placed in two blocks
    the same day via "+1"), so the common case stays a plain task name."""
    seen[name] = seen.get(name, 0) + 1
    n = seen[name]
    return name if n == 1 else f"{name} ({n})"


today = date.today()
week_end = notion_tasks.get_week_end(today)
day_range = [today + timedelta(days=i) for i in range((week_end - today).days + 1)]
full_assigned_counts = block_grid.count_assigned_instances(_working_events())

# One day at a time, not st.tabs(): Streamlit renders every st.tabs() body in
# the same script run regardless of which tab is visually selected (there's
# no API to ask "which tab is active"), so a day-tabs version of this mounted
# up to 8 streamlit-sortables components simultaneously on every mutation --
# the actual trigger for a real "Maximum update depth exceeded" (React error
# #185) crash on Refresh. st.radio reports the selection back to Python, so
# only ever one sortable component exists per render.
selected_day = st.radio(
    "Day", day_range, format_func=lambda d: d.strftime("%a %m/%d"),
    horizontal=True, label_visibility="collapsed",
)

cache_key = selected_day.isoformat()
col_a, col_b = st.columns([1, 3])
if col_a.button("🔍 Check conflicts", key=f"conflicts_{cache_key}"):
    with st.spinner("Checking busy calendars (can take up to ~30s)..."):
        busy_cache[cache_key] = calendar_bridge.list_busy_events(
            datetime.combine(selected_day, time.min), BUSY_CALENDARS
        )
    # Busy rows are removed from `containers` entirely (see below) -- same
    # remount requirement as the +1 button above.
    st.session_state["grid_generation"] += 1
    st.rerun()
busy_intervals = busy_cache.get(cache_key)
col_b.caption(
    f"Conflict-checked ({len(busy_intervals)} busy event(s))." if busy_intervals is not None
    else "Conflicts not checked yet for this day."
)

day_events = [ev for ev in _working_events() if ev.start.date() == selected_day]
row_states = block_grid.get_row_states(selected_day, assigned_events=day_events, busy_intervals=busy_intervals)
if not row_states:
    st.info("Not a working day.")
else:
    seen_labels = {}
    identity_by_label = {}  # label -> ("pool" | "assigned", page_id, uid_or_None)

    pool_items = []
    for t in all_tasks:
        if t.start_date > selected_day:
            continue  # hasn't started yet as of the day being planned -- not draggable
        available = 1 + extra_instances.get(t.page_id, 0) - full_assigned_counts.get(t.page_id, 0)
        for _ in range(max(0, available)):
            label = _unique_label(t.name, seen_labels)
            identity_by_label[label] = ("pool", t.page_id, None)
            pool_items.append(label)
    containers = [{"header": "Task pool", "items": pool_items}]

    row_by_label = {}
    for rs in row_states:
        row_label = f"{rs.row.start.strftime('%H:%M')}–{rs.row.work_end.strftime('%H:%M')}"
        if rs.status == "busy":
            st.caption(f"🔒 {row_label} — busy ({rs.busy_summary})")
            continue
        items = []
        if rs.status == "assigned" and rs.event is not None:
            page_id = block_grid.parse_notion_id(rs.event.notes) or ""
            label = _unique_label(rs.event.summary, seen_labels)
            identity_by_label[label] = ("assigned", page_id, rs.event.uid)
            items = [label]
        containers.append({"header": row_label, "items": items})
        row_by_label[row_label] = rs

    result = sort_items(
        containers, multi_containers=True, direction="vertical",
        custom_style=_GRID_CUSTOM_STYLE,
        key=f"grid_{cache_key}_{st.session_state['grid_generation']}",
    )

    seed_map = {item: c["header"] for c in containers for item in c["items"]}
    result_map = {item: c["header"] for c in result for item in c["items"]}
    moved = [item for item in result_map if seed_map.get(item) != result_map.get(item)]

    conflict = False
    for c in result:
        if c["header"] != "Task pool" and len(c["items"]) > 1:
            conflict = True
            st.warning(f"{c['header']} has more than one task — drop rejected.")

    if moved and not conflict:
        changed = False
        for item in moved:
            identity = identity_by_label.get(item)
            if identity is None:
                continue
            kind, page_id, uid = identity
            from_header, to_header = seed_map.get(item), result_map.get(item)
            task = tasks_by_id.get(page_id)

            if kind == "assigned":
                if uid.startswith("pending:"):
                    local_id = uid.split(":", 1)[1]
                    st.session_state["pending_creates"] = [
                        pc for pc in st.session_state["pending_creates"] if str(pc["id"]) != local_id
                    ]
                else:
                    st.session_state["pending_delete_uids"].add(uid)
                changed = True

            if to_header != "Task pool" and task:
                target_state = row_by_label.get(to_header)
                if target_state:
                    new_id = st.session_state["pending_create_counter"]
                    st.session_state["pending_create_counter"] += 1
                    st.session_state["pending_creates"].append({
                        "id": new_id, "page_id": task.page_id, "task_name": task.name,
                        "notes": sync._build_notes(task), "day": selected_day,
                        "row_start": target_state.row.start, "row_end": target_state.row.work_end,
                    })
                    changed = True

        if changed:
            st.session_state["grid_generation"] += 1
            st.rerun()

# --- Focus session stats -------------------------------------------------
st.header("Focus sessions")
sessions = focus_timer.get_recent_sessions(limit=50)

if not sessions:
    st.info("No focus sessions logged yet — run `focus start` from Terminal.")
else:
    week_ago = datetime.now() - timedelta(days=7)
    week_sessions = [s for s in sessions if s.start_time >= week_ago]
    completed_week = [s for s in week_sessions if s.completed]

    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions (7d)", len(week_sessions))
    c1_rate = f"{100 * len(completed_week) / len(week_sessions):.0f}%" if week_sessions else "—"
    c2.metric("Completion rate (7d)", c1_rate)
    total_minutes = sum(s.actual_minutes for s in completed_week)
    c3.metric("Focused time (7d)", f"{total_minutes:.0f} min ({total_minutes / 60:.1f} h)")

    # Daily focused minutes, last 7 days -- single series, one hue is the
    # right choice here (see dataviz skill: no legend/palette needed for
    # one series), Streamlit's built-in bar chart handles this cleanly.
    daily_minutes = {}
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).date()
        daily_minutes[day.strftime("%a %d")] = 0.0
    for s in completed_week:
        key = s.start_time.date().strftime("%a %d")
        if key in daily_minutes:
            daily_minutes[key] += s.actual_minutes
    st.bar_chart(daily_minutes)

    st.subheader("Recent sessions")
    for s in sessions[:10]:
        if getattr(s, "outcome", None) == focus_timer.OUTCOME_FAILED_PAUSE_TIMEOUT:
            status = "⏰"  # paused too long, auto-failed
        elif s.completed:
            status = "✅"
        else:
            status = "⏹️"  # manually stopped early (Ctrl-C)
        label = f" — {s.task_label}" if s.task_label else ""
        reward = f"  →  +{s.runes_awarded} Runes" if s.runes_awarded else ""
        st.write(f"{status} {s.start_time.strftime('%Y-%m-%d %H:%M')}  ({s.actual_minutes:.0f}min){label}{reward}")

# --- Character -----------------------------------------------------------
st.header("⚔️ Character")
c = character.get_character()
st.metric("Level", c.level, help="Sum of all stat levels.")
st.metric("Runes", c.runes)

stain = get_active_bloodstain()
if stain:
    st.warning(f"🩸 Active bloodstain: {stain.runes} Runes waiting to be recovered "
               "by your next completed focus session.")

st.caption("Bonfire leveling — Runes only convert to a permanent stat level when you "
           "deliberately rest, never automatically.")
stat_cols = st.columns(len(CHARACTER_STATS))
for col, stat_name in zip(stat_cols, CHARACTER_STATS):
    level = c.stats.get(stat_name, 0)
    cost = stat_level_cost(level)
    with col:
        st.write(f"**{stat_name}**")
        st.write(f"lvl {level}")
        if st.button(f"Rest ({cost} Runes)", key=f"rest_{stat_name}", disabled=c.runes < cost):
            character.spend_runes_on_stat(stat_name)
            st.rerun()

active_questlines = questlines.list_active_questlines()
if active_questlines:
    st.subheader("Questlines")
    for q in active_questlines:
        st.write(f"📜 **{q['project_name']}** — {q['session_count']} sessions "
                 f"({q['milestones_paid']} milestone(s) claimed)")

# --- Armory ----------------------------------------------------------------
st.header("🛡️ Armory")
owned = set(gear.list_owned_gear())
for item in gear.load_gear_catalog():
    col1, col2 = st.columns([5, 1])
    owned_flag = " ✅ owned" if item.gear_id in owned else ""
    col1.markdown(f"**{item.name}** (lvl {item.min_level}, {item.cost} Runes){owned_flag}")
    col1.caption(item.flavor_text)
    can_buy = (item.gear_id not in owned) and c.level >= item.min_level and c.runes >= item.cost
    if col2.button("Buy", key=f"buy_{item.gear_id}", disabled=not can_buy):
        gear.purchase_gear(item.gear_id)
        st.rerun()
