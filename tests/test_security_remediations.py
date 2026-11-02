import asyncio
import os
import secrets
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import patch

from fastapi import HTTPException, Request

import server


def make_request(path, *, method="POST", headers=(), query=b""):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query,
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "server": ("testserver", 443),
        "client": ("127.0.0.1", 12345),
    })


class SecurityRemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        self.original_admin_pin = server.ADMIN_SECRET_PIN
        self.original_crypto_secret = server.NKOCET_CRYPTO_SECRET
        self.original_public_app_url = server.PUBLIC_APP_URL
        server.DB_PATH = os.path.join(self.temp_dir.name, "security-test.db")
        server.ADMIN_SECRET_PIN = secrets.token_urlsafe(24)
        server.NKOCET_CRYPTO_SECRET = secrets.token_hex(32)
        server.PUBLIC_APP_URL = "https://associationhub.example"
        server._register_rate_limits.clear()
        server.init_db()

    def tearDown(self):
        server.DB_PATH = self.original_db_path
        server.ADMIN_SECRET_PIN = self.original_admin_pin
        server.NKOCET_CRYPTO_SECRET = self.original_crypto_secret
        server.PUBLIC_APP_URL = self.original_public_app_url
        self.temp_dir.cleanup()

    def seed_registration_verification(self, *, email="student@example.edu", roll="T-101",
                                       session_id="a" * 32, expires_at=None, token="REGISTRATION-token"):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO email_otp_verifications
                        (email, roll_no, association, session_id, expires_at, last_sent_at,
                         attempts, is_verified, verification_token, verified_at)
                    VALUES (?, ?, NULL, ?, ?, 0, 0, 1, ?, CURRENT_TIMESTAMP)
                """, (
                    email, roll, session_id,
                    expires_at if expires_at is not None else time.time() + 300,
                    token,
                ))

    def registration_request(self, *, email="student@example.edu", roll="T-101"):
        return server.StudentCompleteRegistrationRequest(
            name="Synthetic Student",
            email=email,
            roll_no=roll,
            dept="Computer Science",
            password="secure-test-password",
        )

    def test_membership_list_requires_admin_and_token_can_authorize(self):
        with self.assertRaises(HTTPException) as unauthorized:
            asyncio.run(server.list_memberships(make_request("/api/memberships", method="GET")))
        self.assertEqual(unauthorized.exception.status_code, 403)

        token = server.create_admin_session_token()
        result = asyncio.run(server.list_memberships(make_request(
            "/api/memberships", method="GET",
            headers=(("Authorization", f"Bearer {token}"),),
        )))
        self.assertGreaterEqual(result["count"], 0)
        self.assertTrue(all("crypto_signature" not in member for member in result["members"]))

    def test_admin_sessions_are_unique_expire_and_revoke(self):
        first = server.create_admin_session_token()
        second = server.create_admin_session_token()
        self.assertNotEqual(first, second)
        self.assertTrue(server.verify_admin_session_token(first))
        self.assertTrue(server.verify_admin_session_token(second))

        parts = first.split(".")
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute(
                    "UPDATE admin_sessions SET expires_at = ? WHERE session_id = ?;",
                    (time.time() - 1, parts[2]),
                )
        self.assertFalse(server.verify_admin_session_token(first))
        self.assertFalse(server.verify_admin_session_token("SESSION.malformed"))

        revoked = server.create_admin_session_token()
        revoked_id = revoked.split(".")[2]
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute(
                    "UPDATE admin_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE session_id = ?;",
                    (revoked_id,),
                )
        self.assertFalse(server.verify_admin_session_token(revoked))

    def test_admin_logout_revokes_session(self):
        token = server.create_admin_session_token()
        request = make_request(
            "/api/admin/logout", method="POST",
            headers=(("X-Admin-Token", token),),
        )
        result = asyncio.run(server.logout_admin(request))
        self.assertTrue(result["success"])
        self.assertFalse(server.verify_admin_session_token(token))

    def test_admin_pin_login_success_and_invalid_pin(self):
        success = asyncio.run(server.verify_admin_pin(
            server.AdminPinVerify(pin=server.ADMIN_SECRET_PIN),
            make_request("/api/admin/verify-pin"),
        ))
        self.assertTrue(success["valid"])
        self.assertTrue(server.verify_admin_session_token(success["token"]))

        with self.assertRaises(HTTPException) as rejected:
            asyncio.run(server.verify_admin_pin(
                server.AdminPinVerify(pin="incorrect-pin-value"),
                make_request("/api/admin/verify-pin"),
            ))
        self.assertEqual(rejected.exception.status_code, 403)

    def test_brute_force_uses_rolling_fifteen_minute_window(self):
        server._admin_failed_attempts.clear()
        ip = "198.51.100.10"
        for _ in range(5):
            server.record_admin_failed_attempt(ip)
        with self.assertRaises(HTTPException) as locked:
            server.check_admin_brute_force(ip)
        self.assertEqual(locked.exception.status_code, 429)
        self.assertIn("15 minutes", locked.exception.detail)

    def test_failed_attempts_persist_in_sqlite_after_memory_clear(self):
        server._admin_failed_attempts.clear()
        ip = "198.51.100.11"
        for _ in range(5):
            server.record_admin_failed_attempt(ip)

        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            persisted_count = conn.execute(
                "SELECT COUNT(*) FROM admin_failed_attempts WHERE ip_address = ?;",
                (ip,),
            ).fetchone()[0]
        self.assertEqual(persisted_count, 5)

        server._admin_failed_attempts.clear()
        with self.assertRaises(HTTPException) as locked:
            server.check_admin_brute_force(ip)
        self.assertEqual(locked.exception.status_code, 429)

    def test_attempts_older_than_rolling_window_do_not_count(self):
        ip = "198.51.100.12"
        now = time.time()
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("DELETE FROM admin_failed_attempts WHERE ip_address = ?;", (ip,))
                conn.executemany(
                    "INSERT INTO admin_failed_attempts (ip_address, attempted_at) VALUES (?, ?);",
                    [(ip, now - 16 * 60)] * 5,
                )

        server.check_admin_brute_force(ip)
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.executemany(
                    "INSERT INTO admin_failed_attempts (ip_address, attempted_at) VALUES (?, ?);",
                    [(ip, now)] * 5,
                )
        with self.assertRaises(HTTPException):
            server.check_admin_brute_force(ip)

    def test_client_ip_trusts_only_configured_forwarding(self):
        direct_request = make_request(
            "/api/admin/verify-pin", method="POST",
            headers=(("X-Forwarded-For", "203.0.113.20"),),
        )
        direct_request.scope["client"] = ("198.51.100.10", 12345)
        self.assertEqual(server.get_client_ip(direct_request), "198.51.100.10")

        with patch.dict(os.environ, {"TRUSTED_PROXY_IPS": "198.51.100.10"}):
            trusted_request = make_request(
                "/api/admin/verify-pin", method="POST",
                headers=(("X-Forwarded-For", "203.0.113.20, 198.51.100.10"),),
            )
            trusted_request.scope["client"] = ("198.51.100.10", 12345)
            self.assertEqual(server.get_client_ip(trusted_request), "203.0.113.20")

    def test_direct_registration_accepts_valid_student_details(self):
        request = make_request("/api/student/register/complete")
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example"}):
            result = asyncio.run(server.student_register_complete(self.registration_request(), request))
        self.assertTrue(result["success"])
        self.assertFalse(result["is_email_verified"])
        self.assertEqual(result["email_verified_at"], "")

    def test_direct_registration_rejects_duplicate_email_or_roll(self):
        request = make_request("/api/student/register/complete")
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example"}):
            result = asyncio.run(server.student_register_complete(self.registration_request(), request))
            self.assertTrue(result["success"])
            with self.assertRaises(HTTPException) as reused:
                asyncio.run(server.student_register_complete(self.registration_request(), request))
        self.assertEqual(reused.exception.status_code, 400)

    def test_chat_registration_works_without_otp(self):
        data = server.ChatRegisterRequest(
            name="Direct Chat Student",
            roll_no="CHAT-DIRECT-1",
            dept="Computer Science & Engineering",
            email="direct-chat@example.edu",
        )
        request = make_request("/api/chat/auth/verify-and-enter")

        result = asyncio.run(server.verify_and_enter_chat(data, request))

        self.assertTrue(result["success"])
        self.assertTrue(result["token"])
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            otp_rows = conn.execute(
                "SELECT COUNT(*) FROM email_otp_verifications WHERE email = ? AND roll_no = ?",
                (data.email, data.roll_no),
            ).fetchone()[0]
            user = conn.execute(
                "SELECT name, email FROM community_users WHERE roll_no = ?",
                (data.roll_no,),
            ).fetchone()
        self.assertEqual(otp_rows, 0)
        self.assertEqual(user, ("Direct Chat Student", data.email))

    def test_chat_sessions_expire_and_revoked_sessions_do_not_authenticate(self):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO community_users
                        (user_id, name, roll_no, email, dept, status, session_token,
                         session_expires_at, session_revoked_at)
                    VALUES ('U1', 'Student', 'T-1', 'student@example.edu', 'CSE',
                            'ACTIVE', 'expired-token', datetime('now', '-1 hour'), NULL)
                """)
                conn.execute("""
                    INSERT INTO community_users
                        (user_id, name, roll_no, email, dept, status, session_token,
                         session_expires_at, session_revoked_at)
                    VALUES ('U2', 'Student', 'T-2', 'other@example.edu', 'CSE',
                            'ACTIVE', 'revoked-token', datetime('now', '+1 hour'), CURRENT_TIMESTAMP)
                """)
                conn.execute("""
                    INSERT INTO community_users
                        (user_id, name, roll_no, email, dept, status, session_token,
                         session_expires_at, session_revoked_at)
                    VALUES ('U3', 'Student', 'T-3', 'active@example.edu', 'CSE',
                            'ACTIVE', 'active-token', datetime('now', '+1 hour'), NULL)
                """)

        for token in ("expired-token", "revoked-token"):
            with self.subTest(token_state=token):
                with self.assertRaises(HTTPException) as rejected:
                    asyncio.run(server.get_chat_current_user(make_request(
                        "/api/chat/auth/me", method="GET", headers=(("X-Chat-Token", token),)
                    )))
                self.assertEqual(rejected.exception.status_code, 401)

        result = asyncio.run(server.get_chat_current_user(make_request(
            "/api/chat/auth/me", method="GET", headers=(("X-Chat-Token", "active-token"),)
        )))
        self.assertTrue(result["authenticated"])
        with self.assertRaises(HTTPException) as query_auth:
            asyncio.run(server.get_chat_current_user(make_request(
                "/api/chat/auth/me", method="GET", query=b"token=active-token"
            )))
        self.assertEqual(query_auth.exception.status_code, 401)

    def test_chat_ban_revokes_the_persisted_session(self):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO community_users
                        (user_id, name, roll_no, email, dept, status, session_token,
                         session_expires_at, session_revoked_at)
                    VALUES ('BAN-ME', 'Student', 'T-4', 'ban@example.edu', 'CSE',
                            'ACTIVE', 'ban-token', datetime('now', '+1 hour'), NULL)
                """)
        status_data = server.ChatUserStatusUpdate(status="BANNED")
        request = make_request(
            "/api/admin/chat/users/BAN-ME/status",
            method="PATCH",
            headers=(("X-Admin-Key", server.ADMIN_SECRET_PIN),),
        )
        result = asyncio.run(server.update_chat_user_status("BAN-ME", status_data, request))
        self.assertTrue(result["success"])
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            revoked = conn.execute(
                "SELECT session_token, session_revoked_at FROM community_users WHERE user_id = 'BAN-ME'"
            ).fetchone()
        self.assertIsNone(revoked[0])
        self.assertIsNotNone(revoked[1])

    def test_legacy_chat_sessions_migrate_to_finite_expiry_and_revoke_banned(self):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("DROP TABLE community_users")
                conn.execute("""
                    CREATE TABLE community_users (
                        user_id TEXT PRIMARY KEY, name TEXT NOT NULL, roll_no TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL, dept TEXT NOT NULL, status TEXT DEFAULT 'ACTIVE',
                        session_token TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_active TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    INSERT INTO community_users
                    (user_id, name, roll_no, email, dept, status, session_token, created_at)
                    VALUES ('OLD-ACTIVE', 'Student', 'T-5', 'old-active@example.edu',
                            'CSE', 'ACTIVE', 'legacy-active', datetime('now', '-2 days'))
                """)
                conn.execute("""
                    INSERT INTO community_users
                    (user_id, name, roll_no, email, dept, status, session_token, created_at)
                    VALUES ('OLD-BANNED', 'Student', 'T-6', 'old-banned@example.edu',
                            'CSE', 'BANNED', 'legacy-banned', CURRENT_TIMESTAMP)
                """)

        server.init_db()
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            active = conn.execute("""
                SELECT session_expires_at, session_revoked_at
                FROM community_users WHERE user_id = 'OLD-ACTIVE'
            """).fetchone()
            banned = conn.execute("""
                SELECT session_token, session_revoked_at
                FROM community_users WHERE user_id = 'OLD-BANNED'
            """).fetchone()
        self.assertIsNotNone(active[0])
        self.assertIsNone(active[1])
        self.assertIsNone(banned[0])
        self.assertIsNotNone(banned[1])

    def test_membership_lookup_requires_and_consumes_verified_otp(self):
        pass_id = "PASS-LOOKUP-1"
        signature = server.compute_hmac_signature(pass_id, "T-101", "CSESA")
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO memberships
                        (pass_id, name, roll_no, email, dept, year, association, interest,
                         qr_code_base64, status, crypto_signature)
                    VALUES (?, 'Synthetic Student', 'T-101', 'student@example.edu',
                            'Computer Science', 'Second Year (SY)', 'CSESA', 'Testing',
                            'data:image/png;base64,stale-local-qr', 'ACTIVE', ?)
                """, (pass_id, signature))

        otp_capture = []
        request = make_request("/api/memberships/lookup/send-otp")
        lookup_request = server.MembershipLookupOtpRequest(
            query=pass_id,
            email="student@example.edu",
            session_id="e" * 32,
        )
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example"}):
            with patch.object(server, "send_real_smtp_email", side_effect=lambda email, name, otp: (
                otp_capture.append(otp) or {"sent": True}
            )):
                sent = asyncio.run(server.send_membership_lookup_otp(lookup_request, request))
        self.assertEqual(sent["roll_no"], "T-101")

        verified = asyncio.run(server.verify_email_otp(
            server.VerifyOtpRequest(
                email="student@example.edu",
                otp=otp_capture[0],
                roll_no="T-101",
                association="CSESA",
                session_id="e" * 32,
            ),
            make_request("/api/auth/verify-otp"),
        ))
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example"}):
            result = asyncio.run(server.lookup_membership(
                server.MembershipLookupRequest(
                    query=pass_id,
                    email="student@example.edu",
                    roll_no="T-101",
                    association="CSESA",
                    otp_token=verified["verification_token"],
                    session_id="e" * 32,
                ),
                make_request("/api/memberships/lookup"),
            ))
        self.assertEqual(result["pass_id"], pass_id)
        self.assertIn("https://associationhub.example/verify.html", result["verify_url"])
        self.assertNotEqual(result["qr_code_base64"], "data:image/png;base64,stale-local-qr")
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example"}):
            unsigned = asyncio.run(server.verify_membership(
                pass_id,
                make_request("/api/memberships/verify/" + pass_id, method="GET"),
            ))
            tampered = asyncio.run(server.verify_membership(
                pass_id,
                make_request("/api/memberships/verify/" + pass_id, method="GET"),
                sig="BAD-SIGNATURE",
            ))
            verified_pass = asyncio.run(server.verify_membership(
                pass_id,
                make_request("/api/memberships/verify/" + pass_id, method="GET"),
                sig=signature,
            ))
        self.assertFalse(unsigned["valid"])
        self.assertFalse(tampered["valid"])
        self.assertNotEqual(
            verified_pass["member"]["qr_code_base64"],
            "data:image/png;base64,stale-local-qr",
        )

        with self.assertRaises(HTTPException) as replay:
            asyncio.run(server.lookup_membership(
                server.MembershipLookupRequest(
                    query=pass_id,
                    email="student@example.edu",
                    roll_no="T-101",
                    association="CSESA",
                    otp_token=verified["verification_token"],
                    session_id="e" * 32,
                ),
                make_request("/api/memberships/lookup"),
            ))
        self.assertEqual(replay.exception.status_code, 403)

    def test_qr_urls_use_configured_public_https_frontend_only(self):
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://associationhub.example/app"}):
            self.assertEqual(
                server.build_verification_url("PASS-1", "SIGNATURE"),
                "https://associationhub.example/app/verify.html?pass_id=PASS-1&sig=SIGNATURE",
            )

        for value in ("", "http://localhost:8080", "https://127.0.0.1", "https://[invalid"):
            with self.subTest(public_app_url=value):
                with patch.dict(os.environ, {"PUBLIC_APP_URL": value}):
                    with self.assertRaises(HTTPException) as rejected:
                        server.build_verification_url("PASS-1", "SIGNATURE")
                self.assertEqual(rejected.exception.status_code, 503)

    def test_admin_query_parameter_cannot_authenticate(self):
        with self.assertRaises(HTTPException) as rejected:
            server.verify_admin_access(make_request(
                "/api/admin/events", query=b"pin=" + server.ADMIN_SECRET_PIN.encode()
            ))
        self.assertEqual(rejected.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
