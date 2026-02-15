from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import ROLE_ADMIN, ROLE_CHILD, ROLE_PARENT
from app.db import connect, init_db
from app.services.core import (
    AppError,
    approvals_queue,
    approve_chore,
    approve_redemption,
    authenticate,
    change_password,
    create_chore,
    create_reward,
    create_user,
    deny_redemption,
    get_chore,
    get_points_total,
    get_user,
    list_chores,
    list_ledger,
    list_redemptions,
    list_rewards,
    list_users,
    mark_chore_done,
    patch_user,
    reject_chore,
    request_redemption,
    reset_password,
)

APP_PORT = int(os.getenv("APP_PORT", "8080"))
APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-me")

app = FastAPI(title="Healthy Routine for Kids")
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    init_db()
    if APP_SECRET == "dev-secret-change-me":
        print("WARNING: APP_SECRET is default. Set APP_SECRET in production.")


@app.middleware("http")
async def attach_user(request: Request, call_next):
    conn = connect()
    request.state.conn = conn
    request.state.user = None
    try:
        response = await call_next(request)
    finally:
        conn.close()
    return response


def _current_user(request: Request):
    if getattr(request.state, "user", None):
        return request.state.user
    if "session" not in request.scope:
        return None
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = get_user(request.state.conn, int(user_id))
    if not user or not user["is_active"]:
        request.session.clear()
        return None
    request.state.user = user
    return user


def _require_login(request: Request):
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _ctx(request: Request, **kwargs: Any) -> dict[str, Any]:
    user = _current_user(request)
    return {
        "request": request,
        "user": user,
        "is_admin": bool(user and user["role"] == ROLE_ADMIN),
        "is_parent": bool(user and user["role"] == ROLE_PARENT),
        "is_child": bool(user and user["role"] == ROLE_CHILD),
        **kwargs,
    }


async def _body(request: Request) -> dict[str, Any]:
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        return await request.json()
    form = await request.form()
    return dict(form)


def _error_response(request: Request, e: AppError):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=e.status_code, content={"error": e.message})
    raise HTTPException(status_code=e.status_code, detail=e.message)


def _require_roles(request: Request, roles: set[str]):
    user = _require_login(request)
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root(request: Request):
    if _current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login")
