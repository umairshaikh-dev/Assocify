import asyncio
import os
import secrets
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from fastapi import HTTPException, Request

import server


class ServerConfigurationTests(unittest.TestCase):
    def valid_environment(self):
        return {
            "ADMIN_SECRET_PIN": secrets.token_urlsafe(24),
            "NKOCET_CRYPTO_SECRET": secrets.token_hex(32),
        }

    def test_required_secrets_must_be_present(self):
        for missing in ("ADMIN_SECRET_PIN", "NKOCET_CRYPTO_SECRET"):
            with self.subTest(missing=missing):
                environment = self.valid_environment()
                environment.pop(missing)
                with self.assertRaisesRegex(ValueError, missing):
                    server.load_server_configuration(environment)

    def test_application_startup_fails_closed_when_required_secrets_are_missing(self):
        async def start_application():
            async with server.lifespan(server.app):
                self.fail("Application startup unexpectedly accepted missing secrets")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ADMIN_SECRET_PIN.*NKOCET_CRYPTO_SECRET"):
                asyncio.run(start_application())

    def test_application_startup_loads_configured_secrets(self):
        environment = self.valid_environment()
        original_admin_pin = server.ADMIN_SECRET_PIN
        original_crypto_secret = server.NKOCET_CRYPTO_SECRET

        async def start_application():
            with patch.object(server, "init_db"):
                async with server.lifespan(server.app):
                    self.assertTrue(secrets.compare_digest(
                        server.ADMIN_SECRET_PIN, environment["ADMIN_SECRET_PIN"]
                    ))
                    self.assertTrue(secrets.compare_digest(
                        server.NKOCET_CRYPTO_SECRET, environment["NKOCET_CRYPTO_SECRET"]
                    ))

        try:
            with patch.dict(os.environ, environment, clear=True):
                asyncio.run(start_application())
        finally:
            server.ADMIN_SECRET_PIN = original_admin_pin
            server.NKOCET_CRYPTO_SECRET = original_crypto_secret

    def test_required_secrets_reject_placeholders_and_weak_values(self):
        environment = self.valid_environment()
        environment["ADMIN_SECRET_PIN"] = "replace-this-admin-pin"
        with self.assertRaisesRegex(ValueError, "ADMIN_SECRET_PIN"):
            server.load_server_configuration(environment)

        environment = self.valid_environment()
        environment["NKOCET_CRYPTO_SECRET"] = "short"
        with self.assertRaisesRegex(ValueError, "NKOCET_CRYPTO_SECRET"):
            server.load_server_configuration(environment)

        environment = self.valid_environment()
        environment["ADMIN_SECRET_PIN"] = environment["NKOCET_CRYPTO_SECRET"]
        with self.assertRaisesRegex(ValueError, "must differ"):
            server.load_server_configuration(environment)

    def test_smtp_placeholder_credentials_are_rejected(self):
        environment = self.valid_environment()
        environment.update({
            "SMTP_USER": "sender@college.invalid",
            "SMTP_PASSWORD": "replace-this-password",
        })
        with self.assertRaisesRegex(ValueError, "SMTP_PASSWORD"):
            server.load_server_configuration(environment)

    def test_smtp_is_optional_but_requires_complete_valid_settings(self):
        environment = self.valid_environment()
        config = server.load_server_configuration(environment)
        self.assertFalse(config["smtp_user"])
        self.assertFalse(config["smtp_password"])

        environment["SMTP_USER"] = "sender@example.invalid"
        with self.assertRaisesRegex(ValueError, "both be set"):
            server.load_server_configuration(environment)

        environment["SMTP_PASSWORD"] = secrets.token_urlsafe(24)
        environment["SMTP_PORT"] = "not-a-port"
        with self.assertRaisesRegex(ValueError, "SMTP_PORT"):
            server.load_server_configuration(environment)

        environment["SMTP_PORT"] = "65536"
        with self.assertRaisesRegex(ValueError, "SMTP_PORT"):
            server.load_server_configuration(environment)

    def test_smtp_configuration_comes_only_from_environment_and_cleans_legacy_db(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_db_path = server.DB_PATH
            server.DB_PATH = os.path.join(temp_dir, "test.db")
            try:
                server.init_db()
                with closing(sqlite3.connect(server.DB_PATH)) as conn:
                    with conn:
                        conn.execute(
                            "INSERT INTO system_settings (key, value) VALUES ('smtp_password', 'legacy-db-value')"
                        )

                environment = self.valid_environment()
                environment.update({
                    "SMTP_USER": "sender@college.invalid",
                    "SMTP_PASSWORD": secrets.token_urlsafe(24),
                    "SMTP_HOST": "smtp.example.invalid",
                    "SMTP_PORT": "2525",
                })
                with patch.dict(os.environ, environment, clear=True):
                    smtp_config = server.get_smtp_config()
                    self.assertEqual(smtp_config["user"], "sender@college.invalid")
                    self.assertEqual(smtp_config["host"], "smtp.example.invalid")
                    self.assertEqual(smtp_config["port"], 2525)
                    self.assertTrue(secrets.compare_digest(
                        smtp_config["password"], environment["SMTP_PASSWORD"]
                    ))

                    server.init_db()
                    with closing(sqlite3.connect(server.DB_PATH)) as conn:
                        legacy_count = conn.execute(
                            "SELECT COUNT(*) FROM system_settings WHERE key LIKE 'smtp_%'"
                        ).fetchone()[0]
                    self.assertEqual(legacy_count, 0)
            finally:
                server.DB_PATH = original_db_path

    def test_legacy_admin_smtp_save_endpoint_rejects_credentials(self):
        request = Request({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/admin/smtp-config",
            "raw_path": b"/api/admin/smtp-config",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        })
        with patch.object(server, "verify_admin_access"):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(server.save_admin_smtp_config(request))
        self.assertEqual(raised.exception.status_code, 410)

    def test_admin_smtp_status_does_not_return_password(self):
        request = Request({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/admin/smtp-config",
            "raw_path": b"/api/admin/smtp-config",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        })
        environment = self.valid_environment()
        environment.update({
            "SMTP_USER": "sender@college.invalid",
            "SMTP_PASSWORD": secrets.token_urlsafe(24),
        })
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(server, "verify_admin_access"):
                result = asyncio.run(server.get_admin_smtp_config(request))
        self.assertNotIn("password", result)
        self.assertNotIn("masked_password", result)
        self.assertTrue(result["configured"])


if __name__ == "__main__":
    unittest.main()
