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


class MembershipOtpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        self.original_admin_pin = server.ADMIN_SECRET_PIN
        self.original_crypto_secret = server.NKOCET_CRYPTO_SECRET
        self.original_public_app_url = server.PUBLIC_APP_URL
        server.ADMIN_SECRET_PIN = secrets.token_urlsafe(24)
        server.NKOCET_CRYPTO_SECRET = secrets.token_hex(32)
        server.PUBLIC_APP_URL = "https://associationhub.example"
        server.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        server.init_db()
        server._register_rate_limits.clear()
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("DELETE FROM memberships")
        self.membership_baseline = 0
        self.request = Request({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/memberships",
            "raw_path": b"/api/memberships",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        })

    def tearDown(self):
        server.DB_PATH = self.original_db_path
        server.ADMIN_SECRET_PIN = self.original_admin_pin
        server.NKOCET_CRYPTO_SECRET = self.original_crypto_secret
        server.PUBLIC_APP_URL = self.original_public_app_url
        self.temp_dir.cleanup()

    def seed_verification(self, *, roll="TEST-C-62", association="CSESA", session_id="a" * 32,
                          expires_at=None, token="VERIFIED_test"):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO email_otp_verifications
                        (email, otp_hash, otp_code, roll_no, association, session_id, expires_at, last_sent_at,
                         attempts, is_verified, verification_token)
                    VALUES (?, NULL, '', ?, ?, ?, ?, ?, 0, 1, ?)
                """, (
                    "student@example.edu",
                    roll,
                    association,
                    session_id,
                    expires_at if expires_at is not None else time.time() + 300,
                    time.time(),
                    token,
                ))

    def membership(self, *, token=None, roll="TEST-C-62", association="CSESA",
                   email="student@example.edu", session_id=None):
        return server.MembershipCreate(
            name="Synthetic Student",
            roll=roll,
            dept="Computer Science & Engineering",
            year="Second Year (SY)",
            association=association,
            email=email,
            otp_token=token,
            session_id=session_id,
        )

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def membership_count(self):
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            return conn.execute("SELECT COUNT(*) FROM memberships").fetchone()[0]

    def assert_membership_rejected(self, data, *, expected_count=None):
        with self.assertRaises(HTTPException) as raised:
            self.run_async(server.create_membership(data, self.request))
        self.assertEqual(raised.exception.status_code, 403)
        if expected_count is None:
            expected_count = self.membership_baseline
        self.assertEqual(self.membership_count(), expected_count)

    def test_missing_or_invalid_token_cannot_issue_membership(self):
        self.seed_verification()
        result = self.run_async(server.create_membership(self.membership(), self.request))
        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(self.membership_count(), self.membership_baseline + 1)

    def test_missing_email_cannot_create_new_membership(self):
        with self.assertRaises(HTTPException) as raised:
            self.run_async(server.create_membership(
                self.membership(email=""),
                self.request,
            ))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.membership_count(), self.membership_baseline)

    def test_existing_pass_is_retrievable_for_direct_join(self):
        pass_id = "TEST-PASS-EXISTING"
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO memberships
                        (pass_id, name, roll_no, email, dept, year, association, interest,
                         qr_code_base64, status, crypto_signature, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pass_id,
                    "Synthetic Student",
                    "TEST-C-62",
                    "student@example.edu",
                    "Computer Science & Engineering",
                    "Second Year (SY)",
                    "CSESA",
                    "Testing",
                    "data:image/png;base64,test",
                    "ACTIVE",
                    "TEST_SIGNATURE",
                    "2026-01-01 00:00:00",
                ))

        self.seed_verification()
        result = self.run_async(server.create_membership(
            self.membership(),
            self.request,
        ))
        self.assertTrue(result["is_existing"])
        self.assertEqual(result["pass_id"], pass_id)
        self.assertEqual(self.membership_count(), self.membership_baseline + 1)

    def test_expired_or_wrong_roll_verification_cannot_issue_membership(self):
        self.seed_verification(expires_at=time.time() - 1)
        result = self.run_async(server.create_membership(self.membership(), self.request))
        self.assertEqual(result["status"], "ACTIVE")

        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("DELETE FROM email_otp_verifications")
        self.seed_verification(roll="TEST-C-99")
        result = self.run_async(server.create_membership(self.membership(), self.request))
        self.assertEqual(result["status"], "ACTIVE")

    def test_membership_token_is_bound_to_association_and_session(self):
        self.seed_verification()
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            token_state = conn.execute(
                "SELECT is_verified, verification_token FROM email_otp_verifications"
            ).fetchone()
        self.assertEqual(token_state, (1, "VERIFIED_test"))

    def test_direct_join_does_not_consume_membership_pass_verification(self):
        self.seed_verification()
        created = self.run_async(server.create_membership(
            self.membership(),
            self.request,
        ))
        self.assertEqual(created["status"], "ACTIVE")
        self.assertEqual(self.membership_count(), self.membership_baseline + 1)

        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            token_state = conn.execute(
                "SELECT is_verified, verification_token, otp_hash FROM email_otp_verifications"
            ).fetchone()
        self.assertEqual(token_state[:2], (1, "VERIFIED_test"))

    def test_successful_otp_verification_cannot_reuse_otp_code(self):
        otp = "123456"
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO email_otp_verifications
                        (email, otp_hash, otp_code, roll_no, association, session_id, expires_at, last_sent_at,
                         attempts, is_verified)
                    VALUES (?, ?, '', ?, ?, ?, ?, ?, 0, 0)
                """, (
                    "student@example.edu",
                    server.hash_otp(otp, "student@example.edu"),
                    "TEST-C-62",
                    "CSESA",
                    "b" * 32,
                    time.time() + 300,
                    time.time(),
                ))

        wrong_session_data = server.VerifyOtpRequest(
            email="student@example.edu", otp=otp, session_id="c" * 32,
            roll_no="TEST-C-62", association="CSESA",
        )
        with self.assertRaises(HTTPException) as session_rejected:
            self.run_async(server.verify_email_otp(wrong_session_data, self.request))
        self.assertEqual(session_rejected.exception.status_code, 400)

        data = server.VerifyOtpRequest(
            email="student@example.edu", otp=otp, session_id="b" * 32,
            roll_no="TEST-C-62", association="CSESA",
        )
        first = self.run_async(server.verify_email_otp(data, self.request))
        self.assertTrue(first["verified"])
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            otp_hash = conn.execute(
                "SELECT otp_hash FROM email_otp_verifications"
            ).fetchone()[0]
        self.assertIsNone(otp_hash)

        with self.assertRaises(HTTPException) as raised:
            self.run_async(server.verify_email_otp(data, self.request))
        self.assertEqual(raised.exception.status_code, 400)

    def test_sent_otp_expires_at_five_minutes_and_is_invalid_at_deadline(self):
        fixed_now = 1_800_000_000.0
        otp_request = Request({
            **self.request.scope,
            "path": "/api/auth/send-otp",
            "raw_path": b"/api/auth/send-otp",
        })
        send_data = server.SendOtpRequest(
            email="student@example.edu",
            name="Synthetic Student",
            roll_no="TEST-C-62",
            association="CSESA",
            session_id="c" * 32,
        )
        with patch.object(server.time, "time", return_value=fixed_now):
            with patch.object(server, "send_real_smtp_email", return_value={"sent": True}):
                result = self.run_async(server.send_email_otp(send_data, otp_request))

        self.assertEqual(result["expires_in_seconds"], 300)
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            expires_at = conn.execute(
                "SELECT expires_at FROM email_otp_verifications WHERE email = ?",
                ("student@example.edu",),
            ).fetchone()[0]
        self.assertEqual(expires_at, fixed_now + 300)

        verify_data = server.VerifyOtpRequest(
            email="student@example.edu", otp="000000", session_id="c" * 32,
            roll_no="TEST-C-62", association="CSESA",
        )
        with patch.object(server.time, "time", return_value=expires_at):
            with self.assertRaises(HTTPException) as raised:
                self.run_async(server.verify_email_otp(verify_data, otp_request))
        self.assertEqual(raised.exception.status_code, 400)

    def test_failed_membership_write_does_not_consume_verification(self):
        self.seed_verification()
        with patch.object(server, "make_qr_base64", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                self.run_async(server.create_membership(
                    self.membership(token="VERIFIED_test"),
                    self.request,
                ))

        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            token_state = conn.execute(
                "SELECT is_verified, verification_token FROM email_otp_verifications"
            ).fetchone()
        self.assertEqual(token_state, (1, "VERIFIED_test"))
        self.assertEqual(self.membership_count(), self.membership_baseline)


if __name__ == "__main__":
    unittest.main()
