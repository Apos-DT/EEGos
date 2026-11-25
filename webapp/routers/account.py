"""Browser forms for account setup, sign-in and researcher approval."""

import re
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from .. import accounts
from ..common import templates
from ..config import LOOPBACK_HOSTS

router = APIRouter()


def _local_setup(request):
    return bool(request.client and request.client.host in LOOPBACK_HOSTS and request.url.hostname in LOOPBACK_HOSTS)


def _page(request, mode, *, error="", message="", pending=(), status=200, next_path="/"):
    return templates.TemplateResponse(request=request, name="account.html", context={
        "mode": mode, "error": error, "message": message, "pending": pending, "next_path": next_path,
    }, status_code=status, headers={"Cache-Control": "no-store"})


def _destination(value):
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value and not any(ord(c) < 32 for c in value) else "/"


async def _fields(request):
    origin = f"{request.url.scheme}://{request.url.netloc}"
    if request.headers.get("origin") != origin:
        raise HTTPException(403, "请从当前站点提交表单。")
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413)
    try:
        return {key: values[0] for key, values in parse_qs(body.decode(), max_num_fields=8).items()}
    except ValueError as exc:
        raise HTTPException(400, "表单格式无效。") from exc


@router.get("/login")
async def login_page(request: Request, next: str = "/"):
    return _page(request, "login", next_path=_destination(next))


@router.post("/login")
async def login(request: Request):
    values = await _fields(request)
    identity, password = values.get("identity", "").strip(), values.get("password", "")
    destination = _destination(values.get("next", "/"))
    try:
        if not identity or len(identity) > 254 or not password or len(password) > 128:
            raise ValueError("请填写有效的登录信息。")
        token = await run_in_threadpool(accounts.sign_in, identity, password)
    except (ValueError, PermissionError) as exc:
        return _page(request, "login", error=str(exc), status=401, next_path=destination)
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(accounts.COOKIE, token, max_age=accounts.SESSION_SECONDS,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax")
    return response


@router.get("/register")
async def register_page(request: Request):
    setup = not await run_in_threadpool(accounts.has_admin)
    message = (
        "首个账号将成为管理员，请在运行 EmoStudio 的电脑上使用 127.0.0.1 注册。"
        if setup else "注册后由管理员审核，通过后即可登录。"
    )
    return _page(request, "register", message=message)


@router.post("/register")
async def register(request: Request):
    values = await _fields(request)
    username, email = values.get("username", "").strip(), values.get("email", "").strip()
    password = values.get("password", "")
    try:
        if not re.fullmatch(r"[\w.-]{3,32}", username):
            raise ValueError("用户名须为 3–32 个字符，可使用字母、数字、下划线、点和连字符。")
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("请填写有效的邮箱。")
        if not 10 <= len(password) <= 128 or password != values.get("confirmation"):
            raise ValueError("密码须为 10–128 个字符，两次输入需一致。")
        first = await run_in_threadpool(accounts.register, username, email, password, local_setup=_local_setup(request))
    except (ValueError, PermissionError) as exc:
        return _page(request, "register", error=str(exc), status=400)
    return _page(request, "login", message="管理员账号已创建，可以登录。" if first else "注册成功，管理员审核通过后即可登录。")


@router.post("/logout")
async def logout(request: Request):
    await _fields(request)
    await run_in_threadpool(accounts.sign_out, request.cookies.get(accounts.COOKIE))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(accounts.COOKIE)
    response.delete_cookie("eeg_token")
    return response


def _require_admin(request):
    if not getattr(request.state, "user", None) or request.state.user["role"] != "admin":
        raise HTTPException(403, "请使用管理员账号登录。")


@router.get("/accounts")
async def account_list(request: Request):
    _require_admin(request)
    return _page(request, "accounts", pending=await run_in_threadpool(accounts.pending_accounts))


@router.post("/accounts/{user_id}/approve")
async def approve(request: Request, user_id: int):
    _require_admin(request)
    await _fields(request)
    await run_in_threadpool(accounts.approve, user_id)
    return RedirectResponse("/accounts", status_code=303)
