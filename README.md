# procrastination-tool

Personal automation: Notion tasks → macOS Calendar sync, a Pomodoro-style focus
timer, and a "spin wheel" reward mechanic. Built in phases — see
`~/.claude/plans/functional-shimmying-rain.md` (or the Obsidian wiki page
`projects/procrastination-tool/synthesis/phased-plan-and-punishment-redesign.md`)
for the full plan and reasoning.

## Status: All 4 phases resolved — daily sync, focus timer, and a dashboard are all live

Run `streamlit run app.py` (or `.venv/bin/streamlit run app.py`) for the dashboard: today's schedule, a manual sync button, focus session stats with a 7-day chart, and a spin-wheel item editor — all reading/writing the exact same data the background automation and `focus` CLI use, no separate logic. See "What Phase 4 proved" below.

## Phase 3: how it actually resolved (2026-08-02)

**Gmail: skipped by explicit user decision.** The rent-detection OAuth flow was built (`gmail_client.py`, `email_tasks.py`, etc.) up through a working `pages.create` test, then the user realized rent was the only concrete Gmail use case and manual entry is simpler than maintaining Google Cloud OAuth credentials + a 7-day token refresh cadence for one recurring task. **All of that code was removed**, not left disabled — per this project's own principle of not leaving half-finished/unused features around. If a real need comes back, the design (and the working `parent: {"type": "data_source_id", ...}` page-creation call) is documented in the plan file and wiki.

**Outlook: technically works, but built as an on-demand interactive pattern, not a background script.** The Mail.app AppleScript spike succeeded once the user enabled Mail sync for the "Exchange" account in System Settings (it was Calendar-only before) — reading subject/sender/date/body from the real inbox is fast (~150ms/message) and reliable. But when asked what pattern should auto-generate tasks, the user's actual answer was "read my emails and use judgment" — which is a real judgment call, not a mechanical filter, and isn't something to run unattended: a scan during testing turned up sensitive personal correspondence sitting in the same inbox as work mail, which is a concrete reason not to pipe unfiltered inbox content through an unsupervised LLM-based pipeline that creates real, visible Notion tasks with no review step. **Resolution**: no automated script was built for this. Instead, reviewing the inbox for actionable items is now an on-demand thing done interactively in a Claude Code session — Claude reads recent messages, proposes candidates, the user picks which become tasks, nothing gets created without that review step. First real run of this pattern (same session) surfaced 4 candidates from 40 recent messages; investigating them further downgraded one (a to-do thread that turned out to already be resolved once the full thread was read, not just the subject line) and confirmed two with real due dates pulled from the actual email bodies (a finance/admin reminder and an access-renewal notice with a specific expiration date) — both created as real Notion tasks, correctly picked up by the existing Phase 1 sync pipeline with no extra code needed.

Real Notion tasks are being scheduled into the "Focus Blocks" calendar automatically every
morning at 7:00am, and `focus start` runs a real Pomodoro-style session with a spin-wheel
reward on completion. See "What Phase 1 proved" below for how it works and the design decisions
baked into it (priority ordering, working hours, idempotency).

## Project location

**Deliberately lives at `~/Developer/procrastination-tool`, not under iCloud Drive.**
Confirmed empirically during Phase 0: `launchd`-spawned background processes get
`Operation not permitted` on any path under `~/Library/Mobile Documents/com~apple~CloudDocs/...`
(iCloud Drive) — even a plain `ls` fails. This is a broader, harder-to-grant
restriction than the Calendar/Notification TCC prompts (which do have a normal
grantable dialog); iCloud Drive access has no equivalent dialog for a headless
process to be granted through. If you ever want this project synced/backed up,
sync `~/Developer/procrastination-tool` some other way (e.g. a git remote) rather
than moving it back under iCloud Drive.

## Running independently on two Macs, data synced via Syncthing (current setup)

**2026-08-11, chosen over the shared-server option below.** Each Mac (this laptop + a Mac mini) runs its own full instance of the app — its own `uvicorn`/CLI, its own Calendar.app automation, its own desktop notifications, all correct for whichever machine you're actually sitting at — and `data/sessions.db` is kept in sync between them by [Syncthing](https://syncthing.net) (not iCloud Drive: this project's own history already has iCloud Drive silently reverting a different file to an older version with no warning at all, a worse failure mode for a database file specifically than for most documents).

