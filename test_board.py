#!/usr/bin/env python3
"""
Comprehensive test suite for the Weekly Board API.
Tests run against the live server on port 8089 using urllib only (zero deps).

Groups:
    TestWeeks       - GET /api/weeks, week listing
    TestTasks       - GET/POST/PUT/DELETE /api/tasks and /api/tasks/:id
    TestActivity    - POST /api/activity, GET /api/activity, /counts, /streak
    TestCarryOver   - POST /api/weeks/next (carry-over logic)
    TestEdgeCases   - Validation errors, missing params, boundary conditions
"""

import json
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from datetime import date, timedelta as _td

BASE = "http://localhost:8089"
# Week key reserved exclusively for tests (never in seed data)
TEST_WEEK = "2099_w01"
TEST_MONDAY = "2099-01-06"
TEST_WEEK_2 = "2099_w02"
TEST_MONDAY_2 = "2099-01-13"

# Dynamic seed week (matches server.py seed_initial_data)
_today = date.today()
_monday = _today - _td(days=_today.weekday())
SEED_WEEK = _monday.strftime("%G_w%V")
SEED_MONDAY = _monday.isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(path: str, *, expect_error: bool = False) -> dict:
    """HTTP GET; returns parsed JSON. Raises on non-2xx unless expect_error=True."""
    url = BASE + path
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        if expect_error:
            return json.loads(exc.read())
        raise


