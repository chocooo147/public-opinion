#!/usr/bin/env python3
"""Minimal server-side session and static-file boundary for the APEX site.

Credentials stay in a root-managed JSON file outside the public release tree.
The unauthenticated root serves only the application login shell; every report,
dashboard data file, asset, and application document requires a valid HttpOnly
session cookie.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
COOKIE_NAME = "apex_session"
PBKDF2_ITERATIONS = 310_000
MAX_BODY_BYTES = 16_384

LOGIN_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX 舆情控制台 · 登录</title><style>
:root{color-scheme:dark;--accent:#f21f2b;--line:rgba(255,255,255,.13);--muted:#9aa2b4}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 20%,#281014 0,#0c0d11 42%,#07080a 100%);font:14px/1.5 Inter,"PingFang SC",sans-serif;color:#fff}
.card{width:min(430px,calc(100vw - 32px));padding:32px;border:1px solid var(--line);background:rgba(13,14,18,.94);box-shadow:0 28px 90px rgba(0,0,0,.55)}
.brand{display:flex;align-items:center;gap:14px;margin-bottom:28px}.mark{width:42px;height:42px;display:grid;place-items:center;background:var(--accent);clip-path:polygon(50% 0,100% 88%,78% 100%,50% 78%,22% 100%,0 88%)}
h1{margin:0;font-size:22px}.brand p,.note{margin:4px 0 0;color:var(--muted);font-size:11px;letter-spacing:.08em}.field{display:grid;gap:7px;margin:14px 0}.field label{color:#d8dbe2;font-size:12px}.field input{width:100%;height:44px;padding:0 12px;border:1px solid var(--line);background:#08090c;color:#fff;outline:none}.field input:focus{border-color:var(--accent)}
button{width:100%;height:44px;margin-top:12px;border:1px solid #ff626a;background:var(--accent);color:#fff;font-weight:800;cursor:pointer}button:disabled{opacity:.6}.error{min-height:22px;margin:12px 0 0;color:#ff9ca1;font-size:12px}.note{margin-top:18px;line-height:1.7;letter-spacing:0}
</style></head><body><main class="card"><div class="brand"><div class="mark" aria-hidden="true"></div><div><h1>APEX 舆情控制台</h1><p>AUTHORIZED ACCESS ONLY / 授权账号访问</p></div></div>
<form id="login" autocomplete="on"><div class="field"><label for="username">账号</label><input id="username" name="username" autocomplete="username" required autofocus></div><div class="field"><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><button type="submit">登录并进入看板</button><p class="error" id="error" role="alert"></p></form><p class="note">账号由管理员统一配置。凭据仅提交给 APEX 服务端验证，未授权用户无法取得看板数据或报告文件。</p></main>
<script>document.getElementById('login').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button'),error=document.getElementById('error');button.disabled=true;error.textContent='正在验证账号…';try{const response=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({username:form.username.value.trim(),password:form.password.value})});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||'账号或密码错误，或账号已停用。');form.password.value='';location.replace('/');}catch(reason){error.textContent=reason.message;}finally{button.disabled=false;}});</script></body></html>"""