**The one hard rule this depends on: only run the app on one machine at a time.** Fully quit it on machine A (Ctrl-C the server/CLI, or `launchctl bootout` if it's installed as a LaunchAgent), let Syncthing finish syncing, *then* start it on machine B. Two live instances writing to their own not-yet-synced copies of the same SQLite file at once is a real corruption/data-loss risk that Syncthing's own conflict handling won't cleanly resolve for a binary database file the way it can for a text document.

**Built-in safety net**: `procrastination_tool/device_lock.py` stores a `hostname` + `is_running` marker *inside* `data/sessions.db` itself (so it travels with the file, not as a separate thing that could itself race out of sync). Both the web server (`api/main.py`'s startup) and the `focus` CLI check it before touching anything else, and refuse to start with a clear error if it looks like the other machine's last session is still open:

```
Refusing to start: data/sessions.db was last opened by 'mac-mini.local' at
2026-08-11T09:14:02 and was never marked closed cleanly. If 'mac-mini.local'
is still running this app, stop it there first, wait for the sync to
finish, then start here. If it crashed or was force-quit and you're SURE
it isn't running, set PROCRASTINATION_TOOL_FORCE_UNLOCK=1 to override once.
```

This only catches "forgot to quit on the other machine first" — it can't detect whether Syncthing has actually *finished* syncing yet, so still pause a few seconds after quitting on one machine before starting on the other, especially over a slow/relay connection.

Setup, on each Mac:

```bash
cd ~/Developer/procrastination-tool          # same non-iCloud-Drive location, see above; must
                                              # match on both machines for launchd plists to work
python3 -m venv .venv
./.venv/bin/pip install -e ".[api]"
cd frontend && npm install && npm run build && cd ..
cp .env.example .env    # fill in real values -- same NOTION_TOKEN (only needed if you ever
                         # re-run migrate_notion_tasks.py)/FOCUS_CALENDAR_NAME/EXCHANGE_CALENDAR_NAME
                         # on both machines. Calendar.app needs the same iCloud/Exchange accounts
                         # added on both Macs (System Settings -> Internet Accounts) so calendar
                         # names resolve to the same real calendars either machine writes to.
```

Then install Syncthing on both Macs (`brew install syncthing` or the signed .app from syncthing.net) and add `~/Developer/procrastination-tool/data/` as a synced folder between them — **only that `data/` directory**, not the whole repo (code changes should go through git, not file sync, same as any other project). Use Syncthing's own folder-versioning option (keeps old versions on conflict instead of silently overwriting) rather than its default, given what's riding on this one file.

Run with `.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000` (no need for `--host 0.0.0.0` here, unlike the shared-server option below — you're always accessing this machine's own instance locally) whenever you're actively using that machine, and make sure to stop it (Ctrl-C, or `launchctl bootout` if using a LaunchAgent) before switching to the other one.

## Alternative: running as a persistent server (e.g. on a Mac mini, for access from another Mac)

Kept here as a documented alternative, not the current setup — see above for why independent-and-synced was chosen instead. This approach avoids the single-active-writer discipline entirely (one shared database, no sync race possible) at the cost of Calendar-blocking/notifications only ever firing on the server machine, regardless of which device you're actually using.

`api/main.py` already serves the built frontend itself (`frontend/dist/`, via `StaticFiles`) alongside the API from the same FastAPI process and same origin, so there's no CORS configuration needed — a browser on another device just points at the server machine's address and gets both the UI and the API from one port.

Setup, on whichever Mac will be the server (a Mac mini is a natural fit — normally on, rarely closed/asleep like a laptop):

```bash
cd ~/Developer/procrastination-tool          # same non-iCloud-Drive location, see above
python3 -m venv .venv
./.venv/bin/pip install -e ".[api]"
cd frontend && npm install && npm run build && cd ..

cp .env.example .env    # then fill in real values -- FOCUS_CALENDAR_NAME, EXCHANGE_CALENDAR_NAME,
                         # BUSY_CALENDARS, etc. Calendar.app on THIS machine needs the same
                         # iCloud/Exchange accounts added (System Settings -> Internet Accounts)
                         # for calendar names to match and for calendar-bridge writes to reach
                         # the same calendars you see on your other Mac.

cp launchd/com.qinshuoshen.procrastination-tool.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.server.plist
```

- **First run needs a logged-in GUI session, not just SSH.** Calendar/Notification permission dialogs (macOS TCC) can only be approved by clicking through them once, interactively — the same one-time-dialog behavior documented in "What Phase 0 proved" below. `launchctl kickstart -k gui/$(id -u) com.qinshuoshen.procrastination-tool.server` after logging in triggers this.
- **Copy your real `data/sessions.db` over once** (it's gitignored, so `git clone`/`git pull` won't bring it) — from that point on, the server machine's copy is the single source of truth; don't keep running the app locally on your other Mac against its own separate copy.
- **Prevent the server Mac from sleeping** (System Settings → Energy → uncheck "Put hard disks/display to sleep" or equivalent) — `KeepAlive` in the plist relaunches a crashed process, but can't wake a sleeping machine.
- **Reach it from another device**: `http://<server-hostname>.local:8000` on the same network (find the hostname via `scutil --get LocalHostName` on the server Mac), or its LAN IP directly. For access away from home, put it behind a VPN like Tailscale rather than exposing port 8000 to the public internet — this app has no authentication layer.
- To reload after editing the plist: `launchctl bootout gui/$(id -u)/com.qinshuoshen.procrastination-tool.server 2>/dev/null` then re-run the `bootstrap` line above.

## Setup

```bash
cd ~/Developer/procrastination-tool
python3 -m venv .venv
./.venv/bin/pip install -e .
./.venv/bin/pip install notion-client   # Phase 1+; already installed if you're reading this post-Phase-0
cp .env.example .env
# edit .env yourself in a text editor -- see "Notion setup" below
```

## Notion setup (needed to finish Phase 0 — you have to do this part yourself)

1. Go to <https://www.notion.so/my-integrations>, click **New integration**.
2. Name it (e.g. "Procrastination Tool"), associate it with your workspace, create it.
3. Copy the **Internal Integration Token** (starts with `secret_` or `ntn_`).
4. Open your Notion tasks database → **`...`** menu (top right) → **Connections** → add the integration you just created. **This step is easy to miss and causes every API call to 404 as if the database doesn't exist**, not a clear permissions error.
5. Get the database ID: open the database as a full page, copy the URL — the ID is the 32-character string right after your workspace name and before the `?v=`, e.g. `notion.so/myworkspace/`**`a1b2c3d4e5f6...`**`?v=...`.
6. Edit `.env` (not `.env.example`) yourself and fill in `NOTION_TOKEN` and `NOTION_DATABASE_ID`. Don't paste the token into a chat/conversation — it's a real secret.

## Running the Phase 0 smoke test

Manually (first time, to trigger/approve permission dialogs — **watch your screen**, a system dialog needs a manual click that can't be automated):

```bash
./.venv/bin/python3 scripts/smoke_test.py
```

Non-interactively via the LaunchAgent (the real test — proves it'll work unattended every morning in later phases):

```bash
launchctl kickstart -k gui/501/com.qinshuoshen.procrastination-tool.smoketest
sleep 3 && tail -10 logs/smoke_test.log
```

The LaunchAgent plist is installed at `~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.smoketest.plist`
(source copy in `launchd/`). It has **no automatic schedule on purpose** — Phase 0 only needs to prove
permissions survive a non-interactive run; Phase 1 will add a real morning `StartCalendarInterval`
to a production sync agent (probably a renamed/new plist, not this smoketest one).

To reload after editing the plist:
```bash
launchctl bootout gui/501/com.qinshuoshen.procrastination-tool.smoketest 2>/dev/null
cp launchd/com.qinshuoshen.procrastination-tool.smoketest.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.smoketest.plist
```

## What Phase 0 proved

- macOS Calendar read/write via AppleScript (`osascript`), not PyObjC/EventKit — see `procrastination_tool/calendar_bridge.py`.
  - **Gotcha found**: property access on Calendar event objects (`start date of e`, `uid of e`, etc.) must stay *inside* the `tell application "Calendar"` block. Accessing it after the block closes causes a confusing `Expected end of line but found class name` error during the ISO-date coercion — not what the error message suggests.
- All writes go to a dedicated local **"Focus Blocks"** calendar (auto-created), not the Outlook-synced one — still merges into one Calendar.app view.
- `launchd` LaunchAgent (not `cron`) is required for the permission grant to carry over to non-interactive runs. **First kickstart after granting still showed one more permission dialog** (a different process identity than the interactive grant) — approve it once, and subsequent kickstarts are prompt-free.
- Notifications via `osascript display notification` work but the exit code doesn't prove the notification was actually seen — verify visually.
- **iCloud Drive paths are broadly inaccessible to `launchd`** (see "Project location" above) — this was the single biggest surprise, bigger than the anticipated Calendar-permission risk.

## What Phase 1 proved

- Notion is on the newer **"data sources" API model** — a database no longer carries `properties`/rows directly; you retrieve `databases.retrieve(...)["data_sources"][0]["id"]` first, then use `client.data_sources.query(...)`/`retrieve(...)` with that ID. `notion_client_wrapper.py` and `notion_tasks.py` both do this.
- Real schema confirmed against the live database (not assumed): `Name` (title), `Priority` (select, 4 Eisenhower-style categories — not a simple rank), `Block`, `Specific Project`, `Date` (= deadline), `Completed` (select: Not Started/In-Progress/On hold/Completed/Discarded), `Notes`. No "Estimated Duration" property exists yet.
- **Follow-up fix, same day, after the first live run surfaced two real problems**:
  1. Tasks with **no Priority set** are the user's long-term projects (e.g. an ongoing research project, a personal side project) — not meant to be chunked into a single daily block. `notion_tasks.fetch_actionable_tasks()` now filters these out entirely (`{"property": "Priority", "select": {"is_not_empty": True}}`) rather than scheduling them like everything else.
  2. A flat 60-minute block for every task was unrealistic. Duration is now derived from Priority via `notion_tasks.PRIORITY_DURATION_MINUTES` (Quick Wins/Fill-ins = 30min, Thankless = 90min, Major Projects = 120min) through `get_task_duration_minutes()`, plumbed into `scheduler.schedule_tasks()` as a `duration_fn` instead of a flat number. Adjust the numbers in `notion_tasks.py` directly if they don't feel right after a week of real use — a real per-task "Estimated Duration" Notion property remains a future option if Priority-based defaults aren't accurate enough.
  3. Because idempotency means a task already holding a block never gets touched again, the 8 blocks from the first (pre-fix) run had to be manually deleted and re-synced to pick up the new behavior — confirmed working: 3 tasks now correctly scheduled at 30/30/120 minutes, the other 5 no-priority tasks correctly excluded.
- **Second follow-up fix, same day**: Sunday gets its own separate window, **15:00-21:00** (`config.SUNDAY_START_HOUR`/`SUNDAY_END_HOUR`), no lunch split — and is **light-tasks-only**: only Quick Wins/Fill-ins (`notion_tasks.LIGHT_PRIORITIES`/`is_light_task()`) ever get scheduled there. Major Projects/Thankless Tasks skip Sunday entirely, *even if overdue* (confirmed explicitly with the user — overdue-jumps-queue only affects ordering within eligible days, not which days a task is eligible for at all), rolling to the next available weekday instead. Enforced in `scheduler.schedule_tasks()`'s day-eligibility loop, not in `_work_blocks_for_day()` (which only knows about time-of-day, not task priority). Verified via a dry run with a synthetic overdue Major Project (correctly skipped Sunday, landed Monday morning) before touching the live calendar, then confirmed against the real 3 tasks after another manual delete-and-resync (same idempotency caveat as above).
- **Ranking logic, original 2026-08-02 version, superseded 2026-08-03 — see the seventh follow-up fix below**: overdue tasks always came first regardless of Priority, ordered by how overdue they were. This turned out to be built on a wrong assumption about what the Notion `Date` property means — see below.
- **Third follow-up fix**: the 7am `StartCalendarInterval` trigger assumes the Mac is awake at 7am, which doesn't hold for the user's actual routine (laptop closed overnight, not opened until work starts around 9am). Added `RunAtLoad: true` to the sync plist — fires the sync every time the LaunchAgent is (re)loaded, which happens at every fresh login, independent of whatever the 7am trigger did or didn't do. This is a *guarantee* for the "Mac was off, fresh login at 9am" case; for "Mac was merely asleep, not logged out," `StartCalendarInterval` also has its own documented catch-up-after-wake behavior, so the two triggers are complementary, not redundant-in-a-bad-way — and any actual overlap is harmless since `sync_tasks.py` is fully idempotent (a second same-day run just finds everything already blocked and no-ops). **Verified for real, not just asserted**: reloading the agent triggered an immediate sync run with no manual `launchctl kickstart` needed, confirmed via the log timestamp matching the exact reload time.
- Free-slot computation checks busy time across **`Focus Blocks` + `iCloud-work` (the Outlook-synced calendar) + `PQi` + `个人`** (confirmed calendar names, see `config.BUSY_CALENDARS`) — not just this tool's own calendar.
- Working hours: 9:00–18:00 minus a 12:00–13:00 lunch break, Monday–Friday, Saturday fully excluded; Sunday has its own separate 15:00–21:00 window and light-tasks-only rule (`config.py`; see the second follow-up fix above).
- **Idempotency verified working end-to-end**: each created event's notes are tagged `notion_id:<page_id>`; `sync_tasks.py` checks `calendar_bridge.find_event_by_notion_id()` *before* scheduling, so a task that already has a block is skipped entirely (not re-scheduled, not duplicated) on rerun — confirmed by running the real sync twice back-to-back (8 created, then 8 skipped / 0 created).
- **Fourth follow-up fix (2026-08-02, superseded by the fifth below)**: marking a task Completed in Notion never touched its calendar block — nothing watched for that, so finished tasks kept sitting on the calendar indefinitely. Fixed with a bounded 14-day lookback query (`notion_tasks.find_recently_completed_pages()`), later replaced entirely — see below.
- **Fifth follow-up fix (2026-08-03) — full reconciliation, replacing the fourth fix's bounded lookback**: the user edited an existing task in place (renamed "Renew ID document" → "Renew ID document - gather photos", changed its Priority and Date) rather than completing or deleting it — a case the fourth fix's Completed/Discarded-only query could never catch, since the page still matched every other query filter. **Root cause of why bulk queries can't solve this**: under Notion's data-sources API model, a bulk query only ever returns pages that *currently* match its filter — there's no query for "a page that used to match but was edited or deleted out of matching." The fix instead walks every existing calendar block directly (`calendar_bridge.list_all_events()`, no date bound so a task whose due date drifted can't be missed) and looks up each one's tagged page by ID (`notion_tasks.get_live_task_snapshot(page_id)`), which returns `None` if the page is deleted/archived/no-longer-actionable, or the live `(name, priority, due)` otherwise — compared directly against what's stored in the block's own notes. Any mismatch (or `None`) deletes the block; the task then reschedules fresh (correct name/duration/date) via the normal pass. Calendar event notes now also carry a `Priority:` line (previously just `notion_id:`/`Due:`/url) so priority drift is detectable too, not just name/date.
  - **A real, separate bug surfaced and got fixed along the way**: AppleScript string literals can't contain a raw embedded newline — `osascript` silently truncates at the first one with no error, which meant the multi-line notes format (`notion_id:`/`Priority:`/`Due:`/url, one per line) had *always* collapsed to just its first line once written, since Phase 1. Nothing had ever needed to read those extra lines back until this reconciliation feature did. Fixed in `calendar_bridge.create_event()` by building the notes as an AppleScript `&`-concatenation with the `linefeed` constant instead of a single string literal; the event-list AppleScript output format also switched its record/field delimiters from linefeed/tab to control characters (`ASCII 30`/`31`) so genuinely multi-line notes content can't be confused with the delimiters used to separate one event from the next.
  - **Verified end-to-end against real data, not just logic review**: ran the real edited "Renew ID document" task through it — correctly detected the name+priority+due drift and refreshed the block; a second pre-existing block (created before the `Priority:` line existed) was correctly treated as drifted too (an expected one-time migration side effect, not a bug). A rerun immediately after was a clean no-op (0 removed, 0 created, all already-blocked) — confirms the notes now round-trip correctly and reconciliation doesn't thrash. Then ran a synthetic test task through every drift type individually, each verified against the *other* 6 real blocks staying untouched: due-date change (1 removed, 1 recreated at new date), marked Completed (1 removed, 0 recreated — no longer actionable), archived/deleted (0 removed — already gone, no errors, safe to rerun indefinitely).
- **Former "known Phase 1 limitation" — now resolved by the fifth follow-up fix above**: a task's block used to not move if its Notion `Date` (or Name, or Priority) changed after the block was created; reconciliation now catches and refreshes all of these automatically on every sync, no manual deletion needed.
- **Sixth follow-up fix (2026-08-03) — breathing room between blocks**: the user noticed blocks were packed completely back-to-back with no gap at all. `scheduler.schedule_tasks()` now reserves a break immediately after each placement before considering the next one — 10 minutes after a light (Low Effort) task, 30 minutes after a heavy (High Effort) one (`notion_tasks.get_task_break_minutes()`, same effort-based grouping as `LIGHT_PRIORITIES`). The break itself is never a real calendar event — it's just time the next placement skips over, so it shows as ordinary free time in Calendar.app rather than a separate "Break" block. Verified with a synthetic dry run (read-only against the real calendar, no writes) whose placements were manually traced against the real busy time and matched exactly, then confirmed live after a delete-and-resync of that day's blocks.
- **Seventh follow-up fix (2026-08-03) — `Date` is a start date, not a deadline**: the user pointed out the tool had been misreading the Notion `Date` property the whole time — it marks when a task becomes available to start, not when it's due (there is no separate deadline property in this database). This explains the "too many tasks land on today" complaint directly: the original ranking rule treated *any* task whose Date was in the past as maximally overdue and jumped it to the front of the queue regardless of Priority — and since most of the backlog's start dates were already in the past, nearly everything qualified, flooding today's schedule with low-priority tasks that had simply been sitting unstarted for a while. Fixed in two parts (`notion_tasks.py`): the fetch filter now requires `Date <= today` with no look-ahead window (a future start date isn't actionable yet, period), and ranking is pure Priority order (Quick Wins → Major Projects → Fill-ins → Thankless Tasks) tie-broken by earliest start date within a tier — no more "old start date overrides Priority" behavior. **Verified against real data**: today's actionable count dropped from 6 to the correct 3 (the other 3 had start dates on 2026-08-04/08-06, confirmed directly against Notion, correctly excluded until their own start date arrives), and a delete-and-resync produced a live schedule of exactly those 3, ranked by Priority with the sixth fix's breaks visible in between.
- **Eighth follow-up fix (2026-08-03) — same-day resync could schedule into the past, and concentration wasn't considered at all**: the user added a new Fill-ins task to Notion mid-morning while already working on an earlier Major Projects block; a resync placed the new task at 9:00–9:30 — already past by the time it ran (it was 10:15). Root cause confirmed by tracing every entry point (`scheduler._work_blocks_for_day()`/`compute_free_slots()`/`schedule_tasks()`, reached by the 7am trigger, `RunAtLoad`, and the dashboard's "Run sync now" button alike): nothing anywhere in the pipeline ever consulted the actual wall-clock time — a free slot was offered up purely from fixed work-hour boundaries and Notion/Calendar busy time, with no floor at "now." Fixed in `scheduler.py`: `_work_blocks_for_day()` now accepts an optional `now`, and when the day being scheduled is `now`'s own date, clips every block's start to `max(block_start, round_up(now, 5min))`, dropping any block that's entirely in the past (e.g. `now` already past `WORK_END_HOUR`, or inside/past lunch). `schedule_tasks()` computes `now` once per call (defaulting to `datetime.now()`) so every task placed in the same run shares one consistent floor. A 7am/login-time run is unaffected (`now` is already before `WORK_START_HOUR`) — this only changes behavior for a genuine mid-day resync. Separately, the user asked whether it's logical for low-concentration tasks to slot in ahead of high-concentration ones: `notion_tasks.PRIORITY_ORDER` was Impact-first (`Quick Wins → Major Projects → Fill-ins → Thankless Tasks`) with no concept of concentration/energy at all. Reordered to Effort-first, Impact as the tie-break within each tier: `Major Projects → Thankless Tasks → Quick Wins → Fill-ins` — since `schedule_tasks()` is a single greedy first-fit pass in list order, putting heavy tasks first is sufficient on its own to give them the day's freshest slots, with light tasks naturally filling in whatever's left over. Confirmed via grep that `PRIORITY_ORDER` has exactly one consumer (`notion_tasks.py`'s own `sort_key()`), so the reorder is fully self-contained. **Verified with a synthetic test** (Focus Blocks calendar scoped, avoiding a separately-discovered ~30s-latency issue in the 4-calendar busy check — see below): with a simulated `now` of 10:15am and a real busy "Draft review" block already on the calendar, every synthetic placement landed at or after 10:15, and the heavy synthetic task claimed the day's first available slot while the light ones were pushed later — matching the real bug scenario exactly.
  - **Follow-up, same day — the watermark didn't go far enough**: the user pointed out the live result still had "Side-project coding session" (Fill-ins) landing chronologically *before* the two Major Projects tasks scheduled the same day (it grabbed a small leftover morning gap the heavy tasks couldn't fit into) — correctly identifying that heavy-first *processing order* isn't the same guarantee as heavy-first *chronological placement*, since first-fit backfills whatever gaps a later, smaller task happens to fit. Fixed by making `schedule_tasks()` stably re-sort tasks heavy-before-light regardless of input order (guaranteeing every heavy task in a batch is attempted before any light one), and tracking a per-day watermark: once a heavy task is placed on a given day, no light task considered for that same day may start before that heavy task's own end + break, even if an earlier small gap would otherwise fit it. Deliberately scoped to heavy tasks placed *by this same run* only, not pre-existing calendar blocks from earlier syncs, since there's no reliable way to infer "was this busy interval a heavy task" from a plain calendar event's start/end/summary alone. `_work_blocks_for_day`'s `now` parameter was generalized/renamed to `floor` (any earliest-allowed-start instant, not just wall-clock time) to carry both constraints through the same mechanism. **Verified with an isolated synthetic test** on a real-calendar-data-free future day: a 30-min light task that would previously have grabbed a small pre-heavy-task morning gap now correctly waits until after the heavy task's own placement. **Verified live**: deleted and resynced today's real blocks — "Side-project coding session" now correctly rolls to tomorrow morning instead of squeezing into today's pre-lunch gap, since both real Major Projects tasks fill the rest of today with no room left after their own placements.
  - **Follow-up, same day — the ~30s latency was investigated and fixed, but not the way first assumed**: `calendar_bridge.list_busy_events()`'s 4-calendar query consistently took ~29-30s against the real calendars, right at the edge of (and sometimes past) `_run_applescript`'s hardcoded 30s timeout. Root cause: AppleScript's `whose` filter on Calendar.app events scans a calendar's *entire* event history linearly, not via a date index — one iCloud-synced calendar (`个人`) alone consistently cost ~15s, presumably proportional to its total accumulated event count. **First attempt — running each calendar's query as a separate concurrent subprocess — was tried and measured to make no difference at all** (still ~29.6s total): a direct timing test of two calendars queried concurrently confirmed they finished sequentially, one visibly queued behind the other's actual work rather than overlapping, because Calendar.app itself serializes incoming Apple Events one at a time regardless of how many client processes are asking concurrently. The bottleneck is inside Calendar.app, not this process, so no amount of client-side concurrency can shorten it — reverted to the simpler single-script form. **The only real, available mitigation**: bumped `_run_applescript`'s timeout from 30s to 45s, giving comfortable headroom over the measured ~29-30s. Also switched this function's output delimiters from tab/linefeed to the same control-character scheme (`ASCII 30`/`31`) already used elsewhere in this file, for consistency (calendar/event names here are unlikely to contain tabs, but there's no reason for this one query to be the odd one out).
- Daily automatic sync is live via a real `StartCalendarInterval` LaunchAgent (7:00am, adjustable in `launchd/com.qinshuoshen.procrastination-tool.sync.plist`) — confirmed running cleanly non-interactively (no permission prompts, correct idempotent no-op behavior) via `launchctl kickstart`. **Disabled 2026-08-07** — see the "Reloading the sync agent" section below; this history entry is left as-is since it was accurate at the time.
- **Ninth follow-up fix (2026-08-03) — rest-of-week look-ahead**: the user noticed the calendar only ever showed today, never a preview of the rest of the week. Root cause: `notion_tasks.fetch_actionable_tasks()`'s filter was `Date <= today` with no look-ahead (the seventh follow-up fix above) — a task due Thursday simply wasn't fetched at all until Thursday's own sync ran, so the week filled in one day at a time instead of all at once. Fixed by changing the filter to `Date <= end of this week` (`_end_of_week()` — the coming Sunday, this project's last working day per `WORKING_WEEKDAYS`, or today itself if today is Sunday), so Tuesday–Friday tasks are now visible and placeable today. This alone would have let a task be *placed* before its own start date, though, so `scheduler.schedule_tasks()`'s day-selection loop now also skips any candidate day earlier than the task's own `due` — a task fetched ahead of time is visible for scheduling but still can't land before its start date arrives. `sort_key`'s tie-break order (priority tier first, due date second) was deliberately left unchanged, to preserve the effort-first "heavy tasks get the freshest slot" guarantee from the eighth follow-up fix — due date only breaks ties within a tier, it doesn't override priority now that a fetch can span multiple due dates. **Verified**: a synthetic Major Projects task dated Thursday correctly appeared in a Monday-run fetch but only got *placed* on/after Thursday, while a same-run Fill-ins task due today still landed today unaffected.

## Using the focus timer

```bash
focus start                              # 25-minute default session
focus start --duration 45                # custom length in minutes
focus start --task "Draft review"        # optional label, shown in history
focus history                            # recent sessions
focus history --limit 20
```

(`focus` is installed into `.venv/bin/` — either activate the venv first, or call `.venv/bin/focus` directly, same as the other commands in this README.)

A session blocks the terminal with a live countdown until it finishes, you press **Ctrl-C** to stop early, or you press **`p`** to pause / **`r`** to resume. A **fully completed** session triggers a notification with a random reward suggestion from `spin_wheel_config.json` — edit that file directly to change the list (all items equally likely, no weighting). An **early-stopped** session is still logged (so you have an honest record), but doesn't get a reward, to keep the incentive tied to actually finishing.

**Pause is for real interruptions, not free time.** If a pause lasts more than `PAUSE_FAIL_MINUTES` (default 20, adjustable in `.env`), the session auto-fails — logged distinctly from both a completion and an early stop, no reward. The 20-minute clock is per-pause, not cumulative: resuming resets it, so several short pauses across a session are fine as long as no single one runs past the limit. Time spent paused doesn't count toward the session's logged minutes either way.

**Hard constraint, not just today's behavior**: the spin wheel only ever *displays* a suggestion via a local notification. It has no ability to contact anyone on your behalf, including for suggestions like "call a friend" — that's something you choose to act on, not something the code does. See `spin_wheel.py`'s module docstring for the full reasoning (this was the redesign of your original "automated embarrassment" idea from the planning phase).

## What Phase 2 proved

- Single blocking `focus start` command (Ctrl-C to stop early) rather than separate `start`/`stop` invocations — no state file needed to track "is a session currently running" across process invocations, and it matches how you'd actually sit down and focus.
- Session log is SQLite (`data/sessions.db`, stdlib `sqlite3`, no new dependency) rather than CSV/JSON — gives Phase 4's dashboard something queryable for free.
- `focus` is a properly installed console command (`pyproject.toml`'s `[project.scripts]`), not a `python3 scripts/...` invocation — the daily-use tool deserved better ergonomics than the background sync scripts need.
- Verified end-to-end: a short real session correctly completed, spun the wheel, sent a notification (visually confirmed), and logged to SQLite; a real Ctrl-C mid-session correctly logged as incomplete with no reward and a different notification (also visually confirmed). Test rows cleaned out of the database afterward so they don't skew future stats.
- No LaunchAgent needed for this phase — unlike the Notion sync, focus sessions are something you deliberately start yourself, not a background automation.
- **Follow-up (2026-08-03) — pause/resume with a 20-minute auto-fail**: the user wanted to pause a session for a real interruption without either abandoning it or leaving the clock running unattended. `run_focus_session()` now puts stdin into cbreak mode (`termios`/`tty.setcbreak`) and polls for a single keypress (`select.select`) each tick instead of a plain `time.sleep`: `p` pauses, `r` resumes, Ctrl-C still stops early exactly as before (cbreak only clears `ICANON`/`ECHO`, it leaves `ISIG` alone, so Ctrl-C still raises `KeyboardInterrupt`). If the *current* pause (not cumulative pause time across the session — confirmed with the user, it resets on every resume) exceeds `config.PAUSE_FAIL_MINUTES` (default 20, env-overridable), the session auto-fails: a third distinct outcome (`failed_pause_timeout`) alongside `completed`/`stopped_early`, no reward, its own notification. `actual_minutes` changed from wall-clock (`end - start`) to worked-time-only (pause time excluded) — matches what "focused minutes" is supposed to mean once pausing is a real thing a session can do. Storage: a new nullable `outcome` column on `sessions`, added via a guarded `ALTER TABLE` (`try`/`except sqlite3.OperationalError`, since sqlite has no `ADD COLUMN IF NOT EXISTS`) so the existing populated `data/sessions.db` didn't need a fresh migration script; legacy rows just show `outcome=None` and fall back to the existing `completed` bool for display. A non-tty fallback (redirected stdin) keeps the old plain blocking-loop behavior, minus pause capability, so nothing hangs if `run_focus_session()` is ever called non-interactively. **Verified live** in a real terminal via a pty-based test harness: pausing and resuming within the limit still completes with a reward and correctly excludes paused time from logged minutes; pausing past the limit (tested with `PAUSE_FAIL_MINUTES` temporarily shortened) auto-fails with no reward and a distinct notification; Ctrl-C still logs as a normal early stop. Test rows cleaned out of `data/sessions.db` afterward.

## Using the web dashboard

```bash
cd ~/Developer/procrastination-tool
cd frontend && npm install && npm run build   # one-time, and again after any frontend change
cd ..
./.venv/bin/pip install -e '.[api]'            # one-time, installs fastapi/uvicorn
.venv/bin/uvicorn api.main:app
```

Opens at `http://localhost:8000`. One process, one port: `api/main.py` serves `/api/*` (task list, the drag-and-drop weekly scheduling grid, focus session history/stats, a live-ticking focus timer, RPG character/bloodstain/questlines/gear) and, via a `StaticFiles` mount, the built React app (`frontend/dist/`) for everything else — same single-command ethos as `streamlit run app.py` or `focus start`. This replaces the Streamlit dashboard below: Streamlit's rerun-on-every-interaction model and third-party bidirectional components (see the wheel editor state gotcha in "What Phase 4 proved") were fighting the actual UX wanted — a real drag-and-drop scheduling grid and a smoothly-ticking timer, not a full-page rerun on every interaction. No logic duplicated — `api/` is a read/write layer over the same `procrastination_tool` package everything else uses, and `frontend/` just polls it for state.

## Legacy dashboard (Streamlit, superseded by the web dashboard above)

```bash
cd ~/Developer/procrastination-tool
./.venv/bin/pip install -e '.[dashboard]'   # one-time, installs streamlit
.venv/bin/streamlit run app.py
```

Opens at `http://localhost:8501` (or the next free port). Four sections: today's schedule (reads the Focus Blocks calendar directly), a "Run sync now" button (calls the exact same code the 7am LaunchAgent calls — safe to click any time, idempotent), focus session stats with a 7-day bar chart, and a spin-wheel item editor (view/remove/add, saves straight to `spin_wheel_config.json`). No separate copy of any logic — it's a UI layer over the same `procrastination_tool` package everything else uses. Kept on disk as a fallback, same precedent as `spin_wheel.py` and the old `scheduler.py`/`sync.py` auto-scheduler — still fully functional, just no longer the primary path.

## What Phase 4 proved

- Extracted the sync orchestration out of `scripts/sync_tasks.py` into `procrastination_tool/sync.py` (a `run_sync()` function) *before* writing the dashboard, specifically so the "manual sync" button and the daily LaunchAgent call identical code — verified the refactor changed nothing by rerunning the script and confirming byte-identical log format/behavior before building on top of it.
- Wheel editor has a real Streamlit state-management gotcha worth knowing: a text input's value persists across reruns unless explicitly cleared, so a naive "read the input, append if non-empty" pattern would silently re-add the same item every time the page reruns for an unrelated reason. Fixed with `st.form(..., clear_on_submit=True)` for the add-item flow, and immediate remove-and-rerun buttons (no lingering text state) for removing existing items.
- Only a single-series chart (daily focused minutes, last 7 days) — deliberately did not pull in this session's `dataviz` skill's full categorical-palette/CVD-validation machinery, since that's written for multi-series custom HTML/SVG charts; a single-hue `st.bar_chart` needs none of that (no legend, no palette, per the skill's own rules for one series).
- Dashboard dependency (`streamlit`) is `pyproject.toml`'s optional `dashboard` extra, not a core dependency — the LaunchAgent-driven background automation and the `focus` CLI don't need it installed at all.
- No LaunchAgent for this phase either — same reasoning as Phase 2, this is something you open when you want to look at it, not a background process.

## Package layout

```
app.py                       # Phase 4: legacy Streamlit dashboard (streamlit run app.py), superseded by api/+frontend/
api/                          # Phase 6: FastAPI backend -- /api/* routes, plus serves frontend/dist/ itself (uvicorn api.main:app)
  main.py                    # app instance, router registration, StaticFiles mount for the built frontend
  routers/                   # tasks, calendar, planner, sessions, character, gear, focus
  schemas.py                 # pydantic response/request models
frontend/                     # Phase 6: Vite + React + TS web dashboard (npm run build -> dist/, served by api/main.py)
  src/                       # App.tsx composes TodaySchedule, Planner, FocusTimerWidget, FocusStats, CharacterPanel, ArmoryPanel
procrastination_tool/
  config.py                 # .env loading + scheduling config (working hours, busy calendars, etc.)
  calendar_bridge.py        # AppleScript Calendar read/write, busy-time queries, notion_id lookup
  notify.py                 # macOS notification wrapper
  notion_client_wrapper.py  # basic Notion connectivity check (used by smoke_test.py)
  notion_tasks.py           # fetch + rank actionable tasks from the real Notion schema
  scheduler.py              # free-slot computation + greedy task placement
  sync.py                   # Phase 1 orchestration, shared by scripts/sync_tasks.py and app.py
  focus_timer.py            # Phase 2: session timer loop + SQLite logging
  spin_wheel.py             # Phase 2: reward suggestion picker (suggest-only, see docstring)
  focus_cli.py              # Phase 2: `focus` command (installed via pyproject.toml)
scripts/
  smoke_test.py             # Phase 0 de-risking test
  sync_tasks.py             # Phase 1: thin LaunchAgent wrapper around procrastination_tool.sync
launchd/
  com.qinshuoshen.procrastination-tool.smoketest.plist  # Phase 0 test agent, no schedule
  com.qinshuoshen.procrastination-tool.sync.plist        # Phase 1 production agent, daily 7am
spin_wheel_config.json      # Phase 2: user-editable reward suggestion list (also editable from the dashboard)
logs/
  smoke_test.log / sync_tasks.log / streamlit.log      # application-level logs
  launchd_{smoketest,sync}.{out,err}.log                # raw launchd stdout/stderr capture
data/
  sessions.db                # Phase 2: focus session history (SQLite), read by both `focus history` and the dashboard
```

## The sync LaunchAgent is currently disabled (2026-08-07)

`scripts/sync_tasks.py` (what this LaunchAgent runs) calls `sync.run_sync()`,
which includes `scheduler.schedule_tasks()` — the old automatic first-fit
placer. An audit found it was still firing daily at 7am and on every login,
auto-creating calendar blocks in silent competition with the manual
drag-and-drop grid the React dashboard replaced it with. It's been unloaded
(`launchctl unload`) and the installed copy removed from
`~/Library/LaunchAgents/`; the source plist below is untouched in the repo.

Stale/completed calendar blocks still get cleaned up without this agent —
the dashboard's "🔄 Refresh (Notion + Calendar)" button calls
`sync._reconcile_calendar_with_notion()` directly, which is only the
cleanup half, not the auto-placement half.

To re-enable full automatic scheduling (not recommended if you're using the
manual grid — the two will compete for the same tasks again):

```bash
cp launchd/com.qinshuoshen.procrastination-tool.sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.sync.plist
```

## Reloading the sync agent (e.g. after changing the schedule time, once re-enabled)

```bash
launchctl bootout gui/501/com.qinshuoshen.procrastination-tool.sync 2>/dev/null
cp launchd/com.qinshuoshen.procrastination-tool.sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.qinshuoshen.procrastination-tool.sync.plist
```
