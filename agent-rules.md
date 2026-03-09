# Small Council - Agent Rules

A local AI-native task board runs on `http://localhost:8089`.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks/agent-queue` | GET | Unclaimed agent tasks (mode=work, status=todo, owner=agent) |
| `/api/tasks/:id/claim` | POST | Claim task: sets inprogress, logs comment, creates artifacts dir |
| `/api/tasks/:id/comments` | GET | Get comment thread for a task |
| `/api/tasks/:id/comments` | POST | Add comment `{author, content, type}` |
| `/api/tasks/:id/artifacts` | GET | List artifacts (auto-discovers + registered) |
| `/api/tasks/:id/artifacts` | POST | Register file path `{path}` on task |
| `/api/tasks?week=YYYY_wNN&mode=work` | GET | Get all tasks for a week |
| `/api/tasks` | POST | Create task `{weekKey, title, project, ...}` |
| `/api/tasks/:id` | PUT | Update task fields |
| `/api/tasks/:id` | DELETE | Delete task |
| `/api/weeks?mode=work` | GET | List all weeks |
| `/api/activity` | POST | Log activity `{ts, date, type, project, title}` |

## Week Key Format

`YYYY_wNN` — ISO week number. Calculate with `date +%G_w%V`.

## Comment Types

| Type | When to Use |
|------|-------------|
| `comment` | General notes |
| `plan` | Implementation plan posted |
| `review` | Code review or PR summary |
| `log` | Progress update |
| `blocker` | Something is blocking progress |

## Artifacts Directory

```
~/.claude/board-artifacts/{task-id}/
  plan.md, review.md, output.json, etc.
```

Auto-created on claim, auto-discovered by the artifacts endpoint.

## Agent Workflow

When asked to check tasks, pick up work, or report progress:

```bash
# 1. Check for available work
curl -s http://localhost:8089/api/tasks/agent-queue

# 2. Claim a task (sets status=inprogress, creates artifacts dir)
curl -s -X POST http://localhost:8089/api/tasks/:id/claim \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude"}'

# 3. Write plan to artifacts directory
mkdir -p ~/.claude/board-artifacts/{id}/
cat > ~/.claude/board-artifacts/{id}/plan.md << 'EOF'
# Plan
- Step 1: ...
- Step 2: ...
EOF

# 4. Post plan as comment
curl -s -X POST http://localhost:8089/api/tasks/:id/comments \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude", "content": "Plan written. Key steps: ...", "type": "plan"}'

# 5. Do the actual work...

# 6. Log progress as you go
curl -s -X POST http://localhost:8089/api/tasks/:id/comments \
  -H 'Content-Type: application/json' \
  -d '{"author": "claude", "content": "Completed X. Output at /path/to/file", "type": "log"}'

# 7. Register output artifacts
curl -s -X POST http://localhost:8089/api/tasks/:id/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"path": "/path/to/output.json"}'

# 8. Move to review when done
curl -s -X PUT http://localhost:8089/api/tasks/:id \
  -H 'Content-Type: application/json' \
  -d '{"status": "review"}'

# 9. Log activity for the heatmap
curl -s -X POST http://localhost:8089/api/activity \
  -H 'Content-Type: application/json' \
  -d "{\"ts\": $(date +%s%3N), \"date\": \"$(date +%Y-%m-%d)\", \"type\": \"complete\", \"project\": \"...\", \"title\": \"...\"}"
```

## Quick Commands

```bash
# Get this week's tasks
curl -s "http://localhost:8089/api/tasks?week=$(date +%G_w%V)&mode=work"

# Get agent queue
curl -s http://localhost:8089/api/tasks/agent-queue

# List agent tasks with status
curl -s "http://localhost:8089/api/tasks?week=$(date +%G_w%V)&mode=work" | \
  python3 -c "import sys,json; [print(f'[{t[\"status\"]}] {t[\"project\"]}: {t[\"title\"]}') for t in json.load(sys.stdin) if t['owner']=='agent']"
```
