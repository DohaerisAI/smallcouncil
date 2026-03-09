#!/usr/bin/env python3
"""Weekly Board API - FastAPI + SQLite."""

import json
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board.db")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = Path.home() / ".claude" / "board-artifacts"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    init_db()
    seed_initial_data()
    yield


app = FastAPI(title="Small Council", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Database ──

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def task_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = {
        "id": row["id"],
        "project": row["project"],
        "title": row["title"],
        "priority": row["priority"],
        "status": row["status"],
        "owner": row["owner"],
        "ownerLabel": row["owner_label"],
        "due": row["due"],
        "notes": row["notes"] or "",
        "subtasks": json.loads(row["subtasks"] or "[]"),
        "files": json.loads(row["files"] or "[]"),
        "dependsOn": row["depends_on"],
        "carriedOver": bool(row["carried_over"]),
        "completedDay": row["completed_day"],
        "mode": row["mode"] if "mode" in row.keys() else "work",
    }
    # Include comment_count if present in the row
    if "comment_count" in row.keys():
        d["commentCount"] = row["comment_count"]
    return d


def comment_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "taskId": row["task_id"],
        "author": row["author"],
        "content": row["content"],
        "type": row["type"],
        "createdAt": row["created_at"],
    }


def get_artifacts_dir(task_id: int) -> Path:
    return ARTIFACTS_DIR / str(task_id)


# ── Weeks ──

@app.get("/api/weeks")
def get_weeks(mode: str = Query("work")):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT week_key, monday_date FROM weeks WHERE mode = ? ORDER BY monday_date",
            (mode,),
        ).fetchall()
    return [{"weekKey": r["week_key"], "monday": r["monday_date"]} for r in rows]


# ── Tasks ──

@app.get("/api/tasks/agent-queue")
def get_agent_queue():
    """Unclaimed agent tasks (mode=work, status=todo, owner=agent)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, COALESCE(c.cnt, 0) as comment_count
            FROM tasks t
            LEFT JOIN (SELECT task_id, COUNT(*) as cnt FROM comments GROUP BY task_id) c
              ON t.id = c.task_id
            WHERE t.mode = 'work' AND t.status = 'todo' AND t.owner = 'agent'
            ORDER BY t.id""",
        ).fetchall()
    return [task_to_dict(r) for r in rows]