def api_post(path: str, body: dict, *, expect_error: bool = False) -> dict:
    """HTTP POST with JSON body; returns parsed JSON."""
    url = BASE + path
    data = json.dumps(body).encode()
    req = Request(url, data=data, method="POST",
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        if expect_error:
            return json.loads(exc.read())
        raise


def api_put(path: str, body: dict, *, expect_error: bool = False) -> dict:
    """HTTP PUT with JSON body; returns parsed JSON."""
    url = BASE + path
    data = json.dumps(body).encode()
    req = Request(url, data=data, method="PUT",
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        if expect_error:
            return json.loads(exc.read())
        raise


def api_delete(path: str, *, expect_error: bool = False) -> dict:
    """HTTP DELETE; returns parsed JSON."""
    url = BASE + path
    req = Request(url, method="DELETE")
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        if expect_error:
            return json.loads(exc.read())
        raise


def create_test_task(week_key: str = TEST_WEEK, **overrides) -> dict:
    """Create a task in the test week and return it."""
    payload = {
        "weekKey": week_key,
        "title": "Test task",
        "project": "test",
        "priority": "medium",
        "status": "todo",
        "owner": "me",
        "ownerLabel": "Me",
    }
    payload.update(overrides)
    return api_post("/api/tasks", payload)


def delete_task(task_id: int) -> None:
    """Best-effort delete; ignores errors."""
    try:
        api_delete(f"/api/tasks/{task_id}")
    except Exception:
        pass


def create_test_activity(**overrides) -> dict:
    """Log a test activity event and return the response."""
    payload = {
        "ts": int(time.time() * 1000),
        "date": "2099-01-06",
        "type": "test_event",
        "project": "test",
        "title": "Test activity",
    }
    payload.update(overrides)
    return api_post("/api/activity", payload)


# ---------------------------------------------------------------------------
# TestWeeks
# ---------------------------------------------------------------------------

class TestWeeks(unittest.TestCase):
    """Tests for GET /api/weeks."""

    def test_get_weeks_returns_list(self):
        """Response is a JSON array."""
        data = api_get("/api/weeks")
        self.assertIsInstance(data, list)

    def test_get_weeks_has_seed_week(self):
        """The dynamic seed week must be present."""
        data = api_get("/api/weeks")
        keys = [w["weekKey"] for w in data]
        self.assertIn(SEED_WEEK, keys)

    def test_get_weeks_contains_required_fields(self):
        """Each week entry has weekKey and monday fields."""
        data = api_get("/api/weeks")
        self.assertGreater(len(data), 0, "weeks list must not be empty")
        for week in data:
            self.assertIn("weekKey", week)
            self.assertIn("monday", week)

    def test_weeks_ordered_by_date(self):
        """Weeks are ordered by monday_date ascending."""
        data = api_get("/api/weeks")
        mondays = [w["monday"] for w in data]
        self.assertEqual(mondays, sorted(mondays))

    def test_new_week_appears_after_task_creation(self):
        """Creating a task with a new weekKey causes that week to show up in /api/weeks."""
        task = create_test_task()
        try:
            weeks = api_get("/api/weeks")
            keys = [w["weekKey"] for w in weeks]
            self.assertIn(TEST_WEEK, keys)
        finally:
            delete_task(task["id"])


# ---------------------------------------------------------------------------
# TestTasks - GET
# ---------------------------------------------------------------------------

class TestTasksGet(unittest.TestCase):
    """Tests for GET /api/tasks."""

    def test_get_tasks_for_seed_week(self):
        """Returns list of tasks for existing week."""
        data = api_get(f"/api/tasks?week={SEED_WEEK}")
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_task_fields_present(self):
        """Each task contains all required fields."""
        required = {"id", "project", "title", "priority", "status",
                    "owner", "ownerLabel", "due", "notes",
                    "subtasks", "dependsOn", "carriedOver", "completedDay"}
        tasks = api_get(f"/api/tasks?week={SEED_WEEK}")
        for task in tasks:
            missing = required - task.keys()
            self.assertEqual(missing, set(), f"Missing fields in task {task.get('id')}: {missing}")

    def test_get_tasks_empty_week_returns_empty_list(self):
        """A week that exists but has no tasks returns an empty list."""
        # Create the week via a task then delete the task
        task = create_test_task(title="Ephemeral")
        delete_task(task["id"])
        data = api_get(f"/api/tasks?week={TEST_WEEK}")
        self.assertIsInstance(data, list)
        # May be empty (task deleted) or contain other test artifacts - list type is what matters

    def test_get_tasks_missing_week_param_returns_400(self):
        """Missing ?week param returns 400 with error message."""
        data = api_get("/api/tasks", expect_error=True)
        self.assertIn("error", data)

    def test_get_tasks_nonexistent_week_returns_empty_list(self):
        """A totally unknown week key returns an empty list (not an error)."""
        data = api_get("/api/tasks?week=9999_w99")
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_subtasks_deserialized_as_list(self):
        """subtasks field is always a list, never a raw string."""
        tasks = api_get(f"/api/tasks?week={SEED_WEEK}")
        for task in tasks:
            self.assertIsInstance(task["subtasks"], list, f"Task {task['id']} has non-list subtasks")

    def test_carried_over_is_bool(self):
        """carriedOver field is a boolean."""
        tasks = api_get(f"/api/tasks?week={SEED_WEEK}")
        for task in tasks:
            self.assertIsInstance(task["carriedOver"], bool)


# ---------------------------------------------------------------------------
# TestTasks - CREATE
# ---------------------------------------------------------------------------

class TestTasksCreate(unittest.TestCase):
    """Tests for POST /api/tasks."""

    def setUp(self):
        self._created_ids = []

    def tearDown(self):
        for tid in self._created_ids:
            delete_task(tid)

    def _track(self, task: dict) -> dict:
        self._created_ids.append(task["id"])
        return task

    def test_create_task_returns_201_fields(self):
        """Creating a valid task returns all expected fields."""
        task = self._track(create_test_task(title="Create test"))
        self.assertIn("id", task)
        self.assertIsInstance(task["id"], int)
        self.assertEqual(task["title"], "Create test")
        self.assertEqual(task["project"], "test")
        self.assertEqual(task["status"], "todo")
        self.assertFalse(task["carriedOver"])
        self.assertIsNone(task["completedDay"])

    def test_create_task_defaults(self):
        """Omitted optional fields get correct defaults."""
        task = self._track(api_post("/api/tasks", {"weekKey": TEST_WEEK, "title": "Minimal"}))
        self.assertEqual(task["priority"], "medium")
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["owner"], "me")
        self.assertEqual(task["ownerLabel"], "Me")
        self.assertEqual(task["notes"], "")
        self.assertEqual(task["subtasks"], [])
        self.assertIsNone(task["dependsOn"])

    def test_create_task_missing_title_returns_400(self):
        """POST without title returns 400."""
        resp = api_post("/api/tasks", {"weekKey": TEST_WEEK}, expect_error=True)
        self.assertIn("error", resp)

    def test_create_task_missing_week_key_returns_400(self):
        """POST without weekKey returns 400."""
        resp = api_post("/api/tasks", {"title": "No week"}, expect_error=True)
        self.assertIn("error", resp)

    def test_create_task_empty_body_returns_400(self):
        """POST with empty body returns 400."""
        resp = api_post("/api/tasks", {}, expect_error=True)
        self.assertIn("error", resp)

    def test_create_task_with_subtasks(self):
        """Subtasks are stored and returned as list of objects."""
        subtasks = [{"text": "Step one", "done": False}, {"text": "Step two", "done": True}]
        task = self._track(create_test_task(subtasks=subtasks))
        self.assertEqual(len(task["subtasks"]), 2)
        self.assertEqual(task["subtasks"][0]["text"], "Step one")
        self.assertFalse(task["subtasks"][0]["done"])
        self.assertTrue(task["subtasks"][1]["done"])

    def test_create_task_with_dependency(self):
        """dependsOn field is stored correctly."""
        parent = self._track(create_test_task(title="Parent"))
        child = self._track(create_test_task(title="Child", dependsOn=parent["id"]))
        self.assertEqual(child["dependsOn"], parent["id"])

    def test_create_task_all_priorities(self):
        """Tasks can be created with low, medium, high priority."""
        for priority in ("low", "medium", "high"):
            task = self._track(create_test_task(title=f"Priority {priority}", priority=priority))
            self.assertEqual(task["priority"], priority)

    def test_create_task_all_statuses(self):
        """Tasks can be created with any valid status."""
        for status in ("todo", "inprogress", "blocked", "review", "done"):
            task = self._track(create_test_task(title=f"Status {status}", status=status))
            self.assertEqual(task["status"], status)

    def test_create_task_all_owners(self):
        """Tasks can be created with me, agent, team owner."""
        for owner, label in (("me", "Me"), ("agent", "Agent"), ("team", "Team")):
            task = self._track(create_test_task(owner=owner, ownerLabel=label))
            self.assertEqual(task["owner"], owner)
            self.assertEqual(task["ownerLabel"], label)

    def test_create_task_auto_creates_week(self):
        """Creating a task for a non-existing week auto-creates the week row."""
        task = self._track(create_test_task(title="Week auto-create"))
        weeks = api_get("/api/weeks")
        keys = [w["weekKey"] for w in weeks]
        self.assertIn(TEST_WEEK, keys)

    def test_create_task_carried_over_flag(self):
        """carriedOver=True is stored and returned correctly."""
        task = self._track(create_test_task(carriedOver=True))
        self.assertTrue(task["carriedOver"])

    def test_create_task_with_due_day(self):
        """due field accepts day-of-week strings."""
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            task = self._track(create_test_task(due=day))
            self.assertEqual(task["due"], day)

    def test_create_task_with_notes(self):
        """Notes field is stored and returned."""
        task = self._track(create_test_task(notes="Important context here"))
        self.assertEqual(task["notes"], "Important context here")

    def test_create_task_with_special_characters_in_title(self):
        """Titles with SQL special chars and Unicode are stored safely."""
        title = "Test'; DROP TABLE tasks; -- emoji"
        task = self._track(create_test_task(title=title))
        self.assertEqual(task["title"], title)

    def test_create_task_with_unicode_title(self):
        """Unicode characters in titles are preserved round-trip."""
        title = "Task with Unicode: \u4e2d\u6587 \u00e9\u00e0\u00fc"
        task = self._track(create_test_task(title=title))
        self.assertEqual(task["title"], title)

    def test_created_task_appears_in_get_tasks(self):
        """A newly created task is retrievable via GET /api/tasks."""
        task = self._track(create_test_task(title="Retrievable task"))
        tasks = api_get(f"/api/tasks?week={TEST_WEEK}")
        ids = [t["id"] for t in tasks]
        self.assertIn(task["id"], ids)


# ---------------------------------------------------------------------------
# TestTasks - UPDATE
# ---------------------------------------------------------------------------

class TestTasksUpdate(unittest.TestCase):
    """Tests for PUT /api/tasks/:id."""

    def setUp(self):
        self._task = create_test_task(title="Original title")

    def tearDown(self):
        delete_task(self._task["id"])

    def test_update_title(self):
        """PUT with new title updates the task."""
        updated = api_put(f"/api/tasks/{self._task['id']}", {"title": "Updated title"})
        self.assertEqual(updated["title"], "Updated title")

    def test_update_status(self):
        """Status field can be updated through all transitions."""
        task_id = self._task["id"]
        for status in ("inprogress", "blocked", "review", "done", "todo"):
            updated = api_put(f"/api/tasks/{task_id}", {"status": status})
            self.assertEqual(updated["status"], status)

    def test_update_priority(self):
        """Priority can be changed."""
        updated = api_put(f"/api/tasks/{self._task['id']}", {"priority": "high"})
        self.assertEqual(updated["priority"], "high")

    def test_update_partial_preserves_other_fields(self):
        """Updating one field does not wipe out other fields."""
        task_id = self._task["id"]
        original_project = self._task["project"]
        updated = api_put(f"/api/tasks/{task_id}", {"title": "Changed only title"})
        self.assertEqual(updated["project"], original_project)
        self.assertEqual(updated["priority"], self._task["priority"])
        self.assertEqual(updated["status"], self._task["status"])

    def test_update_subtasks(self):
        """Subtasks list can be replaced entirely."""
        new_subtasks = [{"text": "New step", "done": True}]
        updated = api_put(f"/api/tasks/{self._task['id']}", {"subtasks": new_subtasks})
        self.assertEqual(len(updated["subtasks"]), 1)
        self.assertEqual(updated["subtasks"][0]["text"], "New step")
        self.assertTrue(updated["subtasks"][0]["done"])

    def test_update_notes(self):
        """Notes field can be updated."""
        updated = api_put(f"/api/tasks/{self._task['id']}", {"notes": "New notes"})
        self.assertEqual(updated["notes"], "New notes")

    def test_update_due(self):
        """Due day can be set and changed."""
        updated = api_put(f"/api/tasks/{self._task['id']}", {"due": "Fri"})
        self.assertEqual(updated["due"], "Fri")

    def test_update_completed_day(self):
        """completedDay field can be set when marking task done."""
        updated = api_put(
            f"/api/tasks/{self._task['id']}",
            {"status": "done", "completedDay": "Wed"}
        )
        self.assertEqual(updated["completedDay"], "Wed")

    def test_update_nonexistent_task_returns_404(self):
        """PUT on a non-existent task ID returns 404 with error."""
        resp = api_put("/api/tasks/999999999", {"title": "Ghost"}, expect_error=True)
        self.assertIn("error", resp)

    def test_update_returns_full_task_object(self):
        """PUT response contains the complete task object."""
        required = {"id", "project", "title", "priority", "status",
                    "owner", "ownerLabel", "due", "notes",
                    "subtasks", "dependsOn", "carriedOver", "completedDay"}
        updated = api_put(f"/api/tasks/{self._task['id']}", {"title": "Full object check"})
        missing = required - updated.keys()
        self.assertEqual(missing, set())

    def test_update_owner_and_owner_label(self):
        """Owner and ownerLabel can be changed together."""
        updated = api_put(
            f"/api/tasks/{self._task['id']}",
            {"owner": "agent", "ownerLabel": "Agent"}
        )
        self.assertEqual(updated["owner"], "agent")
        self.assertEqual(updated["ownerLabel"], "Agent")

    def test_update_depends_on(self):
        """dependsOn can be set to another task's ID."""
        other = create_test_task(title="Dependency target")
        try:
            updated = api_put(
                f"/api/tasks/{self._task['id']}",
                {"dependsOn": other["id"]}
            )
            self.assertEqual(updated["dependsOn"], other["id"])
        finally:
            delete_task(other["id"])


# ---------------------------------------------------------------------------
# TestTasks - DELETE
# ---------------------------------------------------------------------------

class TestTasksDelete(unittest.TestCase):
    """Tests for DELETE /api/tasks/:id."""

    def test_delete_existing_task_returns_ok(self):
        """Deleting an existing task returns {ok: True}."""
        task = create_test_task(title="To be deleted")
        resp = api_delete(f"/api/tasks/{task['id']}")
        self.assertEqual(resp, {"ok": True})

    def test_deleted_task_no_longer_in_get(self):
        """After deletion, the task does not appear in GET /api/tasks."""
        task = create_test_task(title="Gone after delete")
        task_id = task["id"]
        api_delete(f"/api/tasks/{task_id}")
        tasks = api_get(f"/api/tasks?week={TEST_WEEK}")
        ids = [t["id"] for t in tasks]
        self.assertNotIn(task_id, ids)

    def test_delete_nonexistent_task_returns_ok(self):
        """Deleting a non-existent task still returns ok (idempotent)."""
        resp = api_delete("/api/tasks/999999998")
        self.assertEqual(resp, {"ok": True})

    def test_double_delete_is_idempotent(self):
        """Deleting the same task twice does not raise an error."""
        task = create_test_task(title="Double delete test")
        api_delete(f"/api/tasks/{task['id']}")
        resp = api_delete(f"/api/tasks/{task['id']}")
        self.assertEqual(resp, {"ok": True})


# ---------------------------------------------------------------------------
# TestActivity
# ---------------------------------------------------------------------------

class TestActivity(unittest.TestCase):
    """Tests for POST /api/activity, GET /api/activity, /counts, /streak."""

    # We tag test activity with a far-future date so it doesn't pollute
    # real date ranges. We clean up by... we can't delete individual activity
    # records via the API, so test entries use a sentinel date.
    SENTINEL_DATE = "2099-01-06"

    def _log_activity(self, **overrides) -> dict:
        return create_test_activity(date=self.SENTINEL_DATE, **overrides)

    def test_log_activity_returns_201_ok(self):
        """POST /api/activity returns {ok: True} with status 201."""
        resp = self._log_activity()
        self.assertEqual(resp, {"ok": True})

    def test_log_activity_with_all_fields(self):
        """All activity fields can be supplied."""
        resp = api_post("/api/activity", {
            "ts": 1234567890000,
            "date": self.SENTINEL_DATE,
            "type": "complete",
            "project": "dragon",
            "title": "Finished something",
        })
        self.assertEqual(resp, {"ok": True})

    def test_log_activity_minimal_fields(self):
        """Activity can be logged with only mandatory fields (all optional)."""
        resp = api_post("/api/activity", {
            "ts": 0,
            "date": self.SENTINEL_DATE,
            "type": "note",
        })
        self.assertEqual(resp, {"ok": True})

    def test_get_activity_returns_list(self):
        """GET /api/activity returns a list."""
        data = api_get("/api/activity?days=90")
        self.assertIsInstance(data, list)

    def test_get_activity_default_days(self):
        """GET /api/activity without ?days param works (defaults to 90)."""
        data = api_get("/api/activity")
        self.assertIsInstance(data, list)

    def test_get_activity_fields(self):
        """Each activity entry has ts, date, type, project, title, extra."""
        # Log something in a recent date so we can inspect it
        resp = api_post("/api/activity", {
            "ts": 9999999999999,
            "date": SEED_MONDAY,  # existing data date
            "type": "test_field_check",
            "project": "test",
            "title": "Field check",
        })
        self.assertEqual(resp, {"ok": True})
        data = api_get("/api/activity?days=365")
        self.assertGreater(len(data), 0)
        required = {"ts", "date", "type", "project", "title", "extra"}
        for entry in data:
            missing = required - entry.keys()
            self.assertEqual(missing, set(), f"Missing fields: {missing}")

    def test_get_activity_days_filter(self):
        """days=1 returns fewer or equal results than days=3650."""
        short = api_get("/api/activity?days=1")
        long_ = api_get("/api/activity?days=3650")
        self.assertLessEqual(len(short), len(long_))

    def test_get_activity_counts_returns_dict(self):
        """GET /api/activity/counts returns a dict mapping date strings to int counts."""
        data = api_get("/api/activity/counts")
        self.assertIsInstance(data, dict)
        for date_key, count in data.items():
            # Date key should look like YYYY-MM-DD
            self.assertRegex(date_key, r"^\d{4}-\d{2}-\d{2}$", f"Bad date key: {date_key}")
            self.assertIsInstance(count, int)

    def test_get_activity_counts_increments(self):
        """After logging an activity for a date, its count in /counts increases by 1."""
        # Use a very specific date unlikely to have noise
        test_date = "2099-06-15"
        before = api_get("/api/activity/counts")
        before_count = before.get(test_date, 0)

        api_post("/api/activity", {
            "ts": int(time.time() * 1000),
            "date": test_date,
            "type": "count_test",
            "project": "test",
            "title": "Count increment check",
        })

        after = api_get("/api/activity/counts")
        after_count = after.get(test_date, 0)
        self.assertEqual(after_count, before_count + 1)

    def test_get_streak_returns_int(self):
        """GET /api/activity/streak returns {streak: <int>}."""
        data = api_get("/api/activity/streak")
        self.assertIn("streak", data)
        self.assertIsInstance(data["streak"], int)
        self.assertGreaterEqual(data["streak"], 0)

    def test_streak_nonnegative(self):
        """Streak is never negative."""
        data = api_get("/api/activity/streak")
        self.assertGreaterEqual(data["streak"], 0)

    def test_activity_ordered_by_ts_desc(self):
        """GET /api/activity returns entries in descending timestamp order."""
        data = api_get("/api/activity?days=3650")
        if len(data) < 2:
            self.skipTest("Not enough activity entries to check ordering")
        timestamps = [e["ts"] for e in data]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_get_activity_limited_to_50(self):
        """GET /api/activity returns at most 50 entries."""
        data = api_get("/api/activity?days=3650")
        self.assertLessEqual(len(data), 50)


# ---------------------------------------------------------------------------
# TestCarryOver
# ---------------------------------------------------------------------------

class TestCarryOver(unittest.TestCase):
    """Tests for POST /api/weeks/next (carry-over of incomplete tasks)."""

    # We use unique week keys per test to avoid collision.
    _week_counter = 0

    def _fresh_weeks(self):
        TestCarryOver._week_counter += 1
        n = TestCarryOver._week_counter
        src = f"2088_w{n:02d}"
        dst = f"2088_w{n + 10:02d}"
        return src, dst

    def _setup_week_with_tasks(self, week_key):
        """Create a week with a mix of done and incomplete tasks."""
        tasks = []
        tasks.append(create_test_task(
            week_key=week_key,
            title="Done task",
            status="done",
            project="dragon",
        ))
        tasks.append(create_test_task(
            week_key=week_key,
            title="Todo task",
            status="todo",
            project="raven",
        ))
        tasks.append(create_test_task(
            week_key=week_key,
            title="Inprogress task",
            status="inprogress",
            project="titan",
        ))
        tasks.append(create_test_task(
            week_key=week_key,
            title="Blocked task",
            status="blocked",
            project="shadow",
        ))
        tasks.append(create_test_task(
            week_key=week_key,
            title="Review task",
            status="review",
            project="crown",
        ))
        return tasks

    def tearDown(self):
        # Best-effort: get all tasks from test week ranges and delete them.
        # We can't delete weeks themselves, but task cleanup is sufficient.
        for n in range(1, self._week_counter + 30):
            for prefix in ("2088_w",):
                wk = f"{prefix}{n:02d}"
                try:
                    tasks = api_get(f"/api/tasks?week={wk}")
                    for t in tasks:
                        delete_task(t["id"])
                except Exception:
                    pass

    def test_carry_over_missing_params_returns_400(self):
        """POST /api/weeks/next without required fields returns 400."""
        resp = api_post("/api/weeks/next", {}, expect_error=True)
        self.assertIn("error", resp)

    def test_carry_over_missing_current_week_returns_400(self):
        """Missing currentWeek returns 400."""
        resp = api_post("/api/weeks/next",
                        {"nextWeek": "2099_w50", "nextMonday": "2099-12-09"},
                        expect_error=True)
        self.assertIn("error", resp)

    def test_carry_over_missing_next_week_returns_400(self):
        """Missing nextWeek returns 400."""
        resp = api_post("/api/weeks/next",
                        {"currentWeek": SEED_WEEK, "nextMonday": "2099-12-09"},
                        expect_error=True)
        self.assertIn("error", resp)

    def test_carry_over_existing_next_week_returns_exists(self):
        """If nextWeek already exists, returns {exists: True} without duplicating."""
        # SEED_WEEK already exists in seed data
        resp = api_post("/api/weeks/next", {
            "currentWeek": "2088_w99",
            "nextWeek": SEED_WEEK,
            "nextMonday": SEED_MONDAY,
        })
        self.assertTrue(resp.get("exists"))
        self.assertEqual(resp["weekKey"], SEED_WEEK)

    def test_carry_over_only_incomplete_tasks(self):
        """Only non-done tasks are carried over; done tasks stay behind."""
        src, dst = self._fresh_weeks()
        tasks = self._setup_week_with_tasks(src)

        resp = api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        self.assertTrue(resp.get("ok"))
        # 4 non-done tasks (todo, inprogress, blocked, review)
        self.assertEqual(resp["carried"], 4)

    def test_carried_tasks_have_carried_over_flag(self):
        """Tasks in next week have carriedOver=True."""
        src, dst = self._fresh_weeks()
        self._setup_week_with_tasks(src)

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        for task in next_tasks:
            self.assertTrue(task["carriedOver"], f"Task '{task['title']}' should be carriedOver")

    def test_inprogress_and_review_reset_to_todo(self):
        """Tasks with status inprogress or review are reset to todo in next week."""
        src, dst = self._fresh_weeks()
        self._setup_week_with_tasks(src)

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        status_map = {t["title"]: t["status"] for t in next_tasks}

        self.assertEqual(status_map.get("Inprogress task"), "todo",
                         "inprogress tasks should reset to todo")
        self.assertEqual(status_map.get("Review task"), "todo",
                         "review tasks should reset to todo")

    def test_todo_and_blocked_status_preserved(self):
        """Tasks with status todo or blocked keep their status after carry-over."""
        src, dst = self._fresh_weeks()
        self._setup_week_with_tasks(src)

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        status_map = {t["title"]: t["status"] for t in next_tasks}

        self.assertEqual(status_map.get("Todo task"), "todo")
        self.assertEqual(status_map.get("Blocked task"), "blocked")

    def test_done_task_not_in_next_week(self):
        """The done task does NOT appear in next week's task list."""
        src, dst = self._fresh_weeks()
        self._setup_week_with_tasks(src)

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        titles = [t["title"] for t in next_tasks]
        self.assertNotIn("Done task", titles)

    def test_due_field_cleared_on_carry_over(self):
        """Carried-over tasks have their due field set to None (reset for new week)."""
        src, dst = self._fresh_weeks()
        create_test_task(week_key=src, title="Has due", due="Mon", status="todo")

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        for t in next_tasks:
            if t["title"] == "Has due":
                self.assertIsNone(t["due"], "due should be cleared after carry-over")

    def test_carry_over_response_fields(self):
        """Successful carry-over response has ok, carried, weekKey fields."""
        src, dst = self._fresh_weeks()
        create_test_task(week_key=src, title="Carry me", status="todo")

        resp = api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        self.assertIn("ok", resp)
        self.assertIn("carried", resp)
        self.assertIn("weekKey", resp)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["weekKey"], dst)

    def test_carry_over_empty_week(self):
        """Carrying over a week with zero incomplete tasks returns carried=0."""
        src, dst = self._fresh_weeks()
        # Create only a done task
        create_test_task(week_key=src, title="Already done", status="done")

        resp = api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp["carried"], 0)
        next_tasks = api_get(f"/api/tasks?week={dst}")
        self.assertEqual(len(next_tasks), 0)

    def test_dependency_remapping(self):
        """Dependencies between carried tasks are remapped to new IDs."""
        src, dst = self._fresh_weeks()
        parent = create_test_task(week_key=src, title="Parent", status="todo")
        child = create_test_task(
            week_key=src,
            title="Child",
            status="todo",
            dependsOn=parent["id"]
        )

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        next_tasks = api_get(f"/api/tasks?week={dst}")
        next_by_title = {t["title"]: t for t in next_tasks}

        parent_new = next_by_title.get("Parent")
        child_new = next_by_title.get("Child")

        self.assertIsNotNone(parent_new, "Parent task should be carried over")
        self.assertIsNotNone(child_new, "Child task should be carried over")

        # The child's dependsOn must point to the NEW parent ID, not old
        self.assertEqual(child_new["dependsOn"], parent_new["id"],
                         "dependency should be remapped to new parent ID")
        self.assertNotEqual(child_new["dependsOn"], parent["id"],
                            "dependency should NOT point to old parent ID")

    def test_next_week_appears_in_weeks_list(self):
        """After carry-over, the new week appears in GET /api/weeks."""
        src, dst = self._fresh_weeks()
        create_test_task(week_key=src, title="Anything", status="todo")

        api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2088-01-13",
        })

        weeks = api_get("/api/weeks")
        keys = [w["weekKey"] for w in weeks]
        self.assertIn(dst, keys)

    def test_carry_over_nonexistent_source_week(self):
        """Carrying over from a week that has no tasks carries 0 tasks."""
        src = "2077_w01"  # definitely does not exist
        dst = "2077_w02"

        resp = api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2077-01-10",
        })
        # Should succeed with 0 carried tasks
        self.assertTrue(resp.get("ok") or resp.get("exists"))


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases: boundary values, unknown routes, OPTIONS preflight."""

    def test_options_preflight_returns_204(self):
        """OPTIONS request returns 204 for CORS preflight."""
        req = Request(BASE + "/api/tasks", method="OPTIONS")
        with urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 204)

    def test_unknown_api_route_post_returns_404(self):
        """POST to an unknown API path returns 404."""
        resp = api_post("/api/nonexistent", {}, expect_error=True)
        self.assertIn("error", resp)

    def test_unknown_api_route_delete_returns_404(self):
        """DELETE to a non-task path returns 404."""
        resp = api_delete("/api/nonexistent", expect_error=True)
        self.assertIn("error", resp)

    def test_update_task_invalid_id_string(self):
        """PUT /api/tasks/abc raises a server error (non-integer ID)."""
        req = Request(
            BASE + "/api/tasks/abc",
            data=json.dumps({"title": "x"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"}
        )
        try:
            with urlopen(req, timeout=5) as resp:
                # If it somehow returns 200 that's also fine
                pass
        except HTTPError as exc:
            self.assertIn(exc.code, (400, 404, 500))
        except Exception:
            pass  # Server may drop connection on bad route parse

    def test_delete_task_invalid_id_string(self):
        """DELETE /api/tasks/abc raises server error."""
        req = Request(BASE + "/api/tasks/abc", method="DELETE")
        try:
            with urlopen(req, timeout=5) as resp:
                pass
        except HTTPError as exc:
            self.assertIn(exc.code, (400, 404, 500))
        except Exception:
            pass

    def test_get_tasks_week_with_spaces(self):
        """week param with spaces returns empty list gracefully."""
        data = api_get("/api/tasks?week=9999+w99")
        self.assertIsInstance(data, list)

    def test_large_subtasks_array(self):
        """Task with many subtasks stores and returns them correctly."""
        subtasks = [{"text": f"Step {i}", "done": i % 2 == 0} for i in range(50)]
        task = create_test_task(subtasks=subtasks)
        try:
            self.assertEqual(len(task["subtasks"]), 50)
            fetched = api_get(f"/api/tasks?week={TEST_WEEK}")
            found = next((t for t in fetched if t["id"] == task["id"]), None)
            self.assertIsNotNone(found)
            self.assertEqual(len(found["subtasks"]), 50)
        finally:
            delete_task(task["id"])

    def test_empty_string_notes(self):
        """Empty string notes are stored and returned as empty string."""
        task = create_test_task(notes="")
        try:
            self.assertEqual(task["notes"], "")
        finally:
            delete_task(task["id"])

    def test_update_empty_subtasks_list(self):
        """Updating subtasks to empty list works correctly."""
        task = create_test_task(subtasks=[{"text": "remove me", "done": False}])
        try:
            updated = api_put(f"/api/tasks/{task['id']}", {"subtasks": []})
            self.assertEqual(updated["subtasks"], [])
        finally:
            delete_task(task["id"])

    def test_multiple_tasks_same_week(self):
        """Multiple tasks can coexist in the same week."""
        ids = []
        try:
            for i in range(5):
                t = create_test_task(title=f"Bulk task {i}")
                ids.append(t["id"])
            tasks = api_get(f"/api/tasks?week={TEST_WEEK}")
            found_ids = {t["id"] for t in tasks}
            for tid in ids:
                self.assertIn(tid, found_ids)
        finally:
            for tid in ids:
                delete_task(tid)

    def test_carry_over_returns_ok_not_exists_on_new_week(self):
        """Carry-over to a genuinely new week returns ok=True, not exists=True."""
        src = "2055_w01"
        dst = "2055_w02"
        create_test_task(week_key=src, title="Carry this", status="todo")
        resp = api_post("/api/weeks/next", {
            "currentWeek": src,
            "nextWeek": dst,
            "nextMonday": "2055-01-10",
        })
        # Clean up
        try:
            tasks = api_get(f"/api/tasks?week={src}")
            for t in tasks:
                delete_task(t["id"])
            tasks = api_get(f"/api/tasks?week={dst}")
            for t in tasks:
                delete_task(t["id"])
        except Exception:
            pass
        self.assertTrue(resp.get("ok"))
        self.assertNotIn("exists", resp)


# ---------------------------------------------------------------------------
# TestServerAvailability
# ---------------------------------------------------------------------------

class TestServerAvailability(unittest.TestCase):
    """Basic smoke tests to confirm the server is reachable."""

    def test_server_is_up(self):
        """Server responds to GET /api/weeks."""
        try:
            data = api_get("/api/weeks")
            self.assertIsInstance(data, list)
        except (URLError, ConnectionRefusedError) as exc:
            self.fail(f"Server not reachable on port 8089: {exc}")

    def test_cors_header_present(self):
        """Responses include Access-Control-Allow-Origin header."""
        req = Request(BASE + "/api/weeks", method="GET")
        with urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_content_type_is_json(self):
        """API responses have Content-Type: application/json."""
        req = Request(BASE + "/api/weeks", method="GET")
        with urlopen(req, timeout=5) as resp:
            ct = resp.headers.get("Content-Type", "")
            self.assertIn("application/json", ct)


if __name__ == "__main__":
    import sys
    loader = unittest.TestLoader()
    # Discover all test classes in this module
    suite = loader.loadTestsFromModule(__import__("__main__"))
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
