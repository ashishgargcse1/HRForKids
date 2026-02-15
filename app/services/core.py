from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.auth import ROLE_ADMIN, ROLE_CHILD, ROLE_PARENT, hash_password, verify_password
from app.db import now_iso


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def list_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, username, display_name, role, avatar, is_active, must_change_password, created_at FROM users ORDER BY id"
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return row_to_dict(row)


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any]:
    user = get_user_by_username(conn, username)
    if not user or not user["is_active"]:
        raise AppError("Invalid credentials", 401)
    if not verify_password(password, user["password_hash"]):
        raise AppError("Invalid credentials", 401)
    return user


def create_user(
    conn: sqlite3.Connection,
    username: str,
    display_name: str,
    role: str,
    password: str,
    avatar: str,
) -> dict[str, Any]:
    if role not in {ROLE_ADMIN, ROLE_PARENT, ROLE_CHILD}:
        raise AppError("Invalid role")
    if not username or not password or not display_name:
        raise AppError("username, display_name and password are required")

    try:
        cur = conn.execute(
            """
            INSERT INTO users (username, display_name, role, password_hash, avatar, is_active, must_change_password, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, ?)
            """,
            (username.strip(), display_name.strip(), role, hash_password(password), avatar or "🙂", now_iso()),
        )
        conn.commit()
        return get_user(conn, int(cur.lastrowid))  # type: ignore[arg-type]
    except sqlite3.IntegrityError:
        raise AppError("Username already exists", 409)