@app.get("/api/tasks")
def get_tasks(week: str = Query(None), mode: str = Query("work")):
    if not week:
        raise HTTPException(400, "week param required")
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, COALESCE(c.cnt, 0) as comment_count
            FROM tasks t
            LEFT JOIN (SELECT task_id, COUNT(*) as cnt FROM comments GROUP BY task_id) c
              ON t.id = c.task_id
            WHERE t.week_key = ? AND t.mode = ?
            ORDER BY t.id""",
            (week, mode),
        ).fetchall()
    return [task_to_dict(r) for r in rows]


@app.post("/api/tasks", status_code=201)
async def create_task(request: Request):
    data = await request.json()
    week_key = data.get("weekKey")
    if not week_key or not data.get("title"):
        raise HTTPException(400, "weekKey and title required")

    mode = data.get("mode", "work")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM weeks WHERE week_key = ? AND mode = ?", (week_key, mode)
        ).fetchone()
        if not existing:
            monday = data.get("monday", "")
            conn.execute(
                "INSERT INTO weeks (week_key, monday_date, mode) VALUES (?, ?, ?)",
                (week_key, monday, mode),
            )

        cur = conn.execute(
            """INSERT INTO tasks (week_key, project, title, priority, status,
                owner, owner_label, due, notes, subtasks, files, depends_on, carried_over, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                week_key,
                data.get("project", ""),
                data["title"],
                data.get("priority", "medium"),
                data.get("status", "todo"),
                data.get("owner", "me"),
                data.get("ownerLabel", "Me"),
                data.get("due"),
                data.get("notes", ""),
                json.dumps(data.get("subtasks", [])),
                json.dumps(data.get("files", [])),
                data.get("dependsOn"),
                1 if data.get("carriedOver") else 0,
                mode,
            ),
        )
        conn.commit()
        task_id = cur.lastrowid
        row = conn.execute(
            """SELECT t.*, 0 as comment_count FROM tasks t WHERE t.id = ?""",
            (task_id,),
        ).fetchone()
    return task_to_dict(row)


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: int, request: Request):
    data = await request.json()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Task not found")

        conn.execute(
            """UPDATE tasks SET
                title = ?, priority = ?, status = ?, owner = ?, owner_label = ?,
                due = ?, notes = ?, subtasks = ?, files = ?, depends_on = ?, completed_day = ?
            WHERE id = ?""",
            (
                data.get("title", existing["title"]),
                data.get("priority", existing["priority"]),
                data.get("status", existing["status"]),
                data.get("owner", existing["owner"]),
                data.get("ownerLabel", existing["owner_label"]),
                data.get("due", existing["due"]),
                data.get("notes", existing["notes"]),
                json.dumps(
                    data.get("subtasks", json.loads(existing["subtasks"] or "[]"))
                ),
                json.dumps(
                    data.get("files", json.loads(existing["files"] or "[]"))
                ),
                data.get("dependsOn", existing["depends_on"]),
                data.get("completedDay", existing["completed_day"]),
                task_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            """SELECT t.*, COALESCE(c.cnt, 0) as comment_count
            FROM tasks t
            LEFT JOIN (SELECT task_id, COUNT(*) as cnt FROM comments GROUP BY task_id) c
              ON t.id = c.task_id
            WHERE t.id = ?""",
            (task_id,),
        ).fetchone()
    return task_to_dict(row)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return {"ok": True}


# ── Task Claim ──

@app.post("/api/tasks/{task_id}/claim")
async def claim_task(task_id: int, request: Request):
    data = await request.json()
    author = data.get("author", "agent")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Task not found")

        conn.execute(
            "UPDATE tasks SET status = 'inprogress' WHERE id = ?", (task_id,)
        )

        conn.execute(
            """INSERT INTO comments (task_id, author, content, type)
            VALUES (?, ?, ?, 'log')""",
            (task_id, author, f"Claimed task and started work."),
        )
        conn.commit()

    # Create artifacts directory
    artifacts_path = get_artifacts_dir(task_id)
    artifacts_path.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        row = conn.execute(
            """SELECT t.*, COALESCE(c.cnt, 0) as comment_count
            FROM tasks t
            LEFT JOIN (SELECT task_id, COUNT(*) as cnt FROM comments GROUP BY task_id) c
              ON t.id = c.task_id
            WHERE t.id = ?""",
            (task_id,),
        ).fetchone()
    return task_to_dict(row)


# ── Comments ──

@app.get("/api/tasks/{task_id}/comments")
def get_comments(task_id: int):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
    return [comment_to_dict(r) for r in rows]


@app.post("/api/tasks/{task_id}/comments", status_code=201)
async def add_comment(task_id: int, request: Request):
    data = await request.json()
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(400, "content required")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Task not found")

        cur = conn.execute(
            """INSERT INTO comments (task_id, author, content, type)
            VALUES (?, ?, ?, ?)""",
            (
                task_id,
                data.get("author", "user"),
                content,
                data.get("type", "comment"),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM comments WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return comment_to_dict(row)


# ── Artifacts ──

@app.get("/api/tasks/{task_id}/artifacts")
def get_artifacts(task_id: int):
    artifacts_path = get_artifacts_dir(task_id)
    files: list[str] = []

    # Auto-discover files from artifacts directory
    if artifacts_path.exists():
        for f in sorted(artifacts_path.iterdir()):
            if f.is_file():
                files.append(str(f))

    # Also include files registered on the task
    with get_db() as conn:
        row = conn.execute(
            "SELECT files FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row:
            task_files = json.loads(row["files"] or "[]")
            for tf in task_files:
                if tf not in files:
                    files.append(tf)

    return {
        "taskId": task_id,
        "artifactsDir": str(artifacts_path),
        "files": files,
    }


@app.post("/api/tasks/{task_id}/artifacts", status_code=201)
async def register_artifact(task_id: int, request: Request):
    data = await request.json()
    file_path = data.get("path", "").strip()
    if not file_path:
        raise HTTPException(400, "path required")

    with get_db() as conn:
        row = conn.execute(
            "SELECT files FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")

        existing_files = json.loads(row["files"] or "[]")
        if file_path not in existing_files:
            updated_files = [*existing_files, file_path]
            conn.execute(
                "UPDATE tasks SET files = ? WHERE id = ?",
                (json.dumps(updated_files), task_id),
            )
            conn.commit()

    return {"ok": True, "path": file_path}


# ── Activity ──

@app.post("/api/activity", status_code=201)
async def log_activity(request: Request):
    data = await request.json()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO activity_log (ts, date, type, project, title, extra)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                data.get("ts", 0),
                data.get("date", ""),
                data.get("type", ""),
                data.get("project", ""),
                data.get("title", ""),
                data.get("extra"),
            ),
        )
        conn.commit()
    return {"ok": True}


@app.get("/api/activity")
def get_activity(days: int = 90):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM activity_log
            WHERE date >= date('now', ?)
            ORDER BY ts DESC LIMIT 50""",
            (f"-{days} days",),
        ).fetchall()
    return [
        {
            "ts": r["ts"],
            "date": r["date"],
            "type": r["type"],
            "project": r["project"],
            "title": r["title"],
            "extra": r["extra"],
        }
        for r in rows
    ]


@app.get("/api/activity/counts")
def get_activity_counts():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, COUNT(*) as count FROM activity_log
            GROUP BY date ORDER BY date"""
        ).fetchall()
    return {r["date"]: r["count"] for r in rows}


@app.get("/api/activity/streak")
def get_streak():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT date FROM activity_log
            WHERE date >= date('now', '-90 days')
            ORDER BY date DESC"""
        ).fetchall()

    active_dates = {r["date"] for r in rows}
    d = datetime.now().date()

    if d.isoformat() not in active_dates:
        d -= timedelta(days=1)

    streak = 0
    while True:
        if d.weekday() >= 5:  # Skip weekends
            d -= timedelta(days=1)
            continue
        if d.isoformat() in active_dates:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return {"streak": streak}


# ── Week Carry-Over ──

@app.post("/api/weeks/next")
async def next_week(request: Request):
    data = await request.json()
    current_week = data.get("currentWeek")
    next_week_key = data.get("nextWeek")
    next_monday = data.get("nextMonday")
    mode = data.get("mode", "work")

    if not current_week or not next_week_key:
        raise HTTPException(400, "currentWeek and nextWeek required")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM weeks WHERE week_key = ? AND mode = ?",
            (next_week_key, mode),
        ).fetchone()
        if existing:
            return {"exists": True, "weekKey": next_week_key}

        rows = conn.execute(
            "SELECT * FROM tasks WHERE week_key = ? AND mode = ? AND status != 'done'",
            (current_week, mode),
        ).fetchall()

        conn.execute(
            "INSERT INTO weeks (week_key, monday_date, mode) VALUES (?, ?, ?)",
            (next_week_key, next_monday, mode),
        )

        old_to_new = {}
        carried = 0

        for row in rows:
            cur = conn.execute(
                """INSERT INTO tasks (week_key, project, title, priority, status,
                    owner, owner_label, due, notes, subtasks, files, depends_on, carried_over, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    next_week_key,
                    row["project"],
                    row["title"],
                    row["priority"],
                    "todo"
                    if row["status"] in ("review", "inprogress", "staging")
                    else row["status"],
                    row["owner"],
                    row["owner_label"],
                    None,
                    row["notes"],
                    row["subtasks"],
                    row["files"],
                    None,
                    mode,
                ),
            )
            old_to_new[row["id"]] = cur.lastrowid
            carried += 1

        for old_id, new_id in old_to_new.items():
            old_row = conn.execute(
                "SELECT depends_on FROM tasks WHERE id = ?", (old_id,)
            ).fetchone()
            if (
                old_row
                and old_row["depends_on"]
                and old_row["depends_on"] in old_to_new
            ):
                conn.execute(
                    "UPDATE tasks SET depends_on = ? WHERE id = ?",
                    (old_to_new[old_row["depends_on"]], new_id),
                )

        conn.commit()
    return {"ok": True, "carried": carried, "weekKey": next_week_key}


