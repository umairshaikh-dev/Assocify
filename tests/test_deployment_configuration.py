import asyncio
import os
import secrets
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request

import server


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGIN = "https://affanchoudhari2006-lang.github.io"


async def asgi_request(method, path, headers=()):
    messages = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    raw_path = path.encode("ascii")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": raw_path,
        "query_string": b"",
        "root_path": "",
        "headers": [(name.lower().encode("ascii"), value.encode("latin-1")) for name, value in headers],
        "client": ("127.0.0.1", 32100),
        "server": ("testserver", 443),
    }
    await server.app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), body


class RenderDeploymentConfigurationTests(unittest.TestCase):
    def test_python_runtime_and_uvicorn_dependency_are_available(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 10))
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertRegex(requirements, r"(?m)^uvicorn\s*>=\s*")

    def test_frontend_pages_share_configured_api_client(self):
        html_files = [
            "index.html",
            "aids.html",
            "cep-about us.html",
            "cep-cesa.html",
            "cep-mesa.html",
            "civil.html",
            "entc.html",
            "esa.html",
            "verify.html",
        ]
        for filename in html_files:
            with self.subTest(filename=filename):
                document = (ROOT / filename).read_text(encoding="utf-8")
                config_index = document.find('src="api-config.js"')
                self.assertGreaterEqual(config_index, 0)
                if filename != "verify.html":
                    self.assertLess(config_index, document.find('src="main.js'))

        config = (ROOT / "api-config.js").read_text(encoding="utf-8")
        self.assertIn("ASSOCIATIONHUB_API_BASE_URL", config)
        self.assertIn("window.location.hostname.endsWith('.github.io')", config)
        self.assertIn("Promise.reject(error)", config)
        self.assertNotIn("onrender.com", config)
        main_js = (ROOT / "main.js").read_text(encoding="utf-8")
        self.assertNotIn("fetch(", main_js)
        verify_html = (ROOT / "verify.html").read_text(encoding="utf-8")
        self.assertNotIn("return fetch(url, options)", verify_html)

    def test_cors_preflight_allows_only_the_configured_origin_and_headers(self):
        status, headers, _ = asyncio.run(asgi_request(
            "OPTIONS",
            "/api/student/register/send-otp",
            (
                ("Origin", ALLOWED_ORIGIN),
                ("Access-Control-Request-Method", "POST"),
                ("Access-Control-Request-Headers", "content-type,x-chat-token,x-admin-key"),
            ),
        ))
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"access-control-allow-origin"].decode(), ALLOWED_ORIGIN)
        self.assertNotIn(b"access-control-allow-credentials", headers)
        self.assertIn(b"x-chat-token", headers[b"access-control-allow-headers"].lower())
        self.assertNotIn(b"*", headers[b"access-control-allow-origin"])
        self.assertIn(b"GET", headers[b"access-control-allow-methods"])
        self.assertIn(b"POST", headers[b"access-control-allow-methods"])
        self.assertIn(b"PATCH", headers[b"access-control-allow-methods"])
        self.assertIn(b"DELETE", headers[b"access-control-allow-methods"])
        self.assertNotIn(b"PUT", headers[b"access-control-allow-methods"])

    def test_cors_rejects_unlisted_origins_and_allows_api_health(self):
        status, headers, _ = asyncio.run(asgi_request(
            "OPTIONS",
            "/api/student/register/send-otp",
            (
                ("Origin", "https://example.invalid"),
                ("Access-Control-Request-Method", "POST"),
                ("Access-Control-Request-Headers", "content-type"),
            ),
        ))
        self.assertEqual(status, 400)
        self.assertNotIn(b"access-control-allow-origin", headers)

        status, headers, body = asyncio.run(asgi_request(
            "GET", "/api/health", (("Origin", ALLOWED_ORIGIN),)
        ))
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"access-control-allow-origin"].decode(), ALLOWED_ORIGIN)
        self.assertIn(b'"status":"healthy"', body)

    def test_database_path_is_configurable_and_existing_records_survive_init(self):
        configured_path = os.path.join("custom", "render-data", "hub.db")
        self.assertEqual(
            server.resolve_database_path({"DATABASE_PATH": configured_path}),
            configured_path,
        )
        self.assertTrue(server.resolve_database_path({}).endswith("associationhub.db"))

        original_db_path = server.DB_PATH
        original_crypto_secret = server.NKOCET_CRYPTO_SECRET
        with tempfile.TemporaryDirectory() as temp_dir:
            server.DB_PATH = os.path.join(temp_dir, "nested", "persisted.db")
            server.NKOCET_CRYPTO_SECRET = secrets.token_hex(32)
            try:
                server.init_db()
                with server.get_db() as conn:
                    conn.execute(
                        "UPDATE memberships SET crypto_signature = ? WHERE pass_id = ?",
                        ("existing-signature", "NKOCET-2026-CSESA-7EB769"),
                    )
                    conn.execute(
                        """INSERT INTO registered_students
                        (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
                        ("STUDENT-KEEP", "Existing Student", "existing@college.edu", "KEEP-001",
                         "Computer Science", "password-hash", "password-salt"),
                    )
                    conn.execute(
                        "INSERT INTO events (title, association, date_str, category, description) VALUES (?, ?, ?, ?, ?)",
                        ("Preserved event", "CSESA", "date", "test", "existing data"),
                    )
                    conn.execute(
                        "INSERT INTO gate_checkins (pass_id, student_name, roll_no, association) VALUES (?, ?, ?, ?)",
                        ("NKOCET-2026-CSESA-7EB769", "Test Member", "C-62", "CSESA"),
                    )

                server.init_db()
                with server.get_db() as conn:
                    signature = conn.execute(
                        "SELECT crypto_signature FROM memberships WHERE pass_id = ?",
                        ("NKOCET-2026-CSESA-7EB769",),
                    ).fetchone()[0]
                    event = conn.execute(
                        "SELECT description FROM events WHERE title = ?",
                        ("Preserved event",),
                    ).fetchone()[0]
                    checkins = conn.execute(
                        "SELECT COUNT(*) FROM gate_checkins WHERE student_name = ?",
                        ("Test Member",),
                    ).fetchone()[0]
                    student = conn.execute(
                        "SELECT full_name, roll_no FROM registered_students WHERE student_id = ?",
                        ("STUDENT-KEEP",),
                    ).fetchone()
                self.assertEqual(signature, "existing-signature")
                self.assertEqual(event, "existing data")
                self.assertEqual(checkins, 1)
                self.assertEqual(tuple(student), ("Existing Student", "KEEP-001"))
                self.assertTrue(os.path.isfile(server.DB_PATH))
            finally:
                server.DB_PATH = original_db_path
                server.NKOCET_CRYPTO_SECRET = original_crypto_secret

    def test_smtp_failures_return_generic_error_and_block_registration(self):
        environment = {
            "ADMIN_SECRET_PIN": secrets.token_urlsafe(24),
            "NKOCET_CRYPTO_SECRET": secrets.token_hex(32),
            "SMTP_USER": "sender@college.edu",
            "SMTP_PASSWORD": secrets.token_urlsafe(24),
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(server.smtplib, "SMTP", side_effect=server.smtplib.SMTPAuthenticationError(535, b"internal detail")):
                with self.assertLogs("associationhub.smtp", level="ERROR") as captured:
                    result = server.send_real_smtp_email("student@college.edu", "Student", "123456")
        self.assertFalse(result["sent"])
        self.assertNotIn("internal detail", result["reason"])
        self.assertEqual(result["reason"], "SMTP authentication failed")
        smtp_log = "\n".join(captured.output)
        self.assertIn("SMTPAuthenticationError", smtp_log)
        self.assertIn("535", smtp_log)
        self.assertIn("internal detail", smtp_log)

    def test_smtp_diagnostic_log_redacts_secrets_and_message_content(self):
        environment = {
            "ADMIN_SECRET_PIN": secrets.token_urlsafe(24),
            "NKOCET_CRYPTO_SECRET": secrets.token_hex(32),
            "SMTP_USER": "sender@college.edu",
            "SMTP_PASSWORD": "gmail-app-password-secret",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
        }
        failure = RuntimeError(
            "password=gmail-app-password-secret sender@college.edu otp=123456 recipient student@college.edu"
        )
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(server.smtplib, "SMTP", side_effect=failure):
                with self.assertLogs("associationhub.smtp", level="ERROR") as captured:
                    result = server.send_real_smtp_email(
                        "student@college.edu",
                        "Student",
                        "123456",
                    )

        self.assertFalse(result["sent"])
        smtp_log = "\n".join(captured.output)
        self.assertIn("RuntimeError", smtp_log)
        self.assertNotIn("gmail-app-password-secret", smtp_log)
        self.assertNotIn("sender@college.edu", smtp_log)
        self.assertNotIn("student@college.edu", smtp_log)
        self.assertNotIn("123456", smtp_log)

        original_db_path = server.DB_PATH
        original_crypto_secret = server.NKOCET_CRYPTO_SECRET
        original_admin_pin = server.ADMIN_SECRET_PIN
        with tempfile.TemporaryDirectory() as temp_dir:
            server.DB_PATH = os.path.join(temp_dir, "test.db")
            server.NKOCET_CRYPTO_SECRET = environment["NKOCET_CRYPTO_SECRET"]
            server.ADMIN_SECRET_PIN = environment["ADMIN_SECRET_PIN"]
            server._register_rate_limits.clear()
            server.init_db()
            request = Request({
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/student/register/send-otp",
                "raw_path": b"/api/student/register/send-otp",
                "query_string": b"",
                "headers": [],
                "server": ("testserver", 443),
                "client": ("192.0.2.55", 12345),
            })
            data = server.StudentSendOtpRequest(
                name="Example Student",
                email="new-student@college.edu",
                roll_no="TEST-PHASE3",
                dept="Computer Science",
                password="test-password",
                confirm_password="test-password",
                session_id="d" * 32,
            )
            try:
                with patch.dict(os.environ, environment, clear=True):
                    with patch.object(server, "send_real_smtp_email", return_value={
                        "sent": False,
                        "configured": True,
                        "reason": "SMTP dispatch failed",
                    }):
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(server.student_register_send_otp(data, request))
                self.assertEqual(raised.exception.status_code, 410)
                self.assertEqual(
                    raised.exception.detail,
                    "Student Gmail OTP registration has been removed.",
                )
                with closing(sqlite3.connect(server.DB_PATH)) as conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM registered_students WHERE roll_no = ?",
                            ("TEST-PHASE3",),
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM memberships WHERE roll_no = ?",
                            ("TEST-PHASE3",),
                        ).fetchone()[0],
                        0,
                    )
                    verification = conn.execute(
                        "SELECT otp_code, is_verified FROM email_otp_verifications WHERE email = ?",
                        ("new-student@college.edu",),
                    ).fetchone()
                self.assertIsNone(verification)
            finally:
                server.DB_PATH = original_db_path
                server.NKOCET_CRYPTO_SECRET = original_crypto_secret
                server.ADMIN_SECRET_PIN = original_admin_pin


if __name__ == "__main__":
    unittest.main()
