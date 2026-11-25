"""Local account credentials and revocable SQLite sessions."""

import hashlib
import hmac
import secrets
import sqlite3
from threading import BoundedSemaphore

from .db import transaction

COOKIE = "emostudio_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
_hash_slots = BoundedSemaphore(2)
_dummy_salt = secrets.token_bytes(16)


def _derive(password, salt):
    with _hash_slots:
        return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)


def has_admin():
    with transaction() as conn:
        return conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone() is not None


def register(username, email, password, *, local_setup):
    if not local_setup and not has_admin():
        raise PermissionError("首次注册请在运行 EmoStudio 的电脑上使用本机地址。")
    salt = secrets.token_bytes(16)
    password_hash = f"scrypt${salt.hex()}${_derive(password, salt).hex()}"
    try:
        with transaction(write=True) as conn:
            first = conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone() is None
            if first and not local_setup:
                raise PermissionError("首次注册需要从本机访问。")
            conn.execute(
                "INSERT INTO users(username,email,password_hash,role,status) VALUES (?,?,?,?,?)",
                (username, email, password_hash, "admin" if first else "researcher", "active" if first else "pending"),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("用户名或邮箱已被使用。") from exc
    return first


def sign_in(identity, password):
    with transaction() as conn:
        user = conn.execute(
            "SELECT id, password_hash, status FROM users WHERE username = ? OR email = ?", (identity, identity)
        ).fetchone()
    try:
        scheme, salt, expected = user["password_hash"].split("$") if user else ("", "", "")
        salt, expected = bytes.fromhex(salt), bytes.fromhex(expected)
    except ValueError:
        scheme, salt, expected = "", b"", b""
    supported = scheme == "scrypt" and len(salt) == 16 and len(expected) == 64
    actual = _derive(password, salt if supported else _dummy_salt)
    if not supported or not hmac.compare_digest(actual, expected):
        raise ValueError("用户名、邮箱或密码不正确。")
    if user["status"] != "active":
        raise PermissionError("账号正在等待管理员审核。" if user["status"] == "pending" else "账号已停用。")
    token = secrets.token_urlsafe(32)
    with transaction(write=True) as conn:
        updated = conn.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'active'",
            (user["id"],),
        )
        if not updated.rowcount:
            raise PermissionError("账号当前不可用。")
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= CURRENT_TIMESTAMP")
        conn.execute(
            "INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES (?,?,datetime('now',?))",
            (user["id"], _digest(token), f"+{SESSION_SECONDS} seconds"),
        )
    return token


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session_user(token):
    if not token or len(token) != 43:
        return None
    with transaction() as conn:
        return conn.execute(
            """SELECT u.id, u.username, u.role FROM users u
            JOIN auth_sessions s ON s.user_id = u.id
            WHERE s.token_hash = ? AND s.revoked_at IS NULL
              AND s.expires_at > CURRENT_TIMESTAMP AND u.status = 'active'""",
            (_digest(token),),
        ).fetchone()


def sign_out(token):
    if token:
        with transaction(write=True) as conn:
            conn.execute("UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token_hash = ?", (_digest(token),))


def pending_accounts():
    with transaction() as conn:
        return conn.execute("SELECT id, username, email, created_at FROM users WHERE status = 'pending' ORDER BY id").fetchall()


def approve(user_id):
    with transaction(write=True) as conn:
        conn.execute("UPDATE users SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'", (user_id,))