def patch_user(conn: sqlite3.Connection, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    user = get_user(conn, user_id)
    if not user:
        raise AppError("User not found", 404)

    allowed = {"display_name", "role", "avatar", "is_active", "must_change_password"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if "role" in updates and updates["role"] not in {ROLE_ADMIN, ROLE_PARENT, ROLE_CHILD}:
        raise AppError("Invalid role")

    if not updates:
        return user

    sets = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [user_id]
    conn.execute(f"UPDATE users SET {sets} WHERE id = ?", values)
    conn.commit()
    return get_user(conn, user_id)  # type: ignore[return-value]


def reset_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    user = get_user(conn, user_id)
    if not user:
        raise AppError("User not found", 404)
    if not new_password:
        raise AppError("new_password is required")
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()


def change_password(conn: sqlite3.Connection, user_id: int, old_password: str, new_password: str) -> None:
    user = get_user(conn, user_id)
    if not user:
        raise AppError("User not found", 404)
    if not verify_password(old_password, user["password_hash"]):
        raise AppError("Old password is incorrect", 400)
    if not new_password:
        raise AppError("new_password is required", 400)
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()


def get_points_total(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT COALESCE(SUM(delta), 0) AS total FROM ledger WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["total"]) if row else 0


def add_ledger_entry(
    conn: sqlite3.Connection,
    user_id: int,
    delta: int,
    reason: str,
    ref_type: str,
    ref_id: int | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO ledger (user_id, delta, reason, ref_type, ref_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, delta, reason, ref_type, ref_id, now_iso()),
    )
    return int(cur.lastrowid)


def list_ledger(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, user_id, delta, reason, ref_type, ref_id, created_at FROM ledger WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def create_chore(
    conn: sqlite3.Connection,
    actor: dict[str, Any],
    title: str,
    description: str | None,
    points: int,
    assignee_ids: list[int],
    recurrence: str,
    due_date: str | None,
) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    if not title:
        raise AppError("title is required")
    if points < 0:
        raise AppError("points must be >= 0")
    if recurrence not in {"NONE", "DAILY", "WEEKLY"}:
        raise AppError("invalid recurrence")
    if not assignee_ids:
        raise AppError("At least one assignee is required")

    # Validate assignees are CHILD users.
    q = ",".join(["?"] * len(assignee_ids))
    rows = conn.execute(f"SELECT id, role, is_active FROM users WHERE id IN ({q})", assignee_ids).fetchall()
    if len(rows) != len(set(assignee_ids)):
        raise AppError("Invalid assignee(s)")
    for r in rows:
        if r["role"] != ROLE_CHILD or not r["is_active"]:
            raise AppError("Assignees must be active CHILD users")

    cur = conn.execute(
        """
        INSERT INTO chores (title, description, points, recurrence, due_date, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, 'ASSIGNED', ?, ?)
        """,
        (title.strip(), (description or "").strip(), points, recurrence, due_date, actor["id"], now_iso()),
    )
    chore_id = int(cur.lastrowid)
    for uid in sorted(set(assignee_ids)):
        conn.execute("INSERT INTO chore_assignments (chore_id, user_id) VALUES (?, ?)", (chore_id, uid))
    conn.execute(
        "INSERT INTO chore_events (chore_id, from_status, to_status, actor_user_id, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (chore_id, None, "ASSIGNED", actor["id"], "Chore created", now_iso()),
    )
    conn.commit()
    return get_chore(conn, chore_id)


def _chore_assignee_ids(conn: sqlite3.Connection, chore_id: int) -> list[int]:
    rows = conn.execute("SELECT user_id FROM chore_assignments WHERE chore_id = ?", (chore_id,)).fetchall()
    return [int(r["user_id"]) for r in rows]


def get_chore(conn: sqlite3.Connection, chore_id: int) -> dict[str, Any]:
    chore_row = conn.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
    if not chore_row:
        raise AppError("Chore not found", 404)
    chore = row_to_dict(chore_row)
    assignees = conn.execute(
        """
        SELECT u.id, u.username, u.display_name, u.avatar
        FROM chore_assignments ca
        JOIN users u ON u.id = ca.user_id
        WHERE ca.chore_id = ?
        ORDER BY u.display_name
        """,
        (chore_id,),
    ).fetchall()
    chore["assignees"] = [row_to_dict(r) for r in assignees]
    events = conn.execute(
        """
        SELECT ce.id, ce.from_status, ce.to_status, ce.actor_user_id, u.display_name AS actor_name, ce.note, ce.created_at
        FROM chore_events ce
        JOIN users u ON u.id = ce.actor_user_id
        WHERE ce.chore_id = ?
        ORDER BY ce.id DESC
        """,
        (chore_id,),
    ).fetchall()
    chore["events"] = [row_to_dict(r) for r in events]
    return chore


def list_chores(
    conn: sqlite3.Connection,
    actor: dict[str, Any],
    status: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ["1=1"]
    if status:
        where.append("c.status = ?")
        params.append(status)

    if actor["role"] == ROLE_CHILD:
        where.append("ca.user_id = ?")
        params.append(actor["id"])

    rows = conn.execute(
        f"""
        SELECT DISTINCT c.*
        FROM chores c
        JOIN chore_assignments ca ON ca.chore_id = c.id
        WHERE {' AND '.join(where)}
        ORDER BY c.id DESC
        """,
        params,
    ).fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
        chore = row_to_dict(r)
        chore["assignees"] = _chore_assignee_ids(conn, chore["id"])
        result.append(chore)
    return result


def mark_chore_done(conn: sqlite3.Connection, actor: dict[str, Any], chore_id: int) -> dict[str, Any]:
    if actor["role"] != ROLE_CHILD:
        raise AppError("Only CHILD can mark done", 403)
    chore = get_chore(conn, chore_id)
    assignee_ids = [a["id"] for a in chore["assignees"]]
    if actor["id"] not in assignee_ids:
        raise AppError("Not assigned to this chore", 403)
    if chore["status"] not in {"ASSIGNED", "REJECTED"}:
        raise AppError("Chore cannot be marked done now", 400)

    conn.execute("UPDATE chores SET status = 'DONE_PENDING' WHERE id = ?", (chore_id,))
    conn.execute(
        "INSERT INTO chore_events (chore_id, from_status, to_status, actor_user_id, note, created_at) VALUES (?, ?, 'DONE_PENDING', ?, ?, ?)",
        (chore_id, chore["status"], actor["id"], "Marked done", now_iso()),
    )
    conn.commit()
    return get_chore(conn, chore_id)


def _pending_actor_for_chore(conn: sqlite3.Connection, chore_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT actor_user_id
        FROM chore_events
        WHERE chore_id = ? AND to_status = 'DONE_PENDING'
        ORDER BY id DESC LIMIT 1
        """,
        (chore_id,),
    ).fetchone()
    return int(row["actor_user_id"]) if row else None


def _next_due_date(current: str | None, recurrence: str) -> str | None:
    if not current:
        return None
    d = datetime.strptime(current, "%Y-%m-%d").date()
    if recurrence == "DAILY":
        return (d + timedelta(days=1)).isoformat()
    if recurrence == "WEEKLY":
        return (d + timedelta(weeks=1)).isoformat()
    return current


def _create_next_recurrence(conn: sqlite3.Connection, chore: dict[str, Any]) -> None:
    if chore["recurrence"] not in {"DAILY", "WEEKLY"}:
        return
    assignee_ids = _chore_assignee_ids(conn, chore["id"])
    cur = conn.execute(
        """
        INSERT INTO chores (title, description, points, recurrence, due_date, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, 'ASSIGNED', ?, ?)
        """,
        (
            chore["title"],
            chore["description"],
            chore["points"],
            chore["recurrence"],
            _next_due_date(chore["due_date"], chore["recurrence"]),
            chore["created_by"],
            now_iso(),
        ),
    )
    next_id = int(cur.lastrowid)
    for uid in assignee_ids:
        conn.execute("INSERT INTO chore_assignments (chore_id, user_id) VALUES (?, ?)", (next_id, uid))
    conn.execute(
        "INSERT INTO chore_events (chore_id, from_status, to_status, actor_user_id, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (next_id, None, "ASSIGNED", chore["created_by"], "Auto-created recurrence", now_iso()),
    )


def approve_chore(conn: sqlite3.Connection, actor: dict[str, Any], chore_id: int, note: str | None = None) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    chore = get_chore(conn, chore_id)
    if chore["status"] != "DONE_PENDING":
        raise AppError("Chore is not pending", 400)

    child_id = _pending_actor_for_chore(conn, chore_id)
    if not child_id:
        assignees = _chore_assignee_ids(conn, chore_id)
        child_id = assignees[0] if assignees else None
    if not child_id:
        raise AppError("No assignee found", 400)

    conn.execute("UPDATE chores SET status = 'APPROVED' WHERE id = ?", (chore_id,))
    conn.execute(
        "INSERT INTO chore_events (chore_id, from_status, to_status, actor_user_id, note, created_at) VALUES (?, 'DONE_PENDING', 'APPROVED', ?, ?, ?)",
        (chore_id, actor["id"], note or "Approved", now_iso()),
    )
    add_ledger_entry(conn, child_id, int(chore["points"]), f"Chore approved: {chore['title']}", "CHORE", chore_id)
    _create_next_recurrence(conn, chore)
    conn.commit()
    return get_chore(conn, chore_id)


def reject_chore(conn: sqlite3.Connection, actor: dict[str, Any], chore_id: int, note: str | None = None) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    chore = get_chore(conn, chore_id)
    if chore["status"] != "DONE_PENDING":
        raise AppError("Chore is not pending", 400)

    conn.execute("UPDATE chores SET status = 'REJECTED' WHERE id = ?", (chore_id,))
    conn.execute(
        "INSERT INTO chore_events (chore_id, from_status, to_status, actor_user_id, note, created_at) VALUES (?, 'DONE_PENDING', 'REJECTED', ?, ?, ?)",
        (chore_id, actor["id"], note or "Rejected", now_iso()),
    )
    conn.commit()
    return get_chore(conn, chore_id)


def approvals_queue(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.*
        FROM chores c
        WHERE c.status = 'DONE_PENDING'
        ORDER BY c.id ASC
        """
    ).fetchall()
    out = []
    for r in rows:
        chore = row_to_dict(r)
        chore["assignees"] = _chore_assignee_ids(conn, chore["id"])
        out.append(chore)
    return out


def create_reward(
    conn: sqlite3.Connection,
    actor: dict[str, Any],
    name: str,
    cost: int,
    is_active: bool,
    limit_per_week: int | None,
) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    if not name:
        raise AppError("name is required")
    if cost < 0:
        raise AppError("cost must be >=0")
    cur = conn.execute(
        "INSERT INTO rewards (name, cost, is_active, limit_per_week, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name.strip(), cost, 1 if is_active else 0, limit_per_week, actor["id"], now_iso()),
    )
    conn.commit()
    return get_reward(conn, int(cur.lastrowid))


def get_reward(conn: sqlite3.Connection, reward_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
    if not row:
        raise AppError("Reward not found", 404)
    return row_to_dict(row)


def list_rewards(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM rewards ORDER BY id DESC").fetchall()
    return [row_to_dict(r) for r in rows]


def _start_of_week_utc() -> str:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=now.weekday())).date()
    return datetime.combine(start, datetime.min.time(), timezone.utc).isoformat()


def request_redemption(conn: sqlite3.Connection, actor: dict[str, Any], reward_id: int) -> dict[str, Any]:
    if actor["role"] != ROLE_CHILD:
        raise AppError("Only CHILD can redeem", 403)
    reward = get_reward(conn, reward_id)
    if not reward["is_active"]:
        raise AppError("Reward is inactive", 400)

    total = get_points_total(conn, actor["id"])
    if total < reward["cost"]:
        raise AppError("Not enough points", 400)

    if reward["limit_per_week"] is not None:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM redemptions
            WHERE user_id = ? AND reward_id = ? AND status = 'APPROVED' AND created_at >= ?
            """,
            (actor["id"], reward_id, _start_of_week_utc()),
        ).fetchone()
        if int(row["c"]) >= int(reward["limit_per_week"]):
            raise AppError("Weekly limit reached", 400)

    cur = conn.execute(
        """
        INSERT INTO redemptions (reward_id, user_id, status, note, created_at, updated_at, handled_by)
        VALUES (?, ?, 'REQUESTED', ?, ?, ?, NULL)
        """,
        (reward_id, actor["id"], "Requested by child", now_iso(), now_iso()),
    )
    conn.commit()
    return get_redemption(conn, int(cur.lastrowid))


def get_redemption(conn: sqlite3.Connection, redemption_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT r.*, rw.name AS reward_name, rw.cost AS reward_cost, u.display_name AS user_name
        FROM redemptions r
        JOIN rewards rw ON rw.id = r.reward_id
        JOIN users u ON u.id = r.user_id
        WHERE r.id = ?
        """,
        (redemption_id,),
    ).fetchone()
    if not row:
        raise AppError("Redemption not found", 404)
    return row_to_dict(row)


def list_redemptions(conn: sqlite3.Connection, actor: dict[str, Any]) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if actor["role"] == ROLE_CHILD:
        where = "WHERE r.user_id = ?"
        params.append(actor["id"])

    rows = conn.execute(
        f"""
        SELECT r.*, rw.name AS reward_name, rw.cost AS reward_cost, u.display_name AS user_name
        FROM redemptions r
        JOIN rewards rw ON rw.id = r.reward_id
        JOIN users u ON u.id = r.user_id
        {where}
        ORDER BY r.id DESC
        """,
        params,
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def approve_redemption(conn: sqlite3.Connection, actor: dict[str, Any], redemption_id: int, note: str | None = None) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    redemption = get_redemption(conn, redemption_id)
    if redemption["status"] != "REQUESTED":
        raise AppError("Redemption not pending", 400)

    total = get_points_total(conn, redemption["user_id"])
    if total < redemption["reward_cost"]:
        raise AppError("Child no longer has enough points", 400)

    conn.execute(
        "UPDATE redemptions SET status = 'APPROVED', note = ?, updated_at = ?, handled_by = ? WHERE id = ?",
        (note or "Approved", now_iso(), actor["id"], redemption_id),
    )
    add_ledger_entry(
        conn,
        redemption["user_id"],
        -int(redemption["reward_cost"]),
        f"Reward approved: {redemption['reward_name']}",
        "REWARD",
        redemption_id,
    )
    conn.commit()
    return get_redemption(conn, redemption_id)


def deny_redemption(conn: sqlite3.Connection, actor: dict[str, Any], redemption_id: int, note: str | None = None) -> dict[str, Any]:
    if actor["role"] not in {ROLE_ADMIN, ROLE_PARENT}:
        raise AppError("Not allowed", 403)
    redemption = get_redemption(conn, redemption_id)
    if redemption["status"] != "REQUESTED":
        raise AppError("Redemption not pending", 400)

    conn.execute(
        "UPDATE redemptions SET status = 'DENIED', note = ?, updated_at = ?, handled_by = ? WHERE id = ?",
        (note or "Denied", now_iso(), actor["id"], redemption_id),
    )
    conn.commit()
    return get_redemption(conn, redemption_id)
