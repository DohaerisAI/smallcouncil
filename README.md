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
pip install fastapi uvicorn fastmcp
python server.py
```

Open `http://localhost:8089`. Done.

---

## Connect Your Agents

Two ways to wire up: **MCP Server** (auto-discovery, recommended) or **Agent Rules** (copy a file).

### Option A: MCP Server

Install the dependency, then add the server to your agent's MCP config.

```bash
pip install fastmcp
```

**Claude Code** — `~/.claude.json`:
```json
{
  "mcpServers": {
    "small-council": {
      "command": "python3",
      "args": ["/path/to/small-council/mcp_server.py"]
    }
  }
}
```

**Cursor** — `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "small-council": {
      "command": "python3",
      "args": ["/path/to/small-council/mcp_server.py"]
    }
  }
}
```

**Windsurf** — `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "small-council": {
      "command": "python3",
      "args": ["/path/to/small-council/mcp_server.py"]
    }
  }
}
```

**Claude Desktop** — `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "small-council": {
      "command": "python3",
      "args": ["/path/to/small-council/mcp_server.py"]
    }
  }
}
```

**HTTP mode** (for remote agents):
```bash
python3 mcp_server.py --http
# Serves on http://localhost:8090
```

#### MCP Tools

| Tool | Description |
|------|-------------|
| `check_queue` | Get unclaimed agent tasks |
| `claim_task` | Claim a task → inprogress + artifacts dir |
| `get_task` | Full task details + comments + artifacts |
| `list_tasks` | All tasks for a week |
| `create_task` | Create a new task |
| `update_task` | Update status, title, priority, etc. |
| `add_comment` | Post plan / log / review / blocker comment |
| `complete_task` | Summary + move to review + log activity |

### Option B: Agent Rules

Copy `agent-rules.md` where your agent reads instructions. It contains the full workflow and all REST endpoints.

```bash
# Claude Code (global)
cp agent-rules.md ~/.claude/rules/common/small-council.md

# Claude Code (project-specific)
cp agent-rules.md /path/to/project/.claude/rules/small-council.md

# Cursor
cp agent-rules.md /path/to/project/.cursor/rules/small-council.md

# Windsurf
cp agent-rules.md /path/to/project/.windsurfrules/small-council.md

# OpenAI Codex
cat agent-rules.md >> /path/to/project/AGENTS.md
```

Works with any agent that can `curl` — it's just a REST API.

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

---

## License

MIT

---

*"When you play the game of tasks, you win or you carry them over to next week."*