# ── Settings ──

DEFAULT_PROJECTS = {
    "work": {
        "dragon": {"label": "Dragon", "color": "#7DBAA3"},
        "raven": {"label": "Raven", "color": "#E8956F"},
        "titan": {"label": "Titan", "color": "#D4A85C"},
        "shadow": {"label": "Shadow", "color": "#8FA4B5"},
        "crown": {"label": "Crown", "color": "#AD8EA5"},
    },
    "personal": {
        "learning": {"label": "Learning", "color": "#8FA4B5"},
        "sideproject": {"label": "Side Projects", "color": "#A0AD78"},
        "health": {"label": "Health", "color": "#7DBAA3"},
        "finance": {"label": "Finance", "color": "#D4A85C"},
        "home": {"label": "Home", "color": "#B89C77"},
    },
}


@app.get("/api/settings")
def get_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = {r["key"]: json.loads(r["value"]) for r in rows}
    # Ensure projects key always exists
    if "projects" not in result:
        result["projects"] = DEFAULT_PROJECTS
    return result


@app.put("/api/settings")
async def update_settings(request: Request):
    data = await request.json()
    key = data.get("key")
    value = data.get("value")
    if not key or value is None:
        raise HTTPException(400, "key and value required")

    with get_db() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, json.dumps(value)),
        )
        conn.commit()
    return {"ok": True, "key": key}


