#!/usr/bin/env python3
"""Small Council MCP Server — exposes the task board to any MCP-compatible agent."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

BASE_URL = os.environ.get("BOARD_URL", "http://localhost:8089")

mcp = FastMCP(
    name="Small Council",
    instructions=(
        "Task board for agentic workflows. Agents check the queue, claim tasks, "
        "write plans, log progress, and deliver artifacts. Humans review."
    ),
)


# ── Constants ──

VALID_MODES = {"work", "personal"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_STATUSES = {"todo", "inprogress", "blocked", "review", "staging", "done"}
VALID_COMMENT_TYPES = {"comment", "plan", "review", "log", "blocker"}
VALID_OWNERS = {"me", "agent", "team"}
VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri"}

OWNER_LABELS: dict[str, str] = {"me": "Me", "agent": "Agent", "team": "Team"}


# ── Validation ──


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ToolError(f"Invalid {label} '{value}'. Must be one of: {', '.join(sorted(allowed))}")
    return value


# ── Helpers ──


def _api_get(path: str) -> Any:
    """GET request to the board API. Returns parsed JSON."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise ToolError(f"API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ToolError(
            f"Cannot reach board at {BASE_URL}. Is server.py running? ({exc.reason})"
        ) from exc


def _api_post(path: str, data: dict[str, Any], method: str = "POST") -> Any:
    """POST/PUT/DELETE request to the board API. Returns parsed JSON."""
    url = f"{BASE_URL}{path}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise ToolError(f"API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ToolError(
            f"Cannot reach board at {BASE_URL}. Is server.py running? ({exc.reason})"
        ) from exc


def _current_week_key() -> str:
    """ISO week key: YYYY_wNN."""
    return datetime.now().strftime("%G_w%V")


# ── Tools ──


@mcp.tool()
def check_queue() -> list[dict[str, Any]]:
    """Get unclaimed agent tasks (status=todo, owner=agent).

    Call this first to see what work is available.
    """
    return _api_get("/api/tasks/agent-queue")


@mcp.tool()
def claim_task(task_id: int, author: str = "claude") -> dict[str, Any]:
    """Claim a task — sets status to inprogress and creates artifacts dir.

    Args:
        task_id: ID of the task to claim.
        author: Who is claiming (default: claude).
    """
    return _api_post(f"/api/tasks/{task_id}/claim", {"author": author})


@mcp.tool()
def get_task(task_id: int) -> dict[str, Any]:
    """Get full task details including comments and artifacts.

    Args:
        task_id: ID of the task.
    """
    task = _api_get(f"/api/tasks/{task_id}")
    comments = _api_get(f"/api/tasks/{task_id}/comments")
    artifacts = _api_get(f"/api/tasks/{task_id}/artifacts")
    return {**task, "comments": comments, "artifacts": artifacts}


@mcp.tool()
def list_tasks(week: str | None = None, mode: str = "work") -> list[dict[str, Any]]:
    """List all tasks for a given week.

    Args:
        week: Week key (YYYY_wNN). Defaults to current week.
        mode: 'work' or 'personal'. Defaults to 'work'.
    """
    _validate(mode, VALID_MODES, "mode")
    week_key = week or _current_week_key()
    params = urllib.parse.urlencode({"week": week_key, "mode": mode})
    return _api_get(f"/api/tasks?{params}")


@mcp.tool()
def create_task(
    title: str,
    project: str,
    priority: str = "medium",
    owner: str = "agent",
    due: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Create a new task on the board.

    Args:
        title: Task title/description.
        project: Project name (e.g. dragon, raven, titan, shadow, crown).
        priority: low, medium, or high.
        owner: me, agent, or team.
        due: Day of week (Mon-Fri) or None.
        notes: Additional notes.
    """
    _validate(priority, VALID_PRIORITIES, "priority")
    _validate(owner, VALID_OWNERS, "owner")
    if due is not None:
        _validate(due, VALID_DAYS, "due")
    return _api_post(
        "/api/tasks",
        {
            "weekKey": _current_week_key(),
            "title": title,
            "project": project,
            "priority": priority,
            "status": "todo",
            "owner": owner,
            "ownerLabel": OWNER_LABELS.get(owner, owner),
            "due": due,
            "notes": notes,
        },
    )


@mcp.tool()
def update_task(
    task_id: int,
    status: str | None = None,
    title: str | None = None,
    priority: str | None = None,
    notes: str | None = None,
    due: str | None = None,
) -> dict[str, Any]:
    """Update task fields.

    Args:
        task_id: ID of the task.
        status: New status (todo, inprogress, blocked, review, staging, done).
        title: New title.
        priority: New priority (low, medium, high).
        notes: Updated notes.
        due: Day of week (Mon-Fri).
    """
    if status is not None:
        _validate(status, VALID_STATUSES, "status")
    if priority is not None:
        _validate(priority, VALID_PRIORITIES, "priority")
    if due is not None:
        _validate(due, VALID_DAYS, "due")
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if title is not None:
        payload["title"] = title
    if priority is not None:
        payload["priority"] = priority
    if notes is not None:
        payload["notes"] = notes
    if due is not None:
        payload["due"] = due
    if not payload:
        raise ToolError("Provide at least one field to update.")
    return _api_post(f"/api/tasks/{task_id}", payload, method="PUT")


@mcp.tool()
def add_comment(
    task_id: int,
    content: str,
    comment_type: str = "log",
    author: str = "claude",
) -> dict[str, Any]:
    """Add a comment to a task's thread.

    Args:
        task_id: ID of the task.
        content: Comment text.
        comment_type: One of: comment, plan, review, log, blocker.
        author: Who is commenting (default: claude).
    """
    _validate(comment_type, VALID_COMMENT_TYPES, "comment_type")
    return _api_post(
        f"/api/tasks/{task_id}/comments",
        {"author": author, "content": content, "type": comment_type},
    )


@mcp.tool()
def complete_task(
    task_id: int,
    summary: str,
    author: str = "claude",
) -> dict[str, Any]:
    """Mark a task as complete — posts summary comment, moves to review, logs activity.

    Not atomic: if the status update succeeds but activity logging fails,
    the task will be in review but the activity won't be recorded.

    Args:
        task_id: ID of the task.
        summary: Summary of what was done.
        author: Who completed it (default: claude).
    """
    # Post completion comment
    _api_post(
        f"/api/tasks/{task_id}/comments",
        {"author": author, "content": summary, "type": "review"},
    )

    # Move to review
    task = _api_post(f"/api/tasks/{task_id}", {"status": "review"}, method="PUT")

    # Log activity (best-effort — losing telemetry is acceptable)
    now = datetime.now()
    try:
        _api_post(
            "/api/activity",
            {
                "ts": int(now.timestamp() * 1000),
                "date": now.strftime("%Y-%m-%d"),
                "type": "complete",
                "project": task.get("project", ""),
                "title": task.get("title", ""),
            },
        )
    except ToolError:
        pass

    return task


# ── Entry point ──

if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8090)
    else:
        mcp.run(transport="stdio")
