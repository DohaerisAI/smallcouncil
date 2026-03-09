# Small Council

> *"The Small Council does the actual ruling."* — Varys

A zero-dependency, AI-native weekly planner where human and AI agents sit at the same table. Built as a single HTML file + Python server. No frameworks, no build steps, no nonsense.

Your AI agents don't just read tasks — they **claim** them, **write plans**, **log progress**, **deliver artifacts**, and **move to review**. Like a Hand of the King that actually gets things done.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Zero Dependencies](https://img.shields.io/badge/frontend-zero%20deps-green)
![SQLite](https://img.shields.io/badge/database-SQLite-lightgrey)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## What Makes This Different

Most task boards are passive — they show tasks and let you drag cards around. Small Council is **AI-native from day one**:

| Feature | Typical Board | Small Council |
|---------|--------------|---------------|
| AI reads tasks | Maybe via API | Built-in agent queue |
| AI claims work | Manual assignment | `POST /tasks/:id/claim` |
| AI writes plans | Separate docs | Plans live on the task |
| AI logs progress | Nowhere | Comment thread per task |
| AI delivers files | Slack/email | Artifacts auto-discovered |
| Work/Life split | One board | Two realms, one throne |

### The Agent Loop

```
Check queue → Claim task → Write plan → Do work → Log progress → Deliver artifacts → Move to review
```

Every step is an API call. Every action is visible on the board. No black boxes.

---

## Features

### The Board
- **6-column kanban**: Todo, In Progress, Blocked, Review, Staging, Done
- **Drag and drop** cards between columns
- **Click any card** to see full details, comments, and artifacts
- **Project filtering** with one click
- **Calendar picker** — click the week label to jump to any week
- **Subtasks** with inline checkboxes and progress tracking
- **Task dependencies** — see what blocks what
- **Due dates** with overdue/today highlighting
- **Burndown chart** — are you ahead or behind?
- **Activity heatmap** — GitHub-style contribution graph
- **Streak counter** — keep the fire alive
- **Markdown export** — clipboard or file download

### AI-Native
- **Agent Queue** (`GET /tasks/agent-queue`) — unclaimed work, ready to pick up
- **Task Claiming** (`POST /tasks/:id/claim`) — sets status, logs comment, creates artifacts dir
- **Comment Threads** — typed comments (plan, review, log, blocker) per task
- **Artifacts Directory** (`~/.claude/board-artifacts/{task-id}/`) — auto-discovered files
- **Full audit trail** — every claim, plan, and progress update is visible

### Two Realms
- **Small Council** (Work) — your professional projects, warm terracotta theme
- **The Realm** (Personal) — life stuff, cool teal theme
- Toggle with one click, completely separate boards
- Agents only see Work mode — they don't touch your personal life

---

## Installation

### 1. Clone & Setup

```bash
git clone https://github.com/YOUR_USERNAME/small-council.git
cd small-council
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn
```

### 2. Run

```bash
python server.py
# → http://localhost:8089
```

That's it. Open the URL. The database auto-creates on first run with demo tasks.

### 3. Run as a Service (optional)

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/small-council.service << EOF
[Unit]
Description=Small Council
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python $(pwd)/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now small-council.service
```

---

## Agent Integration

### Claude Code

Copy the agent rules file into your Claude Code rules directory:

```bash
# Global (all projects)
cp agent-rules.md ~/.claude/rules/common/small-council.md

# Or project-specific
cp agent-rules.md /path/to/project/.claude/rules/small-council.md
```

Claude will now automatically check the board for tasks, claim work, and report progress.

### OpenAI Codex / Other Agents

Paste the contents of `agent-rules.md` into your agent's system prompt or instructions file.

For Codex, add to your project's `AGENTS.md` or equivalent instructions file:

```bash
cat agent-rules.md >> /path/to/project/AGENTS.md
```

### Any HTTP-capable Agent

The board is just a REST API. Any agent that can make HTTP calls can:

```bash
# Check for work
curl -s http://localhost:8089/api/tasks/agent-queue

# Claim a task
curl -s -X POST http://localhost:8089/api/tasks/3/claim \
  -H 'Content-Type: application/json' \
  -d '{"author": "my-agent"}'

# Log progress
curl -s -X POST http://localhost:8089/api/tasks/3/comments \
  -H 'Content-Type: application/json' \
  -d '{"author": "my-agent", "content": "Done. Output at ./result.json", "type": "log"}'

# Move to review
curl -s -X PUT http://localhost:8089/api/tasks/3 \
  -H 'Content-Type: application/json' \
  -d '{"status": "review"}'
```

---

## Customizing Projects

Edit the `PROJECTS` constant in `index.html` to match your actual projects:

```javascript
const PROJECTS = {
  work: {
    // Change these to your project names
    backend: "Backend API",
    frontend: "Frontend App",
    infra: "Infrastructure",
    mobile: "Mobile App",
    docs: "Documentation"
  },
  personal: {
    learning: "Learning",
    sideproject: "Side Projects",
    health: "Health",
    finance: "Finance",
    home: "Home"
  }
};
```

Then add matching CSS classes for project colors (search for `.project-dragon` in the `<style>` block and follow the pattern).

The seed data only runs on first launch (empty database). Delete `board.db` and restart to re-seed with your new project names.

---

## API Reference

### Tasks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks?week=YYYY_wNN&mode=work` | GET | Get tasks for a week |
| `/api/tasks` | POST | Create task `{weekKey, title, project, ...}` |
| `/api/tasks/:id` | PUT | Update task fields |
| `/api/tasks/:id` | DELETE | Delete task |

### AI-Native Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks/agent-queue` | GET | Unclaimed agent tasks (work mode only) |
| `/api/tasks/:id/claim` | POST | Claim task `{author: "claude"}` |
| `/api/tasks/:id/comments` | GET | Get comment thread |
| `/api/tasks/:id/comments` | POST | Add comment `{author, content, type}` |
| `/api/tasks/:id/artifacts` | GET | List artifacts (auto + registered) |
| `/api/tasks/:id/artifacts` | POST | Register artifact `{path: "..."}` |

### Other

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/weeks?mode=work` | GET | List all weeks |
| `/api/weeks/next` | POST | Carry over to next week |
| `/api/activity` | GET | Recent activity feed |
| `/api/activity/counts` | GET | Activity counts by date |
| `/api/activity/streak` | GET | Current work streak |

---

## Architecture

```
small-council/
  server.py        # FastAPI + SQLite backend (< 600 lines)
  index.html       # Entire frontend — zero deps (< 1800 lines)
  test_board.py    # Test suite (< 1100 lines)
  agent-rules.md   # Copy-paste agent instructions
  board.db         # SQLite database (auto-created, git-ignored)
```

### Why Zero Dependencies (Frontend)?

- No React, no Vue, no Tailwind, no webpack
- The entire UI is one HTML file
- Loads instantly, works offline (minus API calls)
- Easy to hack, fork, and customize
- No `node_modules` black hole

### Tech Stack
- **Backend**: Python 3.10+, FastAPI, SQLite (WAL mode)
- **Frontend**: Vanilla HTML/CSS/JS — zero build step
- **Database**: SQLite with WAL journaling and foreign keys

---

## Default Projects

### Work Mode (Small Council)

| Key | Name | Color |
|-----|------|-------|
| dragon | Dragon | Teal |
| raven | Raven | Orange |
| titan | Titan | Gold |
| shadow | Shadow | Steel |
| crown | Crown | Mauve |

### Personal Mode (The Realm)

| Key | Name | Color |
|-----|------|-------|
| learning | Learning | Steel |
| sideproject | Side Projects | Green |
| health | Health | Teal |
| finance | Finance | Gold |
| home | Home | Warm |

---

## Running Tests

```bash
# Make sure the server is running first
python server.py &

# Run the test suite
python -m unittest test_board.py -v
```

---

## License

MIT — do whatever you want with it.

---

*"When you play the game of tasks, you win or you carry them over to next week."*
