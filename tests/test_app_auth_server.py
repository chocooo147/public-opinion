from __future__ import annotations

import hashlib
import importlib.util
import json
import secrets
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "ops/production/app_auth_server.py"
    spec = importlib.util.spec_from_file_location("app_auth_server_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AppAuthServerTests(unittest.TestCase):
    def test_application_login_is_server_authoritative_and_data_free(self):
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="apex-auth-test-") as temp:
            root = Path(temp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<main>protected-dashboard-marker</main>", encoding="utf-8")
            (site / "dashboard.json").write_text('{"protected":true}', encoding="utf-8")
            password = secrets.token_urlsafe(18)
            accounts = root / "accounts.json"
            accounts.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "accounts": [
                            {
                                "username": "acceptance",
                                "role": "admin",
                                "active": True,
                                "protected": True,
                                "password_sha256": hashlib.sha256(password.encode()).hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state = module.AuthState(accounts, site, 600)
            try:
                server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.AppHandler)
            except PermissionError:
                self.skipTest("local socket binding is unavailable in the filesystem sandbox")
            server.auth_state = state
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def request(path: str, payload=None, cookie: str = ""):
                data = json.dumps(payload).encode() if payload is not None else None
                headers = {"Accept": "application/json,text/html"}
                if payload is not None:
                    headers["Content-Type"] = "application/json"
                if cookie:
                    headers["Cookie"] = cookie
                req = urllib.request.Request(base + path, data=data, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=5) as response:
                        return response.status, response.read(), response.headers
                except urllib.error.HTTPError as exc:
                    return exc.code, exc.read(), exc.headers

            try:
                status, body, _ = request("/")
                self.assertEqual(status, 200)
                self.assertIn("APEX 舆情控制台", body.decode())
                self.assertNotIn("protected-dashboard-marker", body.decode())
                self.assertEqual(request("/dashboard.json")[0], 401)
                self.assertEqual(
                    request(
                        "/api/auth/login",
                        {"username": "acceptance", "password": password + "x"},
                    )[0],
                    401,
                )
                status, _, headers = request(
                    "/api/auth/login",
                    {"username": "acceptance", "password": password},
                )
                self.assertEqual(status, 200)
                set_cookie = headers["Set-Cookie"]
                self.assertIn("HttpOnly", set_cookie)
                self.assertIn("Secure", set_cookie)
                self.assertIn("SameSite=Strict", set_cookie)
                cookie = set_cookie.split(";", 1)[0]
                status, body, _ = request("/", cookie=cookie)
                self.assertEqual(status, 200)
                self.assertIn("protected-dashboard-marker", body.decode())
                self.assertEqual(request("/dashboard.json", cookie=cookie)[0], 200)
                self.assertEqual(request("/api/auth/logout", {}, cookie=cookie)[0], 200)
                self.assertEqual(request("/dashboard.json", cookie=cookie)[0], 401)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_new_passwords_use_pbkdf2_and_public_accounts_hide_verifiers(self):
        module = load_module()
        password = secrets.token_urlsafe(18)
        account = {"username": "operator", "role": "manager", "active": True}
        module.AuthState.set_password(account, password)
        self.assertTrue(module.AuthState.verify_password(account, password))
        self.assertFalse(module.AuthState.verify_password(account, password + "x"))
        public = module.AuthState.public_account(account)
        self.assertNotIn("password_digest", public)
        self.assertNotIn("password_salt", public)


if __name__ == "__main__":
    unittest.main()