class AuthState:
    def __init__(self, accounts_path: Path, site_root: Path, session_ttl: int) -> None:
        self.accounts_path = accounts_path
        self.site_root = site_root
        self.session_ttl = session_ttl
        self.sessions: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()

    def accounts(self) -> list[dict[str, object]]:
        payload = json.loads(self.accounts_path.read_text(encoding="utf-8"))
        accounts = payload.get("accounts") if isinstance(payload, dict) else payload
        if not isinstance(accounts, list):
            raise ValueError("accounts file must contain an accounts list")
        return [item for item in accounts if isinstance(item, dict)]

    def save_accounts(self, accounts: list[dict[str, object]]) -> None:
        payload = {"schema_version": 2, "accounts": accounts}
        temporary = self.accounts_path.with_suffix(self.accounts_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.accounts_path)

    @staticmethod
    def public_account(account: dict[str, object]) -> dict[str, object]:
        return {
            "username": str(account.get("username") or ""),
            "role": str(account.get("role") or "viewer"),
            "active": bool(account.get("active", True)),
            "protected": bool(account.get("protected", False)),
            "createdAt": str(account.get("created_at") or account.get("createdAt") or ""),
        }

    @staticmethod
    def verify_password(account: dict[str, object], password: str) -> bool:
        if account.get("password_scheme") == "pbkdf2_sha256":
            salt = bytes.fromhex(str(account.get("password_salt") or ""))
            iterations = int(account.get("password_iterations") or PBKDF2_ITERATIONS)
            expected = str(account.get("password_digest") or "")
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()
            return bool(expected) and hmac.compare_digest(actual, expected)
        expected = str(account.get("password_sha256") or account.get("passwordHash") or "")
        actual = hashlib.sha256(password.encode()).hexdigest()
        return bool(expected) and hmac.compare_digest(actual, expected)

    @staticmethod
    def set_password(account: dict[str, object], password: str) -> None:
        salt = secrets.token_bytes(16)
        account.pop("password_sha256", None)
        account.pop("passwordHash", None)
        account["password_scheme"] = "pbkdf2_sha256"
        account["password_salt"] = salt.hex()
        account["password_iterations"] = PBKDF2_ITERATIONS
        account["password_digest"] = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, PBKDF2_ITERATIONS
        ).hex()

    def create_session(self, account: dict[str, object]) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self._purge_sessions()
            self.sessions[token] = {
                "username": str(account["username"]),
                "expires": time.time() + self.session_ttl,
            }
        return token

    def session_account(self, token: str) -> dict[str, object] | None:
        with self.lock:
            self._purge_sessions()
            session = self.sessions.get(token)
        if not session:
            return None
        username = str(session["username"]).lower()
        account = next(
            (a for a in self.accounts() if str(a.get("username") or "").lower() == username),
            None,
        )
        return account if account and bool(account.get("active", True)) else None

    def delete_session(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)

    def _purge_sessions(self) -> None:
        now = time.time()
        expired = [token for token, value in self.sessions.items() if float(value["expires"]) <= now]
        for token in expired:
            self.sessions.pop(token, None)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "APEXAuth/1.0"

    @property
    def state(self) -> AuthState:
        return self.server.auth_state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        super().log_message(format, *args)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "private, no-store")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, object], cookie: str | None = None) -> None:
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
        self.send_response(status)
        self._security_headers()
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _token(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        return cookie.get(COOKIE_NAME).value if cookie.get(COOKIE_NAME) else ""

    def _account(self) -> dict[str, object] | None:
        token = self._token()
        return self.state.session_account(token) if token else None

    def _require_account(self, role: str | None = None) -> dict[str, object] | None:
        account = self._account()
        if not account or (role and account.get("role") != role):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "Authentication required."})
            return None
        return account

    def _cookie(self, token: str, *, delete: bool = False) -> str:
        max_age = 0 if delete else self.state.session_ttl
        value = "" if delete else token
        return f"{COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict"

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/api/auth/session":
            account = self._require_account()
            if account:
                self._json(HTTPStatus.OK, {"account": self.state.public_account(account)})
            return
        if path == "/api/auth/accounts":
            if not self._require_account("admin"):
                return
            accounts = [self.state.public_account(item) for item in self.state.accounts()]
            self._json(HTTPStatus.OK, {"accounts": accounts})
            return
        candidate_request = path == "/review-candidate" or path.startswith(
            "/review-candidate/"
        )
        account = self._account()
        if not account:
            if path in ("/", "/login") or candidate_request:
                destination = "/review-candidate/" if candidate_request else "/"
                login_html = LOGIN_HTML.replace(
                    "location.replace('/');", f"location.replace('{destination}');"
                )
                self._send(HTTPStatus.OK, login_html.encode(), "text/html; charset=utf-8")
            else:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "Authentication required."})
            return
        if candidate_request:
            candidate_root = self.state.site_root.parent / "candidate"
            root = candidate_root.resolve()
            relative_path = path.removeprefix("/review-candidate").lstrip("/")
            relative = relative_path or "index.html"
        else:
            relative = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            root = self.state.site_root.resolve()
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, candidate.read_bytes(), mime)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            payload = self._body()
            if path == "/api/auth/login":
                username = str(payload.get("username") or "").strip().lower()
                password = str(payload.get("password") or "")
                account = next(
                    (
                        item
                        for item in self.state.accounts()
                        if str(item.get("username") or "").lower() == username
                    ),
                    None,
                )
                if not account or not bool(account.get("active", True)) or not self.state.verify_password(account, password):
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "账号或密码错误，或账号已停用。"})
                    return
                token = self.state.create_session(account)
                self._json(
                    HTTPStatus.OK,
                    {"account": self.state.public_account(account)},
                    self._cookie(token),
                )
                return
            if path == "/api/auth/logout":
                token = self._token()
                if token:
                    self.state.delete_session(token)
                self._json(HTTPStatus.OK, {"ok": True}, self._cookie("", delete=True))
                return
            if path == "/api/auth/accounts":
                if not self._require_account("admin"):
                    return
                username = str(payload.get("username") or "").strip().lower()
                password = str(payload.get("password") or "")
                role = str(payload.get("role") or "")
                if not USERNAME_RE.fullmatch(username) or role not in ("manager", "viewer"):
                    raise ValueError("invalid account name or role")
                accounts = self.state.accounts()
                account = next((item for item in accounts if str(item.get("username") or "").lower() == username), None)
                if account and bool(account.get("protected")):
                    raise ValueError("protected accounts cannot be changed")
                if not account:
                    if len(password) < 6:
                        raise ValueError("new account password must contain at least 6 characters")
                    account = {"username": username, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    accounts.append(account)
                elif password and len(password) < 6:
                    raise ValueError("new password must contain at least 6 characters")
                if password:
                    self.state.set_password(account, password)
                account.update({"role": role, "active": True, "protected": False})
                self.state.save_accounts(accounts)
                self._json(HTTPStatus.OK, {"accounts": [self.state.public_account(item) for item in accounts]})
                return
            if path == "/api/auth/accounts/action":
                if not self._require_account("admin"):
                    return
                username = str(payload.get("username") or "").strip().lower()
                action = str(payload.get("action") or "")
                accounts = self.state.accounts()
                account = next((item for item in accounts if str(item.get("username") or "").lower() == username), None)
                if not account or bool(account.get("protected")) or action not in ("toggle", "delete"):
                    raise ValueError("invalid or protected account action")
                if action == "delete":
                    accounts.remove(account)
                else:
                    account["active"] = not bool(account.get("active", True))
                self.state.save_accounts(accounts)
                self._json(HTTPStatus.OK, {"accounts": [self.state.public_account(item) for item in accounts]})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--site-root", type=Path, default=Path("/srv/apex-site/current"))
    parser.add_argument("--accounts", type=Path, default=Path("/var/lib/apex/auth/accounts.json"))
    parser.add_argument("--session-ttl", type=int, default=43_200)
    args = parser.parse_args()
    if not args.accounts.is_file():
        raise FileNotFoundError("private APEX accounts file is missing")
    if args.session_ttl < 300:
        raise ValueError("session TTL must be at least five minutes")
    server = ThreadingHTTPServer((args.bind, args.port), AppHandler)
    server.auth_state = AuthState(args.accounts.resolve(), args.site_root, args.session_ttl)  # type: ignore[attr-defined]
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