def login_page(request: Request, error: str | None = None):
    if _current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", _ctx(request, error=error))


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = request.state.conn
    try:
        user = authenticate(conn, username, password)
    except AppError:
        return RedirectResponse("/login?error=Invalid+credentials", status_code=302)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout_submit(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dashboard")
def dashboard(request: Request):
    user = _require_login(request)
    conn = request.state.conn

    if user["role"] == ROLE_CHILD:
        chores = list_chores(conn, user)
        points = get_points_total(conn, user["id"])
        rewards = [r for r in list_rewards(conn) if r["is_active"]]
        pending = [c for c in chores if c["status"] == "DONE_PENDING"]
        return templates.TemplateResponse(
            "dashboard_child.html",
            _ctx(request, chores=chores[:8], pending_count=len(pending), points=points, rewards=rewards[:6]),
        )

    if user["role"] in {ROLE_PARENT, ROLE_ADMIN}:
        children = [u for u in list_users(conn) if u["role"] == ROLE_CHILD and u["is_active"]]
        child_points = [{"user": c, "points": get_points_total(conn, c["id"])} for c in children]
        pending = approvals_queue(conn)
        template = "dashboard_parent.html" if user["role"] == ROLE_PARENT else "dashboard_admin.html"
        return templates.TemplateResponse(
            template,
            _ctx(request, child_points=child_points, pending=pending),
        )

    raise HTTPException(status_code=403, detail="Unknown role")


@app.post("/me/change-password")
async def web_change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
):
    user = require_login(request)
    conn = request.state.conn
    try:
        change_password(conn, user["id"], old_password, new_password)
    except AppError as e:
        return RedirectResponse(f"/dashboard?error={e.message}", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/users")
def users_page(request: Request):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    return templates.TemplateResponse("users.html", _ctx(request, users=list_users(conn)))


@app.post("/users/create")
async def users_create(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    avatar: str = Form("🙂"),
):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    try:
        create_user(conn, username, display_name, role, password, avatar)
    except AppError as e:
        return RedirectResponse(f"/users?error={e.message}", status_code=302)
    return RedirectResponse("/users", status_code=302)


@app.post("/users/{user_id}/toggle")
async def users_toggle(request: Request, user_id: int):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    user = get_user(conn, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    patch_user(conn, user_id, {"is_active": 0 if user["is_active"] else 1})
    return RedirectResponse("/users", status_code=302)


@app.post("/users/{user_id}/role")
async def users_role(request: Request, user_id: int, role: str = Form(...)):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    try:
        patch_user(conn, user_id, {"role": role})
    except AppError as e:
        return RedirectResponse(f"/users?error={e.message}", status_code=302)
    return RedirectResponse("/users", status_code=302)


@app.post("/users/{user_id}/reset-password")
async def users_reset_password(request: Request, user_id: int, new_password: str = Form(...)):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    try:
        reset_password(conn, user_id, new_password)
    except AppError as e:
        return RedirectResponse(f"/users?error={e.message}", status_code=302)
    return RedirectResponse("/users", status_code=302)


@app.get("/chores")
def chores_page(request: Request, status: str | None = None):
    user = _require_login(request)
    conn = request.state.conn
    chores = list_chores(conn, user, status=status)
    children = [u for u in list_users(conn) if u["role"] == ROLE_CHILD and u["is_active"]]
    return templates.TemplateResponse("chores.html", _ctx(request, chores=chores, children=children, status_filter=status))


@app.post("/chores/create")
async def chores_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    points: int = Form(...),
    assignee_ids: list[int] = Form(...),
    recurrence: str = Form("NONE"),
    due_date: str = Form(""),
):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        create_chore(
            conn,
            user,
            title,
            description,
            points,
            assignee_ids,
            recurrence,
            due_date or None,
        )
    except AppError as e:
        return RedirectResponse(f"/chores?error={e.message}", status_code=302)
    return RedirectResponse("/chores", status_code=302)


@app.get("/chores/{chore_id}")
def chore_detail_page(request: Request, chore_id: int):
    user = _require_login(request)
    conn = request.state.conn
    chore = get_chore(conn, chore_id)
    if user["role"] == ROLE_CHILD and user["id"] not in [a["id"] for a in chore["assignees"]]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return templates.TemplateResponse("chore_detail.html", _ctx(request, chore=chore))


@app.post("/chores/{chore_id}/done")
def chores_done_web(request: Request, chore_id: int):
    user = _require_roles(request, {ROLE_CHILD})
    conn = request.state.conn
    try:
        mark_chore_done(conn, user, chore_id)
    except AppError as e:
        return RedirectResponse(f"/chores?error={e.message}", status_code=302)
    return RedirectResponse("/chores", status_code=302)


@app.get("/approvals")
def approvals_page(request: Request):
    _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    return templates.TemplateResponse("approvals.html", _ctx(request, queue=approvals_queue(conn)))


@app.post("/chores/{chore_id}/approve")
async def chores_approve_web(request: Request, chore_id: int, note: str = Form("")):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        approve_chore(conn, user, chore_id, note)
    except AppError as e:
        return RedirectResponse(f"/approvals?error={e.message}", status_code=302)
    return RedirectResponse("/approvals?confetti=1", status_code=302)


@app.post("/chores/{chore_id}/reject")
async def chores_reject_web(request: Request, chore_id: int, note: str = Form("")):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        reject_chore(conn, user, chore_id, note)
    except AppError as e:
        return RedirectResponse(f"/approvals?error={e.message}", status_code=302)
    return RedirectResponse("/approvals", status_code=302)


@app.get("/rewards")
def rewards_page(request: Request):
    user = _require_login(request)
    conn = request.state.conn
    return templates.TemplateResponse(
        "rewards.html",
        _ctx(request, rewards=list_rewards(conn), redemptions=list_redemptions(conn, user), points=get_points_total(conn, user["id"])),
    )


@app.post("/rewards/create")
async def rewards_create_web(
    request: Request,
    name: str = Form(...),
    cost: int = Form(...),
    is_active: str = Form("1"),
    limit_per_week: str = Form(""),
):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        create_reward(conn, user, name, cost, is_active == "1", int(limit_per_week) if limit_per_week else None)
    except AppError as e:
        return RedirectResponse(f"/rewards?error={e.message}", status_code=302)
    return RedirectResponse("/rewards", status_code=302)


@app.post("/rewards/{reward_id}/redeem")
def rewards_redeem_web(request: Request, reward_id: int):
    user = _require_roles(request, {ROLE_CHILD})
    conn = request.state.conn
    try:
        request_redemption(conn, user, reward_id)
    except AppError as e:
        return RedirectResponse(f"/rewards?error={e.message}", status_code=302)
    return RedirectResponse("/rewards", status_code=302)


@app.post("/redemptions/{redemption_id}/approve")
async def redemptions_approve_web(request: Request, redemption_id: int, note: str = Form("")):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        approve_redemption(conn, user, redemption_id, note)
    except AppError as e:
        return RedirectResponse(f"/rewards?error={e.message}", status_code=302)
    return RedirectResponse("/rewards?confetti=1", status_code=302)


@app.post("/redemptions/{redemption_id}/deny")
async def redemptions_deny_web(request: Request, redemption_id: int, note: str = Form("")):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    try:
        deny_redemption(conn, user, redemption_id, note)
    except AppError as e:
        return RedirectResponse(f"/rewards?error={e.message}", status_code=302)
    return RedirectResponse("/rewards", status_code=302)


@app.get("/ledger")
def ledger_page(request: Request, user_id: int | None = None):
    actor = _require_login(request)
    conn = request.state.conn

    if actor["role"] == ROLE_CHILD:
        target_user_id = actor["id"]
    else:
        target_user_id = user_id or actor["id"]

    if actor["role"] == ROLE_CHILD and target_user_id != actor["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    child_users = [u for u in list_users(conn) if u["role"] == ROLE_CHILD and u["is_active"]]
    entries = list_ledger(conn, target_user_id)
    total = get_points_total(conn, target_user_id)
    return templates.TemplateResponse(
        "ledger.html",
        _ctx(request, entries=entries, total=total, child_users=child_users, target_user_id=target_user_id),
    )


# -------------------- API --------------------


@app.post("/api/login")
async def api_login(request: Request):
    conn = request.state.conn
    data = await _body(request)
    try:
        user = authenticate(conn, data.get("username", ""), data.get("password", ""))
    except AppError as e:
        return _error_response(request, e)
    request.session["user_id"] = user["id"]
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "must_change_password": user["must_change_password"],
    }


@app.post("/api/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def api_me(request: Request):
    user = _require_login(request)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "avatar": user["avatar"],
        "must_change_password": user["must_change_password"],
    }


@app.get("/api/users")
def api_users_list(request: Request):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    return list_users(conn)


@app.post("/api/users", status_code=201)
async def api_users_create(request: Request):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        user = create_user(
            conn,
            data.get("username", ""),
            data.get("display_name", ""),
            data.get("role", ""),
            data.get("password", ""),
            data.get("avatar", "🙂"),
        )
    except AppError as e:
        return _error_response(request, e)
    return user


@app.patch("/api/users/{user_id}")
async def api_users_patch(request: Request, user_id: int):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        user = patch_user(conn, user_id, data)
    except AppError as e:
        return _error_response(request, e)
    return user


@app.post("/api/users/{user_id}/reset-password")
async def api_users_reset_password(request: Request, user_id: int):
    _require_roles(request, {ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        reset_password(conn, user_id, data.get("new_password", ""))
    except AppError as e:
        return _error_response(request, e)
    return {"ok": True}


@app.get("/api/chores")
def api_chores_list(request: Request, status: str | None = None):
    user = _require_login(request)
    conn = request.state.conn
    return list_chores(conn, user, status=status)


@app.post("/api/chores", status_code=201)
async def api_chores_create(request: Request):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    assignee_ids = data.get("assignee_ids", [])
    if isinstance(assignee_ids, str):
        assignee_ids = [int(x) for x in assignee_ids.split(",") if x]
    try:
        chore = create_chore(
            conn,
            user,
            data.get("title", ""),
            data.get("description", ""),
            int(data.get("points", 0)),
            [int(x) for x in assignee_ids],
            data.get("recurrence", "NONE"),
            data.get("due_date") or None,
        )
    except AppError as e:
        return _error_response(request, e)
    return chore


@app.get("/api/chores/{chore_id}")
def api_chores_get(request: Request, chore_id: int):
    user = _require_login(request)
    conn = request.state.conn
    try:
        chore = get_chore(conn, chore_id)
    except AppError as e:
        return _error_response(request, e)
    if user["role"] == ROLE_CHILD and user["id"] not in [a["id"] for a in chore["assignees"]]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return chore


@app.post("/api/chores/{chore_id}/done")
def api_chores_done(request: Request, chore_id: int):
    user = _require_roles(request, {ROLE_CHILD})
    conn = request.state.conn
    try:
        chore = mark_chore_done(conn, user, chore_id)
    except AppError as e:
        return _error_response(request, e)
    return chore


@app.post("/api/chores/{chore_id}/approve")
async def api_chores_approve(request: Request, chore_id: int):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        chore = approve_chore(conn, user, chore_id, data.get("note"))
    except AppError as e:
        return _error_response(request, e)
    return chore


@app.post("/api/chores/{chore_id}/reject")
async def api_chores_reject(request: Request, chore_id: int):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        chore = reject_chore(conn, user, chore_id, data.get("note"))
    except AppError as e:
        return _error_response(request, e)
    return chore


@app.get("/api/rewards")
def api_rewards_list(request: Request):
    _require_login(request)
    conn = request.state.conn
    return list_rewards(conn)


@app.post("/api/rewards", status_code=201)
async def api_rewards_create(request: Request):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        raw_active = data.get("is_active", True)
        is_active = raw_active if isinstance(raw_active, bool) else str(raw_active).lower() in {"1", "true", "yes", "on"}
        reward = create_reward(
            conn,
            user,
            data.get("name", ""),
            int(data.get("cost", 0)),
            is_active,
            int(data["limit_per_week"]) if data.get("limit_per_week") not in (None, "") else None,
        )
    except AppError as e:
        return _error_response(request, e)
    return reward


@app.post("/api/rewards/{reward_id}/redeem")
def api_rewards_redeem(request: Request, reward_id: int):
    user = _require_roles(request, {ROLE_CHILD})
    conn = request.state.conn
    try:
        redemption = request_redemption(conn, user, reward_id)
    except AppError as e:
        return _error_response(request, e)
    return redemption


@app.get("/api/redemptions")
def api_redemptions_list(request: Request):
    user = _require_login(request)
    conn = request.state.conn
    return list_redemptions(conn, user)


@app.post("/api/redemptions/{redemption_id}/approve")
async def api_redemptions_approve(request: Request, redemption_id: int):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        redemption = approve_redemption(conn, user, redemption_id, data.get("note"))
    except AppError as e:
        return _error_response(request, e)
    return redemption


@app.post("/api/redemptions/{redemption_id}/deny")
async def api_redemptions_deny(request: Request, redemption_id: int):
    user = _require_roles(request, {ROLE_PARENT, ROLE_ADMIN})
    conn = request.state.conn
    data = await _body(request)
    try:
        redemption = deny_redemption(conn, user, redemption_id, data.get("note"))
    except AppError as e:
        return _error_response(request, e)
    return redemption


@app.get("/api/ledger")
def api_ledger(request: Request, user_id: int | None = None):
    actor = _require_login(request)
    conn = request.state.conn
    target_user_id = user_id or actor["id"]

    if actor["role"] == ROLE_CHILD and target_user_id != actor["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    if actor["role"] in {ROLE_PARENT, ROLE_ADMIN}:
        target = get_user(conn, target_user_id)
        if not target or target["role"] != ROLE_CHILD:
            raise HTTPException(status_code=400, detail="user_id must be a CHILD")

    return {
        "user_id": target_user_id,
        "total": get_points_total(conn, target_user_id),
        "entries": list_ledger(conn, target_user_id),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=APP_PORT, reload=False)
