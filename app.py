"""
Phase 4: a thin Streamlit dashboard over the already-tested Phase 1-2
modules. No logic duplicated with the background automation -- this reads
and writes the exact same data (Notion, Calendar, spin_wheel_config.json,
sessions.db) via the same procrastination_tool package the LaunchAgents
and `focus` CLI use.

Run with: streamlit run app.py
"""
import json
from datetime import datetime, timedelta

import streamlit as st

from procrastination_tool import calendar_bridge, focus_timer, sync
from procrastination_tool.config import FOCUS_CALENDAR_NAME, SPIN_WHEEL_CONFIG_PATH

st.set_page_config(page_title="Procrastination Tool", page_icon="🎯", layout="centered")
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

# --- Manual sync --------------------------------------------------------
st.header("Sync")
st.caption("Runs the same Notion → Calendar sync the 7am automation runs — safe to click "
           "any time, already-blocked tasks are skipped (never duplicated).")
if st.button("Run sync now", type="primary"):
    with st.spinner("Syncing..."):
        try:
            result = sync.run_sync()
        except Exception as e:
            st.error(f"Sync failed: {e}")
        else:
            st.success(
                f"{len(result.created)} created, {len(result.already_blocked)} already blocked, "
                f"{len(result.unscheduled)} unscheduled, {result.removed_count} completed task block(s) removed"
            )
            for p in result.created:
                st.write(f"- {p.start.strftime('%a %H:%M')}–{p.end.strftime('%H:%M')}  {p.task.name}")
            if result.unscheduled:
                st.warning("Couldn't fit into the scheduling horizon: "
                           + ", ".join(t.name for t in result.unscheduled))
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
        reward = f"  →  {s.wheel_result}" if s.wheel_result else ""
        st.write(f"{status} {s.start_time.strftime('%Y-%m-%d %H:%M')}  ({s.actual_minutes:.0f}min){label}{reward}")

# --- Spin wheel config editor -------------------------------------------
st.header("Spin wheel items")
st.caption("Suggestion-only, remember — this never contacts anyone on your behalf, "
           "even for items like \"call a friend.\"")

with open(SPIN_WHEEL_CONFIG_PATH) as f:
    wheel_config = json.load(f)
items = wheel_config.get("items", [])


def _save_items(new_items):
    wheel_config["items"] = new_items
    with open(SPIN_WHEEL_CONFIG_PATH, "w") as f:
        json.dump(wheel_config, f, indent=2)


for i, item in enumerate(items):
    col1, col2 = st.columns([5, 1])
    col1.write(item)
    if col2.button("Remove", key=f"del_{i}"):
        _save_items(items[:i] + items[i + 1:])
        st.rerun()

# clear_on_submit resets the text field after adding -- without a form,
# the input's value would persist across the rerun and silently get
# re-added a second time.
with st.form("add_wheel_item", clear_on_submit=True):
    new_item = st.text_input("Add a new item", placeholder="e.g. Do 20 minutes of yoga")
    if st.form_submit_button("Add item") and new_item.strip():
        _save_items(items + [new_item.strip()])
        st.rerun()