# ── Static files (serve index.html and assets) ──

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


# ── DB Init & Seed ──

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS weeks (
                week_key TEXT NOT NULL,
                monday_date TEXT NOT NULL,
                mode TEXT DEFAULT 'work',
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (week_key, mode)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_key TEXT NOT NULL,
                project TEXT NOT NULL,
                title TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'todo',
                owner TEXT DEFAULT 'me',
                owner_label TEXT DEFAULT 'Me',
                due TEXT,
                notes TEXT DEFAULT '',
                subtasks TEXT DEFAULT '[]',
                files TEXT DEFAULT '[]',
                depends_on INTEGER,
                carried_over INTEGER DEFAULT 0,
                completed_day TEXT,
                mode TEXT DEFAULT 'work',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (week_key, mode) REFERENCES weeks(week_key, mode)
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                project TEXT,
                title TEXT,
                extra TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                author TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'comment',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_week ON tasks(week_key);
            CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(date);
            CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # Migration: add columns if missing
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "files" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN files TEXT DEFAULT '[]'")
        if "mode" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN mode TEXT DEFAULT 'work'")

        # Migration: rebuild weeks table with composite PK if needed
        week_cols = [r[1] for r in conn.execute("PRAGMA table_info(weeks)").fetchall()]
        if "mode" not in week_cols:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                ALTER TABLE weeks RENAME TO weeks_old;
                CREATE TABLE weeks (
                    week_key TEXT NOT NULL,
                    monday_date TEXT NOT NULL,
                    mode TEXT DEFAULT 'work',
                    created_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (week_key, mode)
                );
                INSERT INTO weeks (week_key, monday_date, mode, created_at)
                SELECT week_key, monday_date, 'work', created_at FROM weeks_old;
                DROP TABLE weeks_old;
            """)
            conn.execute("PRAGMA foreign_keys=ON")

        # Migration: fix tasks FK to match composite weeks PK
        fk_info = conn.execute("PRAGMA foreign_key_list(tasks)").fetchall()
        needs_fk_fix = any(
            row[2] == "weeks" and row[4] == "week_key"
            for row in fk_info
            if len([r for r in fk_info if r[2] == "weeks"]) == 1
        )
        if needs_fk_fix:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                ALTER TABLE tasks RENAME TO tasks_old;
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_key TEXT NOT NULL,
                    project TEXT NOT NULL,
                    title TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    status TEXT DEFAULT 'todo',
                    owner TEXT DEFAULT 'me',
                    owner_label TEXT DEFAULT 'Me',
                    due TEXT,
                    notes TEXT DEFAULT '',
                    subtasks TEXT DEFAULT '[]',
                    files TEXT DEFAULT '[]',
                    depends_on INTEGER,
                    carried_over INTEGER DEFAULT 0,
                    completed_day TEXT,
                    mode TEXT DEFAULT 'work',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (week_key, mode) REFERENCES weeks(week_key, mode)
                );
                INSERT INTO tasks SELECT * FROM tasks_old;
                DROP TABLE tasks_old;
            """)
            conn.execute("PRAGMA foreign_keys=ON")

        conn.commit()


