# Winslow — Getting Started

Hi Aleks! This is a little app Qinshuo built to help with procrastination — a task board, a focus timer, and a place to track your mood and daily wins. This guide covers two things:

1. **Getting in** — installing the one thing you need and logging in.
2. **Using it** — a walkthrough of everything on the site.

You don't need to install anything else, and there's nothing to download or set up on your own computer beyond step 1 below. Everything else just runs in your web browser.

---

## Part 1: Getting In

### Step 1 — Install Tailscale

Winslow isn't a public website — it only works over a private, secure connection called **Tailscale**, so a small app needs to be running in the background on your computer first.

1. Go to **[tailscale.com/download](https://tailscale.com/download)** and download it for **Windows**.
2. Run the installer and open Tailscale once it's done.
3. It'll ask you to sign in — you can use a Google account, Microsoft account, or your email. Any of these is fine, just remember which one you used.

### Step 2 — Accept Qinshuo's invite

Qinshuo needs to share access to the Winslow computer with you first — ask him to do this if he hasn't already (Tailscale admin console → "Share" on the `winslow-vps` device). You'll get an email with a link.

1. Open that email and click the invite link.
2. It'll open in your browser and ask you to accept the shared device — click **Accept**.
3. Make sure Tailscale is still running (check for its icon in your system tray, bottom-right of your screen).

You only have to do Steps 1 and 2 once, ever.

### Step 3 — Open Winslow

With Tailscale running, open your browser (Chrome, Edge, whatever you normally use) and go to:

**`https://winslow-vps.tail59b502.ts.net`**

Tip: bookmark this page, or drag the star icon in your address bar, so you don't have to type it again.

### Step 4 — Log in

You'll see a simple login screen.

- **Username:** `Aleks`
- **Password:** whatever Qinshuo set up with you when he created your account.

Click **Sign in**.

### Changing your password

Once you're logged in, click **Change password** in the top-right corner of the page. You'll need your current password plus a new one (typed twice, to make sure you didn't mistype it). After that, only you know your password — not even Qinshuo can see it.

**If you forget your password:** message Qinshuo — he'll reset it to a temporary one and send it to you. Log in with that, then immediately go back to **Change password** and set your own again, so it goes back to being something only you know.

---

## Part 2: Using Winslow

Once you're logged in, you'll see a navigation bar at the top with four pages: **Tasks**, **Projects**, **Focus**, and **Evaluation**.

### Tasks page (the main page)

This is your task board, split into two columns:

- **Today** — what you're planning to work on today.
- **Task Pool** — everything else, waiting to be picked up.

Inside each column, tasks are grouped into four buckets based on how much effort and impact they have:

- **Quick Wins** — low effort, high impact. Do these when you want an easy win.
- **Major Projects** — high effort, high impact. The big, meaningful stuff.
- **Thankless Tasks** — high effort, low impact. The chores nobody wants to do.
- **Fill-ins** — low effort, low impact. Good for filling small gaps in your day.

**To add a task:** click the **+ Add task** button. Give it a name, pick a bucket, and optionally add notes, tags, or link it to a project.

**To work with a task:**
- Click its status dropdown to mark it *Not Started*, *In Progress*, *On Hold*, or *Completed*.
- Click the **Today ⇄ Pool** toggle to move it between the two columns.
- Click on the task's name to open it and edit notes, tags, or its linked project.

Above the board is a **standup box** — type a question (like "what should I focus on today?") or leave it blank and click **Generate** for a short, encouraging note about your day.

### Projects page

For anything bigger than a single task — track its own status and notes, and see every task linked to it laid out as a timeline. Click **+ New project** to create one.

### Focus page

A simple focus timer (like a Pomodoro timer):

1. Type what you're working on (optional) and pick how many minutes.
2. Click **Start**. A countdown appears.
3. You can **Pause**/**Resume** if you get interrupted, or **Stop** to end early.
4. When a session finishes, you'll get a notification — even if you've closed the tab (as long as you said yes to notifications the first time it asked).

Below the timer, you'll see a chart of your focused minutes over the last 7 days.

### Evaluation page

A short end-of-day check-in:

- **Log your mood** any time during the day with one tap (1–5 scale).
- Click **Generate today's evaluation** for a summary of what you got done and how you felt.
- There's also a **weekly retro** below it, if you want a bigger-picture look at the week.

---

## Troubleshooting

- **Can't reach the page at all** → check that Tailscale is running (system tray icon) and that you're signed into it.
- **"Incorrect username or password"** → double check the username is exactly `Aleks` (capital A), and that Caps Lock isn't on. If you're still stuck, message Qinshuo.
- **Nothing happens after clicking Sign in** → try refreshing the page once, then log in again.

If anything else looks broken or confusing, just message Qinshuo — this is a small app he built and maintains himself, not a big company product, so he's the one to ask.
