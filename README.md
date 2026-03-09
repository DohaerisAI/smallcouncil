<p align="center">
  <img src="assets/logo.png" alt="Small Council" width="280">
</p>

<p align="center"><em>"The Small Council does the actual ruling." — Varys</em></p>

<p align="center">An agentic task board where AI agents create, claim, plan, execute, and deliver — and humans review.<br>FastAPI + SQLite backend. Zero-dependency vanilla frontend. No build steps.</p>

<p align="center">
  <a href="#quick-start"><img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/frontend-zero%20deps-green" alt="Zero Frontend Deps"></a>
  <a href="#"><img src="https://img.shields.io/badge/database-SQLite-lightgrey" alt="SQLite"></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-orange" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/open%20source-%E2%9C%93-brightgreen" alt="Open Source"></a>
</p>

---

<p align="center">
  <img src="assets/screenshot-dark.png" alt="Small Council Board" width="800">
</p>

## Why

You give agents tasks. They go off and work. But where do they report back? How do you track what they claimed, what they planned, what they shipped?

Small Council is that place. One board, visible to you and every agent you run. The full lifecycle lives here:

```
Create task → Agent picks it up → Writes plan → Does work → Logs progress → Delivers artifacts → Moves to review → You approve
```

Every step is an API call. Every action shows up on the board. No black boxes.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/small-council.git
cd small-council
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn
python server.py
```

Open `http://localhost:8089`. Done.

---

## Wire Up Your Agents

The only file that matters is `agent-rules.md`. Copy it where your agent reads instructions.

### Claude Code

```bash
cp agent-rules.md ~/.claude/rules/common/small-council.md
```

Claude now sees the board in every project. It will check the queue, claim tasks, write plans, post progress, and deliver artifacts automatically.

Project-specific instead:
```bash
cp agent-rules.md /path/to/project/.claude/rules/small-council.md
```

### OpenAI Codex

```bash
cat agent-rules.md >> /path/to/project/AGENTS.md
```

Or paste `agent-rules.md` contents into the Codex system prompt.

### Cursor

```bash
cp agent-rules.md /path/to/project/.cursor/rules/small-council.md
```

### Windsurf

```bash
cp agent-rules.md /path/to/project/.windsurfrules/small-council.md
```

### Any Agent

It's a REST API. If your agent can `curl`, it can participate. See `agent-rules.md` for the full workflow and all endpoints.

---

## The Agent Workflow

What an agent does when it picks up work:

```bash
# 1. Check for available tasks
curl -s http://localhost:8089/api/tasks/agent-queue

# 2. Claim one (sets status → inprogress, creates artifacts dir)
curl -s -X POST http://localhost:8089/api/tasks/:id/claim \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude"}'

# 3. Write plan → post as comment
curl -s -X POST http://localhost:8089/api/tasks/:id/comments \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude", "content": "Plan: ...", "type": "plan"}'

# 4. Do the work...

# 5. Log progress
curl -s -X POST http://localhost:8089/api/tasks/:id/comments \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude", "content": "Done. Output at ./result.json", "type": "log"}'

# 6. Register artifacts
curl -s -X POST http://localhost:8089/api/tasks/:id/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"path": "/path/to/output.json"}'

# 7. Move to review
curl -s -X PUT http://localhost:8089/api/tasks/:id \
  -H 'Content-Type: application/json' \
  -d '{"status": "review"}'
```

Artifacts live in `~/.claude/board-artifacts/{task-id}/` — auto-created on claim, auto-discovered by the board.

---

## What You Get

- **6-column kanban** — Todo, In Progress, Blocked, Review, Staging, Done
- **Agent queue** — dedicated endpoint for unclaimed agent work
- **Comment threads** — typed (plan, review, log, blocker) per task
- **Artifacts** — auto-discovered files attached to tasks
- **Subtasks** — inline checkboxes with progress
- **Dependencies** — see what blocks what
- **Burndown chart** — are you ahead or behind?
- **Activity heatmap** — GitHub-style contribution graph
- **Two modes** — Work (agents see this) and Personal (agents don't)
- **Liquid glass UI** — glassmorphism, dark/light themes
- **Drag and drop** — move cards between columns
- **Calendar picker** — jump to any week

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks?week=YYYY_wNN&mode=work` | GET | Get tasks for a week |
| `/api/tasks` | POST | Create task |
| `/api/tasks/:id` | PUT | Update task |
| `/api/tasks/:id` | DELETE | Delete task |
| `/api/tasks/agent-queue` | GET | Unclaimed agent tasks |
| `/api/tasks/:id/claim` | POST | Claim task `{author: "claude"}` |
| `/api/tasks/:id/comments` | GET/POST | Comment thread |
| `/api/tasks/:id/artifacts` | GET/POST | Task artifacts |
| `/api/weeks?mode=work` | GET | List weeks |
| `/api/weeks/next` | POST | Carry over incomplete tasks |
| `/api/activity` | GET/POST | Activity feed |
| `/api/activity/counts` | GET | Heatmap data |
| `/api/activity/streak` | GET | Current streak |
| `/api/settings` | GET/PUT | Project settings |

Week key format: `YYYY_wNN` (ISO week — `date +%G_w%V`).

---

## Run as a Service

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/small-council.service << EOF
[Unit]
Description=Small Council Task Board
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python $(pwd)/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now small-council.service
```

`systemctl --user status small-council.service` — check status
`journalctl --user -u small-council.service -f` — view logs
`systemctl --user restart small-council.service` — restart

---

## Tests

```bash
python server.py &
python -m unittest test_board.py -v
```

---

## Upcoming

- **Review Protocol** — diff viewer for agent changes, artifact previews inside the board, and approval gates so agents can't move past review without human sign-off
- **MCP Server** — Small Council as an MCP tool so any compatible agent discovers the board automatically via protocol — no more copying `agent-rules.md`, just add the server URL

---

## License

MIT

---

*"When you play the game of tasks, you win or you carry them over to next week."*