def seed_initial_data():
    """Seed the current week with demo tasks if no data exists."""
    with get_db() as conn:
        # Seed default projects if not configured
        existing_settings = conn.execute(
            "SELECT 1 FROM settings WHERE key = 'projects'"
        ).fetchone()
        if not existing_settings:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('projects', ?)",
                (json.dumps(DEFAULT_PROJECTS),),
            )
            conn.commit()

        row = conn.execute("SELECT COUNT(*) as c FROM weeks").fetchone()
        if row["c"] > 0:
            return

        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        week_key = monday.strftime("%G_w%V")
        monday_str = monday.isoformat()

        conn.execute(
            "INSERT INTO weeks (week_key, monday_date, mode) VALUES (?, ?, 'work')",
            (week_key, monday_str),
        )

        initial_tasks = [
            # Dragon — flagship project, 3-task dependency chain (agent-owned)
            ("dragon", "Design API schema for tracker module",
             "high", "todo", "agent", "Agent", "Tue",
             "Define endpoints, data models, and write OpenAPI spec.",
             json.dumps([
                 {"text": "Design REST endpoints", "done": False},
                 {"text": "Define data models", "done": False},
                 {"text": "Write OpenAPI spec", "done": False},
             ]), None),
            ("dragon", "Implement REST endpoints for tracker",
             "high", "todo", "agent", "Agent", "Wed",
             "Scaffold routes, add validation, write integration tests.",
             json.dumps([
                 {"text": "Scaffold route handlers", "done": False},
                 {"text": "Add input validation", "done": False},
                 {"text": "Write integration tests", "done": False},
             ]), 1),
            ("dragon", "Deploy tracker to staging",
             "high", "todo", "agent", "Agent", "Thu",
             "Configure CI pipeline, set env vars, run smoke tests.",
             json.dumps([
                 {"text": "Configure CI pipeline", "done": False},
                 {"text": "Set environment variables", "done": False},
                 {"text": "Run smoke tests", "done": False},
             ]), 2),
            ("dragon", "Review tracker architecture",
             "medium", "todo", "me", "Me", "Fri",
             "Review agent's implementation before merging to main.",
             "[]", None),
            # Raven — communications / messaging
            ("raven", "Set up message queue infrastructure",
             "high", "todo", "agent", "Agent", "Tue",
             "Evaluate queue options, configure broker, add health checks.",
             json.dumps([
                 {"text": "Evaluate queue options", "done": False},
                 {"text": "Configure message broker", "done": False},
                 {"text": "Add health checks", "done": False},
             ]), None),
            ("raven", "Build notification service prototype",
             "medium", "todo", "agent", "Agent", "Wed",
             "Event-driven notifications. Support email and webhook channels.",
             "[]", None),
            ("raven", "Write technical spec for real-time sync",
             "medium", "todo", "me", "Me", "Thu",
             "Document sync protocol, conflict resolution, and fallback strategy.",
             "[]", None),
            # Titan — infrastructure / heavy lifting
            ("titan", "Benchmark database query performance",
             "high", "todo", "agent", "Agent", "Tue",
             "Profile slow queries, add indexes, measure improvement.",
             json.dumps([
                 {"text": "Profile slow queries", "done": False},
                 {"text": "Add missing indexes", "done": False},
                 {"text": "Measure improvement", "done": False},
                 {"text": "Document findings", "done": False},
             ]), None),
            ("titan", "Migrate storage layer to new provider",
             "medium", "todo", "agent", "Agent", "Thu",
             "Write migration script, test rollback, schedule maintenance window.",
             json.dumps([
                 {"text": "Write migration script", "done": False},
                 {"text": "Test rollback procedure", "done": False},
                 {"text": "Schedule maintenance window", "done": False},
             ]), None),
            ("titan", "Capacity planning review",
             "high", "todo", "me", "Me", "Wed",
             "Review current resource utilization and forecast for next quarter.",
             "[]", None),
            # Shadow — security / internal tooling
            ("shadow", "Audit authentication flow",
             "high", "todo", "me", "Me", "Tue",
             "Check token expiry, session handling, and refresh logic.",
             "[]", None),
            ("shadow", "Implement rate limiting middleware",
             "medium", "todo", "agent", "Agent", "Wed",
             "Choose algorithm, add backing store, write load tests.",
             json.dumps([
                 {"text": "Choose rate limiting algorithm", "done": False},
                 {"text": "Add backing store", "done": False},
                 {"text": "Write load tests", "done": False},
             ]), None),
            ("shadow", "Security scan report review",
             "medium", "todo", "team", "Team", "Thu",
             "Review automated scan results with the team.",
             "[]", None),
            # Crown — governance / admin
            ("crown", "Draft project roadmap for next quarter",
             "high", "todo", "me", "Me", "Mon",
             "Gather input from all project leads before drafting.",
             "[]", None),
            ("crown", "Team retrospective and planning session",
             "medium", "todo", "team", "Team", "Wed",
             "Discuss what went well, what to improve, and next sprint goals.",
             "[]", 14),
            ("crown", "Update onboarding documentation",
             "low", "todo", "agent", "Agent", "Fri",
             "Review current docs, add setup guide, add troubleshooting FAQ.",
             json.dumps([
                 {"text": "Review current docs", "done": False},
                 {"text": "Add setup guide", "done": False},
                 {"text": "Add troubleshooting FAQ", "done": False},
             ]), None),
        ]

        for t in initial_tasks:
            conn.execute(
                """INSERT INTO tasks (week_key, project, title, priority, status,
                    owner, owner_label, due, notes, subtasks, depends_on, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'work')""",
                (week_key, *t),
            )
        conn.commit()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8089, log_level="warning")
