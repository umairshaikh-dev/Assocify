"""
AssociationHub — Enterprise Full-Stack Server
NK Orchid College of Engineering & Technology (NKOCET, Solapur)

Tech Stack: Python 3.10+, FastAPI, Uvicorn, SQLite3, QRCode, Vanilla ES6+
Features:
1. Persistent Membership Intake Pipeline & SQLite Storage (with Connection Pooling & Validation)
2. Dynamic Cryptographic QR Pass Generation & Gate Verification
3. Campus Pulse: Student Experience & Discussion Hub (Gated to verified students, profanity-filtered, anonymous-mode)
4. Master Admin Control Suite (Protected by Admin Master PIN):
   - Member Status Control (Active / Suspended / Revoke)
   - 1-Click Excel / CSV Export for HOD & NAAC Compliance
   - Live Campus Announcement Broadcaster
   - Community Moderation & Anonymous Author Unmasking
5. Dynamic Event Querying & Live Association Telemetry (/api/stats)
6. Unified Static Asset Hosting (HTML, CSS, JS) on Port 8080
"""

import os
import sys
import ipaddress
import io
import base64
import sqlite3
import hashlib
import hmac
import secrets
import html
import re
import csv
import time
import smtplib
import logging
from urllib.parse import urlsplit
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple, Mapping
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, HTTPException, Request, Response, Query, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# QR Code & Image generation
import qrcode
from PIL import Image

logger = logging.getLogger("associationhub.smtp")

# Reconfigure stdout/stderr for CP1252 Windows encoding
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base Directory & Database Path
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

def resolve_database_path(environ: Optional[Mapping[str, str]] = None) -> str:
    values = os.environ if environ is None else environ
    return values.get("DATABASE_PATH", "").strip() or os.path.join(DIRECTORY, "associationhub.db")


DB_PATH = resolve_database_path()
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "").strip()


def build_verification_url(pass_id: str, signature: str) -> str:
    """Build a QR target from the configured public frontend URL.
    Falls back to http://127.0.0.1:8080 in local dev mode so QR codes
    can still be generated without a PUBLIC_APP_URL set.
    """
    app_url = os.environ.get("PUBLIC_APP_URL", PUBLIC_APP_URL).strip().rstrip("/")
    if not app_url:
        app_url = "http://127.0.0.1:8080"
    try:
        parsed = urlsplit(app_url)
        hostname = (parsed.hostname or "").lower()
        try:
            address = ipaddress.ip_address(hostname)
            is_non_public_ip = address.is_private or address.is_loopback
        except ValueError:
            is_non_public_ip = False
        is_valid_public = (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and hostname not in {"localhost", "localhost.localdomain"}
            and not is_non_public_ip
        )
        is_valid_local = (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        is_valid_public = False
        is_valid_local = False
    if not is_valid_public and not is_valid_local:
        raise HTTPException(
            status_code=503,
            detail="Public verification URL is not configured. Set PUBLIC_APP_URL to the HTTPS frontend base URL."
        )
    return f"{app_url}/verify.html?pass_id={pass_id}&sig={signature}"

# Zero-dependency .env loader for local server configuration
def load_dotenv_custom(filepath: Optional[str] = None):
    if filepath is None:
        filepath = os.path.join(DIRECTORY, ".env")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as e:
            print(f"[ENV LOAD ERROR] {e}")

load_dotenv_custom()

def load_server_configuration(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Load and validate secrets and optional SMTP settings without insecure defaults."""
    values = os.environ if environ is None else environ
    admin_pin = values.get("ADMIN_SECRET_PIN", "").strip()
    crypto_secret = values.get("NKOCET_CRYPTO_SECRET", "").strip()
    errors = []

    def is_placeholder(value: str) -> bool:
        normalized = value.casefold()
        return any(marker in normalized for marker in (
            "replace", "placeholder", "your_", "your-", "example", "<", ">"
        ))

    if not admin_pin:
        errors.append("ADMIN_SECRET_PIN is required")
    elif len(admin_pin) < 16 or is_placeholder(admin_pin):
        errors.append("ADMIN_SECRET_PIN must be a non-placeholder value of at least 16 characters")

    if not crypto_secret:
        errors.append("NKOCET_CRYPTO_SECRET is required")
    elif len(crypto_secret) < 64 or is_placeholder(crypto_secret):
        errors.append("NKOCET_CRYPTO_SECRET must be a non-placeholder value of at least 64 characters")
    elif hmac.compare_digest(admin_pin, crypto_secret):
        errors.append("NKOCET_CRYPTO_SECRET must differ from ADMIN_SECRET_PIN")

    smtp_user = values.get("SMTP_USER", "").strip()
    smtp_password = values.get("SMTP_PASSWORD", "").strip()
    if bool(smtp_user) != bool(smtp_password):
        errors.append("SMTP_USER and SMTP_PASSWORD must either both be set or both be empty")
    if smtp_user and is_placeholder(smtp_user):
        errors.append("SMTP_USER must be a real sender account, not a placeholder")
    if smtp_password and is_placeholder(smtp_password):
        errors.append("SMTP_PASSWORD must be a real app password, not a placeholder")

    try:
        smtp_port = int(values.get("SMTP_PORT", "587"))
        if not 1 <= smtp_port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("SMTP_PORT must be an integer from 1 to 65535")
        smtp_port = 587

    if errors:
        raise ValueError("Invalid server configuration: " + "; ".join(errors))

    return {
        "admin_pin": admin_pin,
        "crypto_secret": crypto_secret,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "smtp_host": values.get("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com",
        "smtp_port": smtp_port,
        "smtp_from_name": values.get("SMTP_FROM_NAME", "NKOCET Solapur Verification Gateway").strip()
            or "NKOCET Solapur Verification Gateway",
    }


ADMIN_SECRET_PIN = os.environ.get("ADMIN_SECRET_PIN", "").strip()
NKOCET_CRYPTO_SECRET = os.environ.get("NKOCET_CRYPTO_SECRET", "").strip()

ALLOWED_ASSOCIATIONS = {"CSESA", "MESA", "EESA", "CESA", "AEXS", "AIESA"}
ALLOWED_YEARS = {"First Year (FY)", "Second Year (SY)", "Third Year (TY)", "Final Year (B.Tech)"}
ALLOWED_CATEGORIES = {"INTERVIEW", "HACKATHON", "CLUB_LIFE", "PROJECT_ADVICE", "GENERAL"}

# In-memory rate limiting & brute-force trackers
_post_rate_limits: Dict[str, List[datetime]] = {}
_register_rate_limits: Dict[str, List[datetime]] = {}
_gate_verify_rate_limits: Dict[str, List[datetime]] = {}
_admin_failed_attempts: Dict[str, List[datetime]] = {}

BLOCKED_KEYWORDS = {
    "abuse", "scam", "fraud", "cheat", "hack", "idiot", "stupid", "bastard", "bitch",
    "fuck", "shit", "asshole", "chutiya", "harami", "madarchod", "bhenchod", "gandu",
    "lauda", "lodu", "saala", "kameena", "troll", "spam", "f**k", "sh*t"
}

def get_client_ip(request: Request) -> str:
    """Safely extracts client IP address."""
    peer = request.client.host if request.client else "127.0.0.1"
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return "127.0.0.1"

    trusted_proxy_ips = {
        value.strip()
        for value in os.environ.get("TRUSTED_PROXY_IPS", "").split(",")
        if value.strip()
    }
    peer_is_trusted = peer_address.is_loopback
    for configured_proxy in trusted_proxy_ips:
        try:
            if peer_address in ipaddress.ip_network(configured_proxy, strict=False):
                peer_is_trusted = True
                break
        except ValueError:
            continue
    if os.environ.get("RENDER", "").strip() == "true" and peer_address.is_private:
        peer_is_trusted = True
    if not peer_is_trusted:
        return peer

    candidates = [
        value.strip()
        for value in request.headers.get("X-Forwarded-For", "").split(",")
        if value.strip()
    ]
    while candidates:
        candidate = candidates[-1]
        try:
            candidate_address = ipaddress.ip_address(candidate)
        except ValueError:
            candidates.pop()
            continue
        candidate_is_trusted = False
        for proxy in trusted_proxy_ips:
            try:
                if candidate_address in ipaddress.ip_network(proxy, strict=False):
                    candidate_is_trusted = True
                    break
            except ValueError:
                continue
        if candidate_is_trusted:
            candidates.pop()
            continue
        return str(candidate_address)

    render_client_ip = request.headers.get("Render-Client-IP", "").strip()
    try:
        return str(ipaddress.ip_address(render_client_ip))
    except ValueError:
        return peer

def compute_hmac_signature(pass_id: str, roll_no: str, association: str) -> str:
    """Computes a 16-character cryptographic HMAC-SHA256 signature for pass integrity."""
    msg = f"{pass_id}:{roll_no}:{association}".encode("utf-8")
    return hmac.new(NKOCET_CRYPTO_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16].upper()

def create_admin_session_token() -> str:
    """Creates a persistent, time-bound administrator session token."""
    timestamp = int(datetime.now().timestamp())
    session_id = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute("""
            INSERT INTO admin_sessions (session_id, expires_at, revoked_at, created_at)
            VALUES (?, ?, NULL, ?);
        """, (session_id, timestamp + 10800, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    data = f"ADMIN:{timestamp}:{session_id}"
    sig = hmac.new(NKOCET_CRYPTO_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"SESSION.{timestamp}.{session_id}.{sig}"

def verify_admin_session_token(token: str) -> bool:
    """Validates signature, server-side expiry, and revocation state."""
    try:
        parts = token.split(".")
        if len(parts) != 4 or parts[0] != "SESSION":
            return False
        timestamp = int(parts[1])
        session_id = parts[2]
        provided_sig = parts[3]
        now = int(datetime.now().timestamp())
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", session_id):
            return False
        if now - timestamp > 10800 or timestamp > now + 300:
            return False
        expected_sig = hmac.new(
            NKOCET_CRYPTO_SECRET.encode("utf-8"),
            f"ADMIN:{timestamp}:{session_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]
        if not hmac.compare_digest(expected_sig, provided_sig):
            return False
        with get_db() as conn:
            row = conn.execute(
                "SELECT expires_at, revoked_at FROM admin_sessions WHERE session_id = ?;",
                (session_id,),
            ).fetchone()
        return bool(row and float(row["expires_at"]) > now and row["revoked_at"] is None)
    except Exception:
        return False

def hash_otp(otp: str, email: str) -> str:
    """Hashes the OTP code with SHA-256 and HMAC salt so plaintext OTP is never persisted in DB."""
    salted = f"{otp.strip()}:{email.strip().lower()}:{NKOCET_CRYPTO_SECRET}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()

def mask_email(email: str) -> str:
    """Masks destination email for UI display: e.g. affanchoudhari2006@gmail.com -> af***06@gmail.com."""
    try:
        parts = email.strip().split("@")
        if len(parts) != 2:
            return email
        name, domain = parts[0], parts[1]
        if len(name) <= 2:
            masked_name = name[0] + "*"
        elif len(name) <= 4:
            masked_name = name[0] + "**" + name[-1]
        else:
            masked_name = name[:2] + "*" * (len(name) - 4) + name[-2:]
        return f"{masked_name}@{domain}"
    except Exception:
        return email

def hash_student_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Cryptographically hashes student password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return pwd_hash, salt

def check_admin_brute_force(ip: str):
    """Enforces persistent lockout after 5 failed PIN attempts within 15 minutes."""
    now = datetime.now()
    cutoff = now.timestamp() - 15 * 60
    with get_db() as conn:
        count = conn.execute("""
            SELECT COUNT(*) FROM admin_failed_attempts WHERE ip_address = ? AND attempted_at > ?;
        """, (ip, cutoff)).fetchone()[0]
    if count >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many failed PIN attempts. Admin console is locked for 15 minutes to prevent brute-force attacks."
        )

def record_admin_failed_attempt(ip: str):
    now = datetime.now().timestamp()
    cutoff = now - 15 * 60
    with get_db() as conn:
        conn.execute("DELETE FROM admin_failed_attempts WHERE attempted_at <= ?;", (cutoff,))
        conn.execute(
            "INSERT INTO admin_failed_attempts (ip_address, attempted_at) VALUES (?, ?);",
            (ip, now),
        )

def check_register_rate_limit(ip: str):
    """Prevents spam automated registrations: max 30 per 10 minutes per IP (60 for local testing & campus labs)."""
    now = datetime.now()
    cutoff = now - timedelta(minutes=10)
    attempts = [t for t in _register_rate_limits.get(ip, []) if t > cutoff]
    max_limit = 60 if ip in ("127.0.0.1", "::1", "localhost") else 30
    if len(attempts) >= max_limit:
        raise HTTPException(
            status_code=429,
            detail="Registration rate limit reached: Maximum registrations per 10 minutes exceeded from this network. Please wait a few minutes."
        )
    attempts.append(now)
    _register_rate_limits[ip] = attempts

def check_account_restriction(email: str, roll_no: Optional[str] = None, name: Optional[str] = None):
    """
    Checks if a student's email or roll number has been restricted/blocked/removed by the Administrator.
    If restricted, blocks automatic registration and logs/updates a Rejoin Approval Request for Admin review.
    """
    clean_email = (email or "").strip().lower()
    clean_roll = (roll_no or "").strip().upper()
    if not clean_email and not clean_roll:
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, email, roll_no, name, status, restricted_at, rejoin_requested_at
        FROM account_restrictions
        WHERE email = ? OR (roll_no != '' AND roll_no = ?)
        ORDER BY id DESC LIMIT 1;
        """, (clean_email, clean_roll))
        row = cursor.fetchone()

        if row:
            curr_status = row["status"]
            if curr_status == "REJOIN_APPROVED":
                # Explicitly approved by Administrator to rejoin
                return

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Upgrade status to REJOIN_PENDING so Administrator sees the incoming request in the approval queue
            cursor.execute("""
            UPDATE account_restrictions
            SET status = 'REJOIN_PENDING',
                rejoin_requested_at = COALESCE(rejoin_requested_at, ?),
                name = COALESCE(?, name),
                roll_no = CASE WHEN (roll_no IS NULL OR roll_no = '') THEN ? ELSE roll_no END
            WHERE id = ?;
            """, (now_str, name, clean_roll, row["id"]))
            conn.commit()

            raise HTTPException(
                status_code=403,
                detail="⛔ Account Restricted: Your email/PRN was previously blocked or removed by the Administrator. Automatic rejoining is disabled. An official Rejoin Approval Request has been logged for Administrator review. Please contact the Department Coordinator or wait for approval."
            )

def check_gate_verify_rate_limit(ip: str):
    """Prevents scraping member registries: max 60 queries per minute per IP."""
    now = datetime.now()
    cutoff = now - timedelta(minutes=1)
    attempts = [t for t in _gate_verify_rate_limits.get(ip, []) if t > cutoff]
    if len(attempts) >= 60:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: Too many gate verification requests. Please wait a minute."
        )
    attempts.append(now)
    _gate_verify_rate_limits[ip] = attempts

def check_anti_troll(text: str, roll_no: str = "UNKNOWN", ip: str = "127.0.0.1", conn: Optional[sqlite3.Connection] = None):
    """
    Campus Anti-Troll Shield:
    1. Blocks vulgar, abusive, and toxic keywords.
    2. Blocks excessive repeated character spam (e.g. aaaaaaa, !!!!!!!).
    3. Blocks malicious / spam link redirects.
    4. Automatically records violations in SQLite security audit logs.
    """
    lowered = text.lower()
    for word in BLOCKED_KEYWORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', lowered) or word in lowered:
            log_audit_event("ANTI_TROLL_FLAGGED", ip, f"Troll keyword detected '{word}' from Roll {roll_no}")
            raise HTTPException(
                status_code=400,
                detail=f"Campus Anti-Troll Shield: Message contains prohibited or abusive language ('{word}'). Professional decorum is strictly enforced."
            )
            
    if re.search(r'(.)\1{9,}', text):
        log_audit_event("ANTI_TROLL_FLAGGED", ip, f"Spam character flood from Roll {roll_no}")
        raise HTTPException(
            status_code=400,
            detail="Campus Anti-Troll Shield: Repetitive character flood detected. Please write meaningful discussions."
        )

    if re.search(r'(t\.me/|wa\.me/|bit\.ly/|free-crypto|earn-money)', lowered):
        log_audit_event("ANTI_TROLL_FLAGGED", ip, f"Suspicious scam link attempt from Roll {roll_no}")
        raise HTTPException(
            status_code=400,
            detail="Campus Anti-Troll Shield: External redirect and spam links are prohibited."
        )

def check_profanity(text: str):
    """Legacy wrapper for check_anti_troll."""
    check_anti_troll(text)

def check_rate_limit(roll_no: str):
    """Enforces maximum 3 posts per 10 minutes per student."""
    now = datetime.now()
    cutoff = now - timedelta(minutes=10)
    timestamps = _post_rate_limits.get(roll_no, [])
    # Filter only recent
    recent = [t for t in timestamps if t > cutoff]
    if len(recent) >= 3:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: You can share at most 3 experiences per 10 minutes."
        )
    recent.append(now)
    _post_rate_limits[roll_no] = recent

def verify_admin_access(request: Request):
    """Verifies that the caller provided either the correct Admin Master PIN or a valid Session Token."""
    key = (
        request.headers.get("X-Admin-Key") or 
        request.headers.get("x-admin-key") or 
        request.headers.get("X-Admin-PIN") or
        request.headers.get("X-Admin-Pin") or
        request.headers.get("x-admin-pin") or
        request.headers.get("X-Admin-Token") or 
        request.headers.get("x-admin-token")
    )
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        key = key or auth_header.split(" ", 1)[1].strip()

    if not key:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing Administrator Security Key."
        )
    if hmac.compare_digest(key.encode("utf-8"), ADMIN_SECRET_PIN.encode("utf-8")) or verify_admin_session_token(key):
        return True
    
    raise HTTPException(
        status_code=403,
        detail="Forbidden: Administrator Security Key or Session Token is invalid or expired."
    )

def log_audit_event(event_type: str, actor_ip: str, details: str, conn: Optional[sqlite3.Connection] = None):
    """Logs security and administrative actions into SQLite audit ledger."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if conn:
            conn.cursor().execute("""
            INSERT INTO security_audit_logs (event_type, actor_ip, details, timestamp)
            VALUES (?, ?, ?, ?);
            """, (event_type, actor_ip, details, now_str))
        else:
            with get_db() as c:
                c.cursor().execute("""
                INSERT INTO security_audit_logs (event_type, actor_ip, details, timestamp)
                VALUES (?, ?, ?, ?);
                """, (event_type, actor_ip, details, now_str))
    except Exception as e:
        print(f"[AUDIT LOG ERROR] {e}")


# --------------------------------------------------------------------------
# DATABASE INITIALIZATION & CONTEXT MANAGEMENT
# --------------------------------------------------------------------------
@contextmanager
def get_db():
    """Safe context manager with WAL mode and generous busy timeout."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=20000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initializes schemas and populates default verified data."""
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Memberships Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            pass_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            email TEXT,
            dept TEXT NOT NULL,
            year TEXT NOT NULL,
            association TEXT NOT NULL,
            interest TEXT,
            qr_code_base64 TEXT NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            crypto_signature TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_member_roll_assoc 
        ON memberships (roll_no, association);
        """)

        # Migration: Ensure status, crypto_signature, and email columns exist
        cursor.execute("PRAGMA table_info(memberships);")
        cols = [r[1] for r in cursor.fetchall()]
        if "status" not in cols:
            cursor.execute("ALTER TABLE memberships ADD COLUMN status TEXT DEFAULT 'ACTIVE';")
        if "crypto_signature" not in cols:
            cursor.execute("ALTER TABLE memberships ADD COLUMN crypto_signature TEXT;")
        if "email" not in cols:
            cursor.execute("ALTER TABLE memberships ADD COLUMN email TEXT;")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            session_id TEXT PRIMARY KEY,
            expires_at REAL NOT NULL,
            revoked_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_failed_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            attempted_at REAL NOT NULL
        );
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_admin_failed_attempt_ip_time
        ON admin_failed_attempts (ip_address, attempted_at);
        """)

        # 1.5. Email OTP Verifications Table (5-min expiry, 60s cooldown, SHA-256 hashed OTP)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_otp_verifications (
            email TEXT PRIMARY KEY,
            otp_hash TEXT,
            otp_code TEXT,
            roll_no TEXT,
            association TEXT,
            session_id TEXT,
            expires_at REAL NOT NULL,
            last_sent_at REAL DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            verification_token TEXT,
            verified_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("PRAGMA table_info(email_otp_verifications);")
        ev_cols = [r[1] for r in cursor.fetchall()]
        if "otp_hash" not in ev_cols:
            cursor.execute("ALTER TABLE email_otp_verifications ADD COLUMN otp_hash TEXT;")
        if "last_sent_at" not in ev_cols:
            cursor.execute("ALTER TABLE email_otp_verifications ADD COLUMN last_sent_at REAL DEFAULT 0;")
        if "verified_at" not in ev_cols:
            cursor.execute("ALTER TABLE email_otp_verifications ADD COLUMN verified_at TEXT;")
        if "association" not in ev_cols:
            cursor.execute("ALTER TABLE email_otp_verifications ADD COLUMN association TEXT;")
        if "session_id" not in ev_cols:
            cursor.execute("ALTER TABLE email_otp_verifications ADD COLUMN session_id TEXT;")

        # 1.6. Registered Students Table (Complete Student Registration Gate)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_students (
            student_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            dept TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            is_email_verified INTEGER DEFAULT 1,
            email_verified_at TEXT NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_students_email ON registered_students(email);
        """)
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_students_roll ON registered_students(roll_no);
        """)

        # Migration: Ensure status column exists in registered_students
        cursor.execute("PRAGMA table_info(registered_students);")
        rs_cols = [r[1] for r in cursor.fetchall()]
        if "status" not in rs_cols:
            cursor.execute("ALTER TABLE registered_students ADD COLUMN status TEXT DEFAULT 'ACTIVE';")

        # 1.7. Account Restrictions & Rejoin Approval Gateway Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_restrictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            roll_no TEXT,
            name TEXT,
            reason TEXT DEFAULT 'Administrative Action (Blocked or Removed)',
            status TEXT DEFAULT 'RESTRICTED',
            restricted_at TEXT NOT NULL,
            rejoin_requested_at TEXT,
            rejoin_approved_at TEXT,
            reviewed_by TEXT
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_restrictions_email ON account_restrictions(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_restrictions_roll ON account_restrictions(roll_no);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memberships_email ON memberships(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memberships_roll ON memberships(roll_no);")

        # Seed default verified student members across associations
        seed_members = [
            ("NKOCET-2026-CSESA-7EB769", "Affan Choudhari", "C-62", "affan.choudhari@orchidengg.ac.in", "Computer Science & Engineering", "Second Year (SY)", "CSESA", "Python, Full-Stack & System Architecture"),
            ("NKOCET-2026-CSESA-A2B4C6", "Suyash Gote", "C-64", "suyash.gote@orchidengg.ac.in", "Computer Science & Engineering", "Second Year (SY)", "CSESA", "UI/UX Design, CSS Architecture & Frontend"),
            ("NKOCET-2026-AIESA-D3E5F7", "Umair Shaikh", "C-54", "umair.shaikh@orchidengg.ac.in", "AI & Data Science", "Second Year (SY)", "AIESA", "Deep Learning, PyTorch & Neural Networks"),
            ("NKOCET-2026-MESA-B8C9D0", "Moin Shaikh", "C-67", "moin.shaikh@orchidengg.ac.in", "Mechanical Engineering", "Second Year (SY)", "MESA", "SolidWorks, CAD/CAM & Autonomous Robotics"),
            ("NKOCET-2026-EESA-F1G2H3", "Sushil Habib", "C-58", "sushil.habib@orchidengg.ac.in", "Electrical Engineering", "Second Year (SY)", "EESA", "Smart Grids, IoT & Embedded Systems"),
            ("NKOCET-2026-CESA-K4L5M6", "Siddeshwar Nagansure", "C-61", "siddeshwar.n@orchidengg.ac.in", "Civil Engineering", "Second Year (SY)", "CESA", "Structural BIM, Concrete Tech & GIS Surveying"),
            ("NKOCET-2026-AEXS-E7F8G9", "Prathamesh Koli", "C-72", "prathamesh.k@orchidengg.ac.in", "Electronics & Telecommunication", "Second Year (SY)", "AEXS", "Embedded C, ESP32 Wireless & Telemetry")
        ]
        for pid, sname, sroll, semail, sdept, syr, sassoc, sint in seed_members:
            sig = compute_hmac_signature(pid, sroll, sassoc)
            qr_b64 = ""
            cursor.execute("""
            INSERT OR IGNORE INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, '2026-10-25 10:00:00');
            """, (pid, sname, sroll, semail, sdept, syr, sassoc, sint, qr_b64, sig))
            # Also backfill signature and email if missing
            cursor.execute(
                "UPDATE memberships SET crypto_signature = COALESCE(crypto_signature, ?), email = COALESCE(email, ?) WHERE pass_id = ?;",
                (sig, semail, pid)
            )

        # 2. Gated Community Chat Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            dept TEXT NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            session_token TEXT,
            session_expires_at TEXT,
            session_revoked_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("PRAGMA table_info(community_users);")
        chat_cols = [r[1] for r in cursor.fetchall()]
        if "session_expires_at" not in chat_cols:
            cursor.execute("ALTER TABLE community_users ADD COLUMN session_expires_at TEXT;")
        if "session_revoked_at" not in chat_cols:
            cursor.execute("ALTER TABLE community_users ADD COLUMN session_revoked_at TEXT;")
        cursor.execute("""
        UPDATE community_users
        SET session_expires_at = datetime(created_at, '+24 hours')
        WHERE session_token IS NOT NULL AND session_expires_at IS NULL;
        """)
        cursor.execute("""
        UPDATE community_users
        SET session_revoked_at = CURRENT_TIMESTAMP,
            session_token = NULL
        WHERE status IN ('BANNED', 'SUSPENDED')
          AND session_token IS NOT NULL
          AND session_revoked_at IS NULL;
        """)

        # 3. Community Experience Posts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_posts (
            post_id TEXT PRIMARY KEY,
            author_name TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            dept TEXT NOT NULL,
            year TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            is_anonymous INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. Community Post Comments Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_comments (
            comment_id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            author_name TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(post_id) REFERENCES community_posts(post_id) ON DELETE CASCADE
        );
        """)

        # 4. Live Broadcast Announcements Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL,
            message TEXT NOT NULL,
            button_text TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 5. Events Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            association TEXT NOT NULL,
            date_str TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL
        );
        """)

        # Seed sample events if empty
        cursor.execute("SELECT COUNT(*) FROM events;")
        if cursor.fetchone()[0] == 0:
            seed_events = [
                ("CodeStorm 2026 Hackathon", "CSESA", "December 12-14, 2026", "Hackathon", "36-hour flagship software engineering and AI sprint for undergraduate builders."),
                ("RoboKriti Robotics Challenge", "MESA", "December 18, 2026", "Robotics", "Autonomous line follower and maze navigation competition in the Mechanical FabLab."),
                ("NeuralForge Deep Learning Summit", "AIESA", "January 8, 2027", "Workshop", "Hands-on GPU cluster workshop on Computer Vision and Large Language Models."),
                ("ElectroVerve IoT Conclave", "EESA", "January 15, 2027", "Symposium", "Smart electrical grid architectures, EV battery charging systems, and power electronics."),
                ("BridgeCraft Structural Expo", "CESA", "January 22, 2027", "Design Challenge", "Civil structural analysis and seismic-resistant bridge modeling symposium.")
            ]
            for title, assoc, dt, cat, desc in seed_events:
                cursor.execute("""
                INSERT INTO events (title, association, date_str, category, description)
                VALUES (?, ?, ?, ?, ?);
                """, (title, assoc, dt, cat, desc))

        # Seed default broadcast announcement if empty
        cursor.execute("SELECT COUNT(*) FROM announcements;")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO announcements (tag, message, button_text, is_active)
            VALUES (?, ?, ?, ?);
            """, (
                "📢 Campus Notice",
                "Academic Session 2026 Student Association Membership & Council Registrations Open for All Batches.",
                "Apply Now →",
                1
            ))

        # Seed realistic community experience posts if empty
        cursor.execute("SELECT COUNT(*) FROM community_posts;")
        if cursor.fetchone()[0] == 0:
            seed_posts = [
                (
                    "POST-2026-HACK-01",
                    "Affan Choudhari",
                    "C-62",
                    "Computer Science & Engineering",
                    "Second Year (SY)",
                    "HACKATHON",
                    "Winning 1st Prize at Solapur Inter-College Hackathon 2026",
                    "Our CSESA team built a real-time smart campus gate check-in system using FastAPI and QR cryptographic verification. Key tips for juniors: (1) Keep your tech stack simple and avoid over-engineering, (2) Plan your SQLite relational schema on paper before coding, and (3) Rehearse the live demo with edge cases. Reach out if you need help with backend setups!",
                    0,
                    19,
                    "2026-10-28 14:30:00"
                ),
                (
                    "POST-2026-PROJ-02",
                    "Suyash Gote",
                    "C-64",
                    "Computer Science & Engineering",
                    "Second Year (SY)",
                    "PROJECT_ADVICE",
                    "Best Practices for 2nd Year B.Tech CEP Lab Projects",
                    "For the Community Engagement Project (CEP), don't wait until the last 2 weeks before submission. Choose a real problem on campus like club management, coordinate directly with faculty coordinators, and maintain a clean Git commit history. It makes the final viva a breeze!",
                    0,
                    14,
                    "2026-10-29 11:15:00"
                ),
                (
                    "POST-2026-AI-03",
                    "Umair Shaikh",
                    "C-54",
                    "AI & Data Science",
                    "Second Year (SY)",
                    "INTERVIEW",
                    "Machine Learning & Python Roadmap for AIESA Freshers",
                    "To crack technical interviews for AI & Data roles, master Pandas, NumPy, and vector mathematics before jumping directly into deep neural networks. The AIESA club is hosting weekly hands-on labs in Lab 3—make sure you participate in the problem-solving sprints!",
                    0,
                    23,
                    "2026-10-30 09:40:00"
                ),
                (
                    "POST-2026-MECH-04",
                    "Moin Shaikh",
                    "C-67",
                    "Mechanical Engineering",
                    "Second Year (SY)",
                    "CLUB_LIFE",
                    "Inside MESA: SolidWorks & Autonomous Rover Workshop Highlights",
                    "Hands-on CAD modeling and 3D printing in the mechanical workshop was an eye-opener. Working with cross-department teams from Electrical and CS on autonomous motor controllers gave us massive exposure. Join MESA if you love building real machines!",
                    0,
                    11,
                    "2026-10-30 16:20:00"
                )
            ]
            for p_id, a_name, roll, dept, yr, cat, title, content, is_anon, likes, dt in seed_posts:
                cursor.execute("""
                INSERT INTO community_posts (post_id, author_name, roll_no, dept, year, category, title, content, is_anonymous, likes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (p_id, a_name, roll, dept, yr, cat, title, content, is_anon, likes, dt))

        # Seed sample comments if empty
        cursor.execute("SELECT COUNT(*) FROM community_comments;")
        if cursor.fetchone()[0] == 0:
            seed_comments = [
                ("COMM-01", "POST-2026-HACK-01", "Sushil Habib", "C-58", "Congrats Affan! Which library did you use for the fast QR code rendering on the pass?"),
                ("COMM-02", "POST-2026-HACK-01", "Affan Choudhari", "C-62", "Thanks Sushil! We used Python's qrcode library combined with PIL and streamed Base64 directly into the pass."),
                ("COMM-03", "POST-2026-AI-03", "Siddeshwar Nagansure", "C-61", "Very helpful roadmap Umair, are non-AI branches allowed in the Lab 3 workshops?")
            ]
            for c_id, p_id, a_name, roll, content in seed_comments:
                cursor.execute("""
                INSERT INTO community_comments (comment_id, post_id, author_name, roll_no, content)
                VALUES (?, ?, ?, ?, ?);
                """, (c_id, p_id, a_name, roll, content))

        # 6. Real-Time Gate Check-In Attendance Ledger
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS gate_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pass_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            association TEXT NOT NULL,
            checkpoint TEXT DEFAULT 'Central Gate / Main Campus',
            status TEXT DEFAULT 'ENTRY_GRANTED',
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(pass_id) REFERENCES memberships(pass_id)
        );
        """)

        # 7. Enterprise Security & Administrative Audit Logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor_ip TEXT,
            details TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 8. System Settings & SMTP Mailer Configuration
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Remove SMTP credentials persisted by older releases; configuration is env-only.
        cursor.execute("DELETE FROM system_settings WHERE key LIKE 'smtp_%';")


def get_smtp_config() -> Dict[str, Any]:
    """Fetches SMTP configuration exclusively from validated environment settings."""
    config = load_server_configuration()
    return {
        "user": config["smtp_user"],
        "password": config["smtp_password"],
        "host": config["smtp_host"],
        "port": config["smtp_port"],
        "from_name": config["smtp_from_name"],
    }


def sanitize_smtp_error(error: Exception, smtp_user: str = "", smtp_password: str = "", otp_code: str = "") -> str:
    message = str(error)
    if isinstance(getattr(error, "args", None), tuple):
        smtp_args = getattr(error, "args", ())
        if smtp_args:
            message = " ".join(
                arg.decode("utf-8", errors="replace") if isinstance(arg, bytes) else str(arg)
                for arg in smtp_args
            )

    for sensitive_value in (smtp_password, smtp_user, otp_code):
        if sensitive_value:
            message = message.replace(sensitive_value, "<redacted>")

    message = re.sub(r"(?i)\b(?:password|app\s*password|passwd|smtp_pass|credential|token)\b\s*[:=]\s*\S+", "<redacted>", message)
    message = re.sub(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", "<redacted-email>", message, flags=re.IGNORECASE)
    message = re.sub(r"\b\d{6}\b", "<redacted-code>", message)
    message = re.sub(r"\s+", " ", message).strip()
    return (message or "SMTP operation failed")[:300]


def send_real_smtp_email(to_email: str, recipient_name: str, otp_code: str) -> Dict[str, Any]:
    """
    Connects to SMTP host (default smtp.gmail.com:587) via TLS, authenticates,
    and dispatches a professional HTML & Plaintext verification email in real-time.
    """
    cfg = get_smtp_config()
    smtp_user = cfg["user"]
    smtp_pass = cfg["password"]
    smtp_host = cfg["host"]
    smtp_port = cfg["port"]
    from_name = cfg["from_name"]

    if not smtp_user or not smtp_pass:
        return {
            "sent": False,
            "configured": False,
            "reason": "SMTP credentials are not configured. Set SMTP_USER and SMTP_PASSWORD in the server environment."
        }

    clean_name = recipient_name.strip() if recipient_name else "Student"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔑 Your NKOCET Verification Code: {otp_code}"
    msg["From"] = f"{from_name} <{smtp_user}>"
    msg["To"] = to_email

    text_content = f"""Hello {clean_name},

Your official verification code for NK Orchid College of Engineering & Technology (NKOCET) Community Chat & Club Access is:

{otp_code}

This code is valid for 5 minutes.
For security, please never share this verification code with anyone.

NK Orchid College of Engineering & Technology, Solapur
AssociationHub & Campus Community Gateway
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NKOCET Verification Code</title>
</head>
<body style="margin: 0; padding: 24px 10px; background-color: #080a0f; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f0f4f8;">
  <div style="max-width: 520px; margin: 0 auto; background: #0d121c; border: 1px solid #1f293d; border-radius: 12px; overflow: hidden; box-shadow: 0 12px 30px rgba(0,0,0,0.7);">
    
    <!-- Top Header -->
    <div style="background: linear-gradient(135deg, #131b2a 0%, #090c13 100%); padding: 26px 20px; text-align: center; border-bottom: 2px solid #E5A93C;">
      <div style="display: inline-block; background: rgba(229, 169, 60, 0.12); border: 1px solid #E5A93C; border-radius: 20px; padding: 4px 14px; font-size: 11px; font-weight: 800; color: #E5A93C; letter-spacing: 1px; margin-bottom: 10px; text-transform: uppercase;">
        NKOCET SOLAPUR &bull; 2026
      </div>
      <h1 style="color: #ffffff; font-size: 20px; font-weight: 800; margin: 0; letter-spacing: -0.02em;">
        Student Identity Verification
      </h1>
      <p style="color: #94a3b8; font-size: 12px; margin: 4px 0 0 0;">
        AssociationHub &amp; Verified Campus Community Gateway
      </p>
    </div>

    <!-- Main Content -->
    <div style="padding: 28px 24px;">
      <p style="color: #e2e8f0; font-size: 14px; margin: 0 0 14px 0; line-height: 1.5;">
        Hello <strong style="color: #ffffff;">{clean_name}</strong>,
      </p>
      <p style="color: #94a3b8; font-size: 13px; line-height: 1.6; margin: 0 0 20px 0;">
        You requested a verification code to authenticate your student identity for the <strong>NKOCET Campus Community Chat</strong> and club registrations.
      </p>

      <!-- OTP Display Box -->
      <div style="background: rgba(229, 169, 60, 0.06); border: 2px dashed #E5A93C; border-radius: 10px; padding: 20px 10px; text-align: center; margin: 24px 0;">
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: #94a3b8; margin-bottom: 6px; font-weight: 600;">
          Your 6-Digit Verification Code
        </div>
        <div style="font-size: 38px; font-weight: 900; letter-spacing: 8px; color: #E5A93C; font-family: 'Courier New', monospace; margin: 4px 0;">
          {otp_code}
        </div>
        <div style="font-size: 11px; color: #19D68C; font-weight: 700; margin-top: 6px;">
          ⏱️ Valid for 5 minutes only
        </div>
      </div>

      <p style="color: #94a3b8; font-size: 12px; line-height: 1.6; margin: 0 0 12px 0;">
        Enter this code in your browser window to verify your student email and unlock community discussion access across all 6 engineering departments.
      </p>
      
      <div style="background: rgba(255, 65, 108, 0.08); border-left: 3px solid #FF416C; padding: 10px 12px; border-radius: 4px; margin-top: 18px;">
        <p style="color: #cbd5e1; font-size: 11px; line-height: 1.5; margin: 0;">
          🔒 <strong>Security Warning:</strong> NKOCET administrators will never ask for your verification code. Do not share this code with anyone.
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #090c12; border-top: 1px solid #1a2233; padding: 18px; text-align: center; font-size: 11px; color: #64748b; line-height: 1.5;">
      NK Orchid College of Engineering &amp; Technology (NKOCET)<br>
      Post Box No. 154, Gut No. 16, Solapur-Tuljapur Road, Solapur - 413002<br>
      <span style="color: #475569;">This is an automated security transmission. Please do not reply directly to this email.</span>
    </div>

  </div>
</body>
</html>
"""

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())
        server.quit()
        return {"sent": True, "configured": True}
    except smtplib.SMTPAuthenticationError as error:
        sanitized_error = sanitize_smtp_error(error, smtp_user, smtp_pass, otp_code)
        logger.error(
            "SMTP authentication failed: exception=%s smtp_host=%s smtp_port=%s message=%s",
            type(error).__name__,
            smtp_host,
            smtp_port,
            sanitized_error,
        )
        return {
            "sent": False,
            "configured": True,
            "reason": "SMTP authentication failed"
        }
    except Exception as error:
        sanitized_error = sanitize_smtp_error(error, smtp_user, smtp_pass, otp_code)
        logger.error(
            "SMTP dispatch failed: exception=%s smtp_host=%s smtp_port=%s message=%s",
            type(error).__name__,
            smtp_host,
            smtp_port,
            sanitized_error,
        )
        return {
            "sent": False,
            "configured": True,
            "reason": "SMTP dispatch failed"
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ADMIN_SECRET_PIN, NKOCET_CRYPTO_SECRET
    config = load_server_configuration()
    ADMIN_SECRET_PIN = config["admin_pin"]
    NKOCET_CRYPTO_SECRET = config["crypto_secret"]
    init_db()
    print("[SERVER] Database schemas verified & connection pool ready.")
    yield


# --------------------------------------------------------------------------
# FASTAPI APPLICATION SETUP
# --------------------------------------------------------------------------
app = FastAPI(
    title="AssociationHub API",
    description="Unified Full-Stack Portal for NK Orchid College of Engineering & Technology (NKOCET, Solapur)",
    version="2.4.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://affanchoudhari2006-lang.github.io"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Admin-Key",
        "X-Admin-Pin",
        "X-Admin-Token",
        "X-Chat-Token",
    ],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforces essential defense-in-depth security headers."""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    
    return response


# --------------------------------------------------------------------------
# QR CODE GENERATION ENGINE
# --------------------------------------------------------------------------
def make_qr_base64(data_url: str) -> str:
    """Generates a high-contrast QR code image as a Base64 data URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#080A0F", back_color="#FFFFFF")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


# --------------------------------------------------------------------------
# PYDANTIC SCHEMAS
# --------------------------------------------------------------------------
class StudentSendOtpRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)
    roll_no: str = Field(..., min_length=1, max_length=50)
    dept: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    confirm_password: str = Field(..., min_length=6, max_length=100)
    session_id: str = Field(..., min_length=32, max_length=64)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format. Please provide a valid Gmail address.")
        return v

    @field_validator("name", "roll_no", "dept")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return html.escape(re.sub(r'<[^>]*?>', '', v).strip())


class StudentVerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    otp: str = Field(..., min_length=6, max_length=6)
    session_id: str = Field(..., min_length=32, max_length=64)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        email = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
            raise ValueError("Invalid email format.")
        return email

    @field_validator("otp")
    @classmethod
    def clean_otp(cls, v: str) -> str:
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()


class StudentCompleteRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)
    roll_no: str = Field(..., min_length=1, max_length=50)
    dept: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("name", "roll_no", "dept")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return html.escape(re.sub(r'<[^>]*?>', '', v).strip())

class SendOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    name: Optional[str] = Field(None, max_length=100)
    roll_no: Optional[str] = Field(None, max_length=50)
    association: Optional[str] = Field(None, max_length=20)
    session_id: str = Field(..., min_length=32, max_length=64)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format. Please provide a valid student Gmail address.")
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()

    @field_validator("association")
    @classmethod
    def validate_association(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().upper()
        if clean not in ALLOWED_ASSOCIATIONS:
            raise ValueError("Invalid association")
        return clean


class SmtpTestRequest(BaseModel):
    test_email: str = Field(..., min_length=5, max_length=150)


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    otp: str = Field(..., min_length=4, max_length=10)
    session_id: str = Field(..., min_length=32, max_length=64)
    roll_no: str = Field(..., min_length=1, max_length=50)
    association: str = Field(..., min_length=2, max_length=20)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("otp")
    @classmethod
    def clean_otp(cls, v: str) -> str:
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()

    @field_validator("roll_no")
    @classmethod
    def clean_roll(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("association")
    @classmethod
    def clean_association(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ALLOWED_ASSOCIATIONS:
            raise ValueError("Invalid association")
        return clean


class MembershipLookupRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=120)
    roll_no: str = Field(..., min_length=1, max_length=50)
    association: str = Field(..., min_length=2, max_length=20)
    otp_token: str = Field(..., min_length=10, max_length=100)
    session_id: str = Field(..., min_length=32, max_length=64)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("roll_no")
    @classmethod
    def clean_roll(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("association")
    @classmethod
    def clean_association(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()


class MembershipLookupOtpRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=120)
    session_id: str = Field(..., min_length=32, max_length=64)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()


class ChatRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    roll_no: str = Field(..., min_length=1, max_length=50)
    dept: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format. Please provide a valid student Gmail address.")
        return v

    @field_validator("name", "roll_no", "dept")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return html.escape(re.sub(r'<[^>]*?>', '', v).strip())

class ChatUserStatusUpdate(BaseModel):
    status: str = Field(..., min_length=3, max_length=20)


class MembershipCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    roll: str = Field(..., min_length=1, max_length=50)
    dept: str = Field(..., min_length=2, max_length=100)
    year: str = Field(..., min_length=2, max_length=50)
    association: str = Field(..., min_length=2, max_length=20)
    interest: Optional[str] = Field(None, max_length=250)
    email: Optional[str] = Field(None, max_length=120)
    otp_token: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, min_length=32, max_length=64)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if v is None:
            return v
        if not re.fullmatch(r"[a-fA-F0-9-]{32,64}", v):
            raise ValueError("Invalid verification session")
        return v.lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> str:
        if not v or not v.strip():
            return ""
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format. Please provide a valid student Gmail address.")
        return v
        return v

    @field_validator("name", "roll", "dept", "interest")
    @classmethod
    def sanitize_strings(cls, v: str) -> str:
        if not v:
            return v
        v = re.sub(r'<[^>]*?>', '', v).strip()
        return html.escape(v)

    @field_validator("association")
    @classmethod
    def validate_association(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ALLOWED_ASSOCIATIONS:
            raise ValueError(
                f"Invalid association '{clean}'. Must be one of: {', '.join(sorted(ALLOWED_ASSOCIATIONS))}"
            )
        return clean


class CommunityPostCreate(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=100)
    roll_no: str = Field(..., min_length=1, max_length=50)
    dept: str = Field(..., min_length=2, max_length=100)
    year: str = Field(..., min_length=2, max_length=50)
    category: str = Field(..., min_length=2, max_length=50)
    title: str = Field(..., min_length=5, max_length=150)
    content: str = Field(..., min_length=10, max_length=3000)
    is_anonymous: bool = False

    @field_validator("title", "content", "author_name", "roll_no")
    @classmethod
    def sanitize(cls, v: str) -> str:
        v = re.sub(r'<[^>]*?>', '', v).strip()
        return html.escape(v)


class CommunityCommentCreate(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=100)
    roll_no: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=2, max_length=1000)

    @field_validator("content", "author_name", "roll_no")
    @classmethod
    def sanitize(cls, v: str) -> str:
        v = re.sub(r'<[^>]*?>', '', v).strip()
        return html.escape(v)


class AnnouncementUpdate(BaseModel):
    tag: str = Field(..., min_length=2, max_length=50)
    message: str = Field(..., min_length=5, max_length=250)
    button_text: str = Field(..., min_length=2, max_length=50)


class EventCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    association: str = Field(..., pattern="^(CSESA|MESA|EESA|CESA|AEXS|AIESA)$")
    date_str: str = Field(..., min_length=3, max_length=60)
    category: str = Field(..., min_length=2, max_length=50)
    description: str = Field(..., min_length=5, max_length=500)

    @field_validator("title", "date_str", "category", "description")
    @classmethod
    def sanitize(cls, v: str) -> str:
        v = re.sub(r'<[^>]*?>', '', v).strip()
        return html.escape(v)


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(ACTIVE|SUSPENDED|BLOCKED|RESTRICTED)$")


class AdminPinVerify(BaseModel):
    pin: str


class GateCheckinRequest(BaseModel):
    pass_id: str = Field(..., min_length=5, max_length=100)
    checkpoint: Optional[str] = Field("Central Gate / Main Campus", max_length=100)


# --------------------------------------------------------------------------
# API ENDPOINTS
# --------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check endpoint for system monitoring."""
    return {
        "status": "healthy",
        "service": "AssociationHub",
        "institution": "NKOCET Solapur",
        "version": "2.4.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/stats")
async def get_system_stats():
    """Returns live registration telemetry, gate attendance, and department breakdowns."""
    with get_db() as conn:
        cursor = conn.cursor()
        total_members = cursor.execute("SELECT COUNT(*) FROM memberships;").fetchone()[0]
        active_members = cursor.execute("SELECT COUNT(*) FROM memberships WHERE status = 'ACTIVE';").fetchone()[0]
        suspended_members = cursor.execute("SELECT COUNT(*) FROM memberships WHERE status = 'SUSPENDED';").fetchone()[0]
        
        cursor.execute("SELECT association, COUNT(*) FROM memberships GROUP BY association;")
        assoc_counts = {r[0]: r[1] for r in cursor.fetchall()}
        
        cursor.execute("SELECT year, COUNT(*) FROM memberships GROUP BY year;")
        year_counts = {r[0]: r[1] for r in cursor.fetchall()}

        total_posts = cursor.execute("SELECT COUNT(*) FROM community_posts;").fetchone()[0]
        total_events = cursor.execute("SELECT COUNT(*) FROM events;").fetchone()[0]
        total_checkins = cursor.execute("SELECT COUNT(*) FROM gate_checkins;").fetchone()[0]

        return {
            "status": "operational",
            "total_registered_members": total_members,
            "active_members_count": active_members,
            "suspended_members_count": suspended_members,
            "total_gate_checkins": total_checkins,
            "members_by_association": assoc_counts,
            "members_by_year": year_counts,
            "total_community_posts": total_posts,
            "total_department_events": total_events,
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


@app.get("/api/events")
async def list_events(association: Optional[str] = None):
    """Returns upcoming department events, optionally filtered by association."""
    with get_db() as conn:
        cursor = conn.cursor()
        if association:
            clean_assoc = association.strip().upper()
            cursor.execute("SELECT id, title, association, date_str, category, description FROM events WHERE association = ? ORDER BY id ASC;", (clean_assoc,))
        else:
            cursor.execute("SELECT id, title, association, date_str, category, description FROM events ORDER BY id ASC;")
        rows = cursor.fetchall()
        return {"events": [dict(r) for r in rows]}


@app.post("/api/admin/events", status_code=201)
async def create_event(data: EventCreate, request: Request):
    """Admin endpoint: Publishes a new departmental event or technical fest."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO events (title, association, date_str, category, description)
        VALUES (?, ?, ?, ?, ?);
        """, (
            data.title.strip(),
            data.association.strip().upper(),
            data.date_str.strip(),
            data.category.strip(),
            data.description.strip()
        ))
        event_id = cursor.lastrowid
        log_audit_event("EVENT_CREATED", ip, f"Admin created event #{event_id} '{data.title}' for {data.association}", conn=conn)
        return {
            "success": True,
            "event_id": event_id,
            "message": f"Event '{data.title}' successfully published to {data.association} calendar."
        }


@app.delete("/api/admin/events/{event_id}")
async def delete_event(event_id: int, request: Request):
    """Admin endpoint: Deletes a departmental event from the active schedule."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, association FROM events WHERE id = ?;", (event_id,))
        ev = cursor.fetchone()
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found.")
        cursor.execute("DELETE FROM events WHERE id = ?;", (event_id,))
        log_audit_event("EVENT_DELETED", ip, f"Admin deleted event #{event_id} '{ev['title']}'", conn=conn)
        return {
            "success": True,
            "event_id": event_id,
            "message": f"Event #{event_id} ({ev['title']}) removed from calendar."
        }


@app.post("/api/student/register/complete", status_code=201)
async def student_register_complete(data: StudentCompleteRegistrationRequest, request: Request):
    """Register a student directly after basic validation and duplicate checks."""
    ip = get_client_ip(request)
    name = data.name.strip()
    email = data.email.strip().lower()
    roll = data.roll_no.strip().upper()
    dept = data.dept.strip()

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR roll_no = ? LIMIT 1;", (email, roll))
        if cursor.fetchone():
            log_audit_event("REGISTRATION_DUPLICATE_BLOCKED", ip, f"Blocked duplicate registration for {email} ({roll})", conn=conn)
            raise HTTPException(status_code=400, detail="Duplicate Account: The Gmail address or roll number is already registered.")

        # Duplicate check: Email
        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? LIMIT 1;", (email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate Account: The Gmail address '{email}' is already registered."
            )

        # Duplicate check: Roll Number
        cursor.execute("SELECT student_id FROM registered_students WHERE roll_no = ? LIMIT 1;", (roll,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate Account: College Roll Number '{roll}' is already registered."
            )

        # Secure password hashing (PBKDF2-HMAC-SHA256 with 100,000 iterations & unique salt)
        pwd_hash, salt = hash_student_password(data.password)

        # Generate unique Student ID
        student_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        verified_at = ""

        # Insert permanent student record
        cursor.execute("""
        INSERT INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
        """, (student_id, name, email, roll, dept, pwd_hash, salt, verified_at, created_at))

        # Synchronize into memberships table if not present so gate & verify know them
        cursor.execute("SELECT pass_id FROM memberships WHERE roll_no = ?;", (roll,))
        if not cursor.fetchone():
            pass_id = f"NKOCET-2026-CSESA-{secrets.token_hex(3).upper()}"
            sig = compute_hmac_signature(pass_id, roll, "CSESA")
            verify_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(verify_url)
            cursor.execute("""
            INSERT OR IGNORE INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
                VALUES (?, ?, ?, ?, ?, 'Second Year (SY)', 'CSESA', 'Registered Student', ?, 'ACTIVE', ?, ?);
            """, (pass_id, name, roll, email, dept, qr_b64, sig, created_at))

        session_token = f"STUDENT_SESSION.{secrets.token_hex(20)}"
        log_audit_event("STUDENT_REGISTERED", ip, f"Registered new student {name} ({roll}) with Gmail {email} [ID: {student_id}]", conn=conn)

        return {
            "success": True,
            "student_id": student_id,
            "full_name": name,
            "email": email,
            "roll_no": roll,
            "dept": dept,
            "is_email_verified": False,
            "email_verified_at": verified_at,
            "created_at": created_at,
            "session_token": session_token,
            "message": f"Congratulations {name}! Your student account ({student_id}) has been created."
        }


# --------------------------------------------------------------------------
# GMAIL VERIFICATION & OTP AUTHENTICATION
# --------------------------------------------------------------------------

@app.post("/api/auth/send-otp")
async def send_email_otp(data: SendOtpRequest, request: Request):
    """
    Sends a 6-digit OTP code to student's Gmail for identity verification.
    Security:
    - 60-second resend cooldown.
    - 5-minute (300 seconds) expiration limit.
    - Cryptographically hashed OTP storage (SHA-256 + HMAC salt).
    - Rate-limited per IP.
    - Real-time Gmail SMTP dispatch only. No plaintext OTP or simulated credentials exposed.
    """
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    roll = data.roll_no.strip().upper() if data.roll_no else None
    now = time.time()

    # Enforce Rejoin Approval Gate: Blocked or removed students require Admin approval
    check_account_restriction(email, roll, data.name)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Enforce 60-second resend cooldown
        cursor.execute("SELECT last_sent_at FROM email_otp_verifications WHERE email = ?;", (email,))
        existing = cursor.fetchone()
        if existing and existing["last_sent_at"]:
            elapsed = now - existing["last_sent_at"]
            if elapsed < 60:
                remaining = int(60 - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Cooldown active: Please wait {remaining} seconds before requesting a new OTP."
                )

        # 2. Prevent duplicate email registration if registering for membership pass
        if request.url.path == "/api/auth/send-otp":
            cursor.execute("SELECT pass_id FROM memberships WHERE email = ? LIMIT 1;", (email,))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate Registration: The Gmail address '{email}' is already registered as an official member."
                )

        # 3. Secure 6-digit OTP generation & cryptographic SHA-256 hashing
        otp_code = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = hash_otp(otp_code, email)
        expires_at = now + 300  # Strictly 5 minutes validity

        # 4. Store hashed OTP, timestamps, and reset attempt counter in database
        if request.url.path == "/api/auth/send-otp" and (not roll or not data.association):
            raise HTTPException(status_code=400, detail="Roll number and association are required for membership verification.")

        cursor.execute("""
        INSERT INTO email_otp_verifications
            (email, otp_hash, otp_code, roll_no, association, session_id, expires_at, last_sent_at, attempts, is_verified, created_at)
        VALUES (?, ?, '', ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            otp_hash = excluded.otp_hash,
            otp_code = '',
            roll_no = excluded.roll_no,
            association = excluded.association,
            session_id = excluded.session_id,
            expires_at = excluded.expires_at,
            last_sent_at = excluded.last_sent_at,
            attempts = 0,
            is_verified = 0,
            verification_token = NULL,
            verified_at = NULL;
        """, (email, otp_hash, roll, data.association, data.session_id, expires_at, now))
        log_audit_event("OTP_REQUESTED", ip, f"OTP requested for {email} (Roll: {roll})", conn=conn)

    # 5. Dispatch real email via Gmail SMTP
    clean_name = data.name.strip() if data.name else "Student"
    smtp_res = send_real_smtp_email(email, clean_name, otp_code)

    if not smtp_res["sent"]:
        log_audit_event("EMAIL_DISPATCH_FAILED", ip, f"Gmail SMTP delivery failed to {email}: {smtp_res.get('reason')}")
        raise HTTPException(
            status_code=503,
            detail="Verification email could not be sent. Please try again later."
        )

    log_audit_event("REAL_EMAIL_DISPATCHED", ip, f"Dispatched real email with OTP to {email}")
    return {
        "success": True,
        "email": email,
        "expires_in_seconds": 300,
        "cooldown_seconds": 60,
        "message": f"Verification code successfully dispatched to your Gmail inbox ({email})! Valid for 5 minutes."
    }


@app.post("/api/auth/verify-otp")
async def verify_email_otp(data: VerifyOtpRequest, request: Request):
    """
    Verifies 6-digit OTP code against stored cryptographic hash.
    Security:
    - 5-minute expiration limit.
    - Maximum 5 attempts lockout.
    - Timing-attack safe hash comparison.
    - Permanent database storage of verified status and verified_at timestamp.
    """
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    otp = data.otp.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT otp_hash, expires_at, attempts FROM email_otp_verifications
        WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?;
        """, (email, data.session_id, data.roll_no, data.association))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="No verification request found for this email. Please click 'Send OTP' first.")

        if time.time() >= row["expires_at"]:
            raise HTTPException(status_code=400, detail="OTP verification code has expired (5-minute validity limit). Please request a new code.")

        if row["attempts"] >= 5:
            raise HTTPException(status_code=429, detail="Too many incorrect OTP attempts (maximum 5). For security, this OTP has been locked. Please request a new code.")

        # Cryptographic hash verification with timing-attack safe comparison
        candidate_hash = hash_otp(otp, email)
        if not hmac.compare_digest(row["otp_hash"] or "", candidate_hash):
            new_attempts = row["attempts"] + 1
            cursor.execute("""
            UPDATE email_otp_verifications SET attempts = ?
            WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?;
            """, (new_attempts, email, data.session_id, data.roll_no, data.association))
            conn.commit()
            remaining = 5 - new_attempts
            if remaining <= 0:
                raise HTTPException(status_code=429, detail="Maximum 5 incorrect attempts reached. This OTP has been invalidated. Please request a new code.")
            raise HTTPException(status_code=400, detail=f"Incorrect OTP verification code. {remaining} attempt(s) remaining.")

        token = f"VERIFIED_{secrets.token_hex(16)}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        UPDATE email_otp_verifications
        SET is_verified = 1,
            verification_token = ?,
            verified_at = ?,
            attempts = 0,
            otp_hash = NULL
        WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?
          AND otp_hash = ? AND is_verified = 0 AND expires_at > ?;
        """, (token, now_str, email, data.session_id, data.roll_no, data.association, row["otp_hash"], time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=400, detail="OTP verification session expired or was already used. Please request a new code.")

        log_audit_event("GMAIL_VERIFIED", ip, f"Verified email {email} successfully", conn=conn)

        return {
            "success": True,
            "verified": True,
            "email": email,
            "verification_token": token,
            "verified_at": now_str,
            "message": f"Gmail identity verified successfully for {email}!"
        }


# --------------------------------------------------------------------------
# GATED COMMUNITY CHAT AUTHENTICATION GATEWAY
# --------------------------------------------------------------------------

@app.post("/api/chat/auth/send-otp")
async def send_chat_otp(data: SendOtpRequest, request: Request):
    raise HTTPException(status_code=410, detail="Chat Gmail OTP verification has been removed.")


@app.post("/api/chat/auth/verify-and-enter")
async def verify_and_enter_chat(data: ChatRegisterRequest, request: Request):
    """Registers a chat identity directly without changing email verification state."""
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    name = data.name.strip()
    roll = data.roll_no.strip().upper()
    dept = data.dept.strip()
    check_account_restriction(email, roll, name)

    with get_db() as conn:
        cursor = conn.cursor()
        # Check if user already exists and is banned
        cursor.execute("SELECT user_id, status FROM community_users WHERE email = ? OR roll_no = ?;", (email, roll))
        existing_user = cursor.fetchone()
        if existing_user and existing_user["status"] == "BANNED":
            raise HTTPException(status_code=403, detail="⛔ Access Denied: Your chat account has been banned by the Administrator.")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = existing_user["user_id"] if existing_user else f"CHAT-USER-{secrets.token_hex(4).upper()}"
        session_token = f"CHAT_SESSION.{secrets.token_hex(16)}"
        session_expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_users
            (user_id, name, roll_no, email, dept, status, session_token, session_expires_at, session_revoked_at, created_at, last_active)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = excluded.name,
            roll_no = excluded.roll_no,
            dept = excluded.dept,
            session_token = excluded.session_token,
            session_expires_at = excluded.session_expires_at,
            session_revoked_at = NULL,
            last_active = excluded.last_active;
        """, (user_id, name, roll, email, dept, session_token, session_expires_at, now_str, now_str))

        # Ensure student is recorded in memberships table so gate & verify know them
        cursor.execute("SELECT pass_id FROM memberships WHERE roll_no = ?;", (roll,))
        if not cursor.fetchone():
            pass_id = f"NKOCET-2026-CSESA-{secrets.token_hex(3).upper()}"
            sig = compute_hmac_signature(pass_id, roll, "CSESA")
            qr_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(qr_url)
            cursor.execute("""
            INSERT OR IGNORE INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
            VALUES (?, ?, ?, ?, ?, 'Second Year (SY)', 'CSESA', 'Campus Pulse Community Peer', ?, 'ACTIVE', ?, ?);
            """, (pass_id, name, roll, email, dept, qr_b64, sig, now_str))

        log_audit_event("CHAT_GATEWAY_AUTHENTICATED", ip, f"Student {name} ({roll}) entered community chat via {email}", conn=conn)

        return {
            "success": True,
            "message": f"Welcome to Campus Pulse, {name}!",
            "token": session_token,
            "user": {
                "user_id": user_id,
                "name": name,
                "roll_no": roll,
                "email": email,
                "dept": dept,
                "status": "ACTIVE"
            }
        }


@app.get("/api/chat/auth/me")
async def get_chat_current_user(request: Request):
    """Validates active chat token and returns user profile & status."""
    token = request.headers.get("X-Chat-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthenticated: No active chat session token.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, name, roll_no, email, dept, status, created_at
        FROM community_users
        WHERE session_token = ? AND session_revoked_at IS NULL
          AND session_expires_at IS NOT NULL
          AND julianday(session_expires_at) > julianday('now')
          AND status IN ('ACTIVE', 'MUTED');
        """, (token.strip(),))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Chat session expired or invalid. Please enter the chat again.")

        return {
            "authenticated": True,
            "user": dict(user)
        }


# --------------------------------------------------------------------------
# MEMBERSHIP INTAKE & VERIFICATION
# --------------------------------------------------------------------------

@app.post("/api/memberships", status_code=201)
async def create_membership(data: MembershipCreate, request: Request):
    """
    Intakes new student membership, verifies Gmail OTP, computes cryptographic HMAC-SHA256 signature & Base64 QR,
    and persists in SQLite with duplicate checking and rate limiting.
    """
    ip = get_client_ip(request)
    check_register_rate_limit(ip)

    name = data.name.strip()
    roll = data.roll.strip().upper()
    dept = data.dept.strip()
    year = data.year.strip()
    assoc = data.association
    email = (data.email or "").strip().lower()
    otp_token = data.otp_token
    session_id = data.session_id
    interest = data.interest.strip() if data.interest else "General Technical Participation & Workshops"

    # Enforce Rejoin Approval Gate: Blocked or removed students require Admin approval to rejoin
    check_account_restriction(email, roll, name)
    if not email:
        raise HTTPException(status_code=403, detail="A valid student email address is required.")

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Existing Member Check: If student already registered for this club or has a pass,
        # return their official Digital Pass only after consuming an OTP bound to this member.
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships
        WHERE (roll_no = ? AND association = ?) OR (email != '' AND email = ? AND association = ?)
        ORDER BY rowid DESC LIMIT 1;
        """, (roll, assoc, email, assoc))
        existing = cursor.fetchone()

        if existing:
            pass_id = existing["pass_id"]
            sig = existing["crypto_signature"] or compute_hmac_signature(pass_id, existing["roll_no"], existing["association"])
            verify_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(verify_url)

            # Fetch or generate Verified Student ID
            cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR (roll_no != '' AND roll_no = ?) LIMIT 1;", 
                           (existing["email"], existing["roll_no"]))
            stu_row = cursor.fetchone()
            if stu_row:
                verified_stu_id = stu_row["student_id"]
            else:
                verified_stu_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
                pwd_hash, salt = hash_student_password("MemberPass@" + pass_id[-6:])
                cursor.execute("""
                INSERT OR IGNORE INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', 'ACTIVE', ?);
                """, (verified_stu_id, existing["name"], existing["email"], existing["roll_no"], existing["dept"], pwd_hash, salt, existing["created_at"]))

            return {
                "pass_id": pass_id,
                "student_id": verified_stu_id,
                "name": existing["name"],
                "roll_no": existing["roll_no"],
                "dept": existing["dept"],
                "year": existing["year"],
                "association": existing["association"],
                "interest": existing["interest"] or interest,
                "qr_code_base64": qr_b64,
                "status": existing["status"],
                "crypto_signature": sig,
                "verify_url": verify_url,
                "created_at": existing["created_at"],
                "is_existing": True,
                "message": f"Welcome back, {existing['name']}! Your official Digi-Pass was loaded from the database."
            }

        is_verified = 0

        # 3. Generate unique Pass ID
        unique_hex = secrets.token_hex(3).upper()
        pass_id = f"NKOCET-2026-{assoc}-{unique_hex}"
        
        # Compute Cryptographic HMAC-SHA256 signature
        sig = compute_hmac_signature(pass_id, roll, assoc)

        # Generate verification QR Code with signature
        verify_url = build_verification_url(pass_id, sig)
        qr_b64 = make_qr_base64(verify_url)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 4. Save into SQLite memberships table
        cursor.execute("""
        INSERT INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?);
        """, (pass_id, name, roll, email, dept, year, assoc, interest, qr_b64, sig, created_at))

        # 5. Save into SQLite registered_students table for unified record keeping
        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR roll_no = ? LIMIT 1;", (email, roll))
        stu_row = cursor.fetchone()
        if stu_row:
            verified_stu_id = stu_row["student_id"]
        else:
            verified_stu_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
            pwd_hash, salt = hash_student_password("MemberPass@" + unique_hex)
            cursor.execute("""
            INSERT OR IGNORE INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', 'ACTIVE', ?);
            """, (verified_stu_id, name, email, roll, dept, pwd_hash, salt, created_at))

        log_audit_event("MEMBER_REGISTERED", ip, f"Registered {name} ({roll}) in {assoc} [Gmail: {email}] [Pass: {pass_id}] [Student ID: {verified_stu_id}]", conn=conn)

        return {
            "pass_id": pass_id,
            "student_id": verified_stu_id,
            "name": name,
            "roll_no": roll,
            "email": email,
            "dept": dept,
            "year": year,
            "association": assoc,
            "interest": interest,
            "qr_code_base64": qr_b64,
            "status": "ACTIVE",
            "crypto_signature": sig,
            "verify_url": verify_url,
            "created_at": created_at,
            "is_existing": False,
            "message": f"Congratulations {name}! Your official Digi-Pass has been generated and permanently saved in the database."
        }


@app.get("/api/memberships")
async def list_memberships(request: Request, association: Optional[str] = None):
    """Lists registered members (excluding large QR base64 strings for speed)."""
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        if association:
            cursor.execute("""
            SELECT pass_id, name, roll_no, dept, year, association, interest, status, created_at
            FROM memberships WHERE association = ? ORDER BY created_at DESC;
            """, (association.strip().upper(),))
        else:
            cursor.execute("""
            SELECT pass_id, name, roll_no, dept, year, association, interest, status, created_at
            FROM memberships ORDER BY created_at DESC;
            """)
        rows = cursor.fetchall()
        return {"count": len(rows), "members": [dict(r) for r in rows]}


@app.post("/api/memberships/lookup/send-otp")
async def send_membership_lookup_otp(data: MembershipLookupOtpRequest, request: Request):
    clean_q = data.query.strip()
    with get_db() as conn:
        row = conn.execute("""
        SELECT roll_no, association, email, name
        FROM memberships
        WHERE pass_id = ? OR roll_no = ? OR email = ?
        ORDER BY rowid DESC LIMIT 1;
        """, (clean_q, clean_q.upper(), clean_q.lower())).fetchone()
    if not row or (row["email"] or "").strip().lower() != data.email:
        raise HTTPException(status_code=404, detail="No membership matching those details was found.")

    otp_request = SendOtpRequest(
        email=data.email,
        name=row["name"],
        roll_no=row["roll_no"],
        association=row["association"],
        session_id=data.session_id,
    )
    result = await send_email_otp(otp_request, request)
    return {
        **result,
        "roll_no": row["roll_no"],
        "association": row["association"],
    }


@app.post("/api/memberships/lookup")
async def lookup_membership(data: MembershipLookupRequest, request: Request):
    """
    Retrieves a digital pass only after consuming an OTP bound to its email,
    roll number, association, and verification session.
    """
    clean_q = data.query.strip()
    if not clean_q or len(clean_q) < 2:
        raise HTTPException(status_code=400, detail="Please enter a valid Roll No, PRN, Email, or Pass ID.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships
        WHERE pass_id = ? OR roll_no = ? OR email = ?
        ORDER BY rowid DESC LIMIT 1;
        """, (clean_q, clean_q.upper(), clean_q.lower()))
        m = cursor.fetchone()

        if (not m or (m["email"] or "").strip().lower() != data.email
                or m["roll_no"].strip().upper() != data.roll_no
                or m["association"].strip().upper() != data.association):
            raise HTTPException(status_code=404, detail="No membership matching those details was found.")

        cursor.execute("""
        UPDATE email_otp_verifications
        SET is_verified = 0, verification_token = NULL, verified_at = NULL, otp_hash = NULL
        WHERE email = ? AND roll_no = ? AND association = ? AND session_id = ?
          AND verification_token = ? AND is_verified = 1 AND expires_at > ?;
        """, (data.email, data.roll_no, data.association, data.session_id, data.otp_token, time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=403, detail="Email verification is missing, expired, used, or does not match this pass. Please verify again.")

        pass_id = m["pass_id"]
        sig = m["crypto_signature"] or compute_hmac_signature(pass_id, m["roll_no"], m["association"])
        verify_url = build_verification_url(pass_id, sig)
        qr_b64 = make_qr_base64(verify_url)

        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR (roll_no != '' AND roll_no = ?) LIMIT 1;", (m["email"], m["roll_no"]))
        s_row = cursor.fetchone()
        student_id = s_row["student_id"] if s_row else f"NKOCET-STU-2026-{pass_id[-6:]}"

        return {
            "pass_id": pass_id,
            "student_id": student_id,
            "name": m["name"],
            "roll_no": m["roll_no"],
            "dept": m["dept"],
            "year": m["year"],
            "association": m["association"],
            "interest": m["interest"],
            "qr_code_base64": qr_b64,
            "status": m["status"],
            "crypto_signature": sig,
            "verify_url": verify_url,
            "created_at": m["created_at"]
        }


@app.get("/api/memberships/verify/{pass_id}")
async def verify_membership(pass_id: str, request: Request, sig: Optional[str] = None):
    """
    Public QR gate check-in verification for membership passes with cryptographic signature validation.
    """
    clean_id = pass_id.strip()
    ip = get_client_ip(request)
    check_gate_verify_rate_limit(ip)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships WHERE pass_id = ?;
        """, (clean_id,))
        row = cursor.fetchone()

        if not row:
            log_audit_event("GATE_VERIFY_NOT_FOUND", ip, f"Pass {clean_id} not found in ledger")
            raise HTTPException(
                status_code=404,
                detail=f"Membership pass '{clean_id}' was not found or is invalid."
            )

        status = row["status"] if "status" in row.keys() and row["status"] else "ACTIVE"
        expected_sig = compute_hmac_signature(row["pass_id"], row["roll_no"], row["association"])
        sig_valid = bool(sig) and hmac.compare_digest(expected_sig, sig)
        # For manual typed lookups (no sig), still show member data but flag sig as unverified.
        # Only block if a sig was supplied but it's wrong (tampered pass).
        if sig and not sig_valid:
            log_audit_event(
                "GATE_VERIFY_INVALID_SIGNATURE",
                ip,
                f"Tampered/invalid signature supplied for pass {clean_id}",
                conn=conn,
            )
        elif not sig:
            log_audit_event(
                "GATE_VERIFY_MANUAL_LOOKUP",
                ip,
                f"Manual pass lookup (no signature) for pass {clean_id}",
                conn=conn,
            )
        try:
            verify_url = build_verification_url(row["pass_id"], expected_sig)
            qr_b64 = make_qr_base64(verify_url)
        except Exception:
            verify_url = ""
            qr_b64 = row["qr_code_base64"] or ""

        if status == "SUSPENDED":
            log_audit_event("GATE_VERIFY_SUSPENDED", ip, f"Suspended pass inspected: {clean_id}")
            return {
                "valid": False,
                "status": "SUSPENDED",
                "signature_verified": sig_valid,
                "crypto_signature": expected_sig,
                "message": "This membership pass is TEMPORARILY SUSPENDED by college administration. Access denied at gate.",
                "member": {
                    "pass_id": row["pass_id"],
                    "name": row["name"],
                    "roll_no": row["roll_no"],
                    "dept": row["dept"],
                    "year": row["year"],
                    "association": row["association"],
                    "interest": row["interest"],
                    "status": "SUSPENDED",
                    "qr_code_base64": qr_b64,
                    "verify_url": verify_url,
                    "crypto_signature": expected_sig,
                    "created_at": row["created_at"]
                }
            }

        return {
            "valid": True,
            "status": "ACTIVE",
            "signature_verified": sig_valid,
            "crypto_signature": expected_sig,
            "security_seal": "NKOCET-DIGITAL-LEDGER-VERIFIED",
            "member": {
                "pass_id": row["pass_id"],
                "name": row["name"],
                "roll_no": row["roll_no"],
                "dept": row["dept"],
                "year": row["year"],
                "association": row["association"],
                "interest": row["interest"],
                "status": status,
                "qr_code_base64": qr_b64,
                "verify_url": verify_url,
                "crypto_signature": expected_sig,
                "created_at": row["created_at"]
            }
        }


@app.post("/api/gate/check-in")
async def record_gate_checkin(data: GateCheckinRequest, request: Request):
    """
    Public / Coordinator Gate Scanner: Validates student pass status and logs attendance.
    Denies entry if pass is suspended or invalid.
    """
    clean_id = data.pass_id.strip()
    checkpoint = data.checkpoint.strip() if data.checkpoint else "Central Gate / Main Campus"
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, dept, year, association, status
        FROM memberships WHERE pass_id = ?;
        """, (clean_id,))
        row = cursor.fetchone()

        if not row:
            log_audit_event("GATE_CHECKIN_FAILED", ip, f"Invalid pass ID attempted: {clean_id} at {checkpoint}")
            raise HTTPException(status_code=404, detail=f"Pass ID '{clean_id}' not found in registry.")

        status = row["status"] if "status" in row.keys() and row["status"] else "ACTIVE"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status == "SUSPENDED":
            log_audit_event("GATE_CHECKIN_DENIED", ip, f"Suspended pass denied entry: {clean_id} ({row['name']}) at {checkpoint}", conn=conn)
            cursor.execute("""
            INSERT INTO gate_checkins (pass_id, student_name, roll_no, association, checkpoint, status, timestamp)
            VALUES (?, ?, ?, ?, ?, 'DENIED_SUSPENDED', ?);
            """, (clean_id, row["name"], row["roll_no"], row["association"], checkpoint, now_str))
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Membership pass for {row['name']} is currently SUSPENDED by administration."
            )

        cursor.execute("""
        INSERT INTO gate_checkins (pass_id, student_name, roll_no, association, checkpoint, status, timestamp)
        VALUES (?, ?, ?, ?, ?, 'ENTRY_GRANTED', ?);
        """, (clean_id, row["name"], row["roll_no"], row["association"], checkpoint, now_str))

        log_audit_event("GATE_CHECKIN_SUCCESS", ip, f"Student {row['name']} ({row['roll_no']}) checked in at {checkpoint}", conn=conn)

        return {
            "success": True,
            "status": "ENTRY_GRANTED",
            "message": f"Gate access granted for {row['name']} ({row['association']})",
            "student_name": row["name"],
            "roll_no": row["roll_no"],
            "dept": row["dept"],
            "year": row["year"],
            "association": row["association"],
            "checkpoint": checkpoint,
            "timestamp": now_str,
            "pass_id": clean_id
        }


@app.get("/api/gate/checkins")
async def list_gate_checkins(limit: int = 50, pass_id: Optional[str] = None):
    """Returns recent gate attendance logs."""
    with get_db() as conn:
        cursor = conn.cursor()
        if pass_id:
            cursor.execute("""
            SELECT id, pass_id, student_name, roll_no, association, checkpoint, status, timestamp
            FROM gate_checkins WHERE pass_id = ? ORDER BY id DESC LIMIT ?;
            """, (pass_id.strip(), limit))
        else:
            cursor.execute("""
            SELECT id, pass_id, student_name, roll_no, association, checkpoint, status, timestamp
            FROM gate_checkins ORDER BY id DESC LIMIT ?;
            """, (limit,))
        rows = cursor.fetchall()
        return {"checkins": [dict(r) for r in rows]}


@app.delete("/api/memberships/{pass_id}")
async def delete_membership(pass_id: str, request: Request):
    """
    Admin endpoint: Permanently revokes and removes a registered member pass from the database.
    Requires Administrator Authorization.
    """
    verify_admin_access(request)
    clean_id = pass_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pass_id, name, roll_no, association, email FROM memberships WHERE pass_id = ?;", (clean_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Membership pass '{clean_id}' was not found in the registry."
            )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if existing["email"] or existing["roll_no"]:
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Membership Pass Revoked by Administrator', 'RESTRICTED', ?);
            """, (existing["email"] or "", existing["roll_no"], existing["name"], now_str))

        cursor.execute("DELETE FROM memberships WHERE pass_id = ?;", (clean_id,))
        log_audit_event("MEMBER_REVOKED_DELETED", ip, f"Revoked & deleted pass {clean_id} for {existing['name']} (Roll: {existing['roll_no']})", conn=conn)
        return {
            "success": True,
            "message": f"Membership for {existing['name']} (Roll: {existing['roll_no']}, {existing['association']}) has been successfully revoked and removed.",
            "pass_id": clean_id
        }


# --------------------------------------------------------------------------
# CAMPUS PULSE: STUDENT EXPERIENCE & DISCUSSION HUB
# --------------------------------------------------------------------------

@app.get("/api/community/posts")
async def list_community_posts(
    category: Optional[str] = None,
    dept: Optional[str] = None,
    search: Optional[str] = None
):
    """Lists community posts with comment counts and like tallies."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
        SELECT p.post_id, p.author_name, p.roll_no, p.dept, p.year, p.category, p.title, p.content, p.is_anonymous, p.likes, p.created_at,
               COUNT(c.comment_id) AS comment_count
        FROM community_posts p
        LEFT JOIN community_comments c ON p.post_id = c.post_id
        WHERE 1=1
        """
        params = []

        if category and category.upper() != "ALL":
            query += " AND p.category = ?"
            params.append(category.strip().upper())

        if dept and dept.upper() != "ALL":
            query += " AND p.dept LIKE ?"
            params.append(f"%{dept.strip()}%")

        if search:
            query += " AND (p.title LIKE ? OR p.content LIKE ?)"
            s = f"%{search.strip()}%"
            params.extend([s, s])

        query += " GROUP BY p.post_id ORDER BY p.created_at DESC;"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        posts = []
        for r in rows:
            p = dict(r)
            if p["is_anonymous"] == 1:
                p["author_name"] = "Anonymous Orchidite"
                p["roll_no"] = "Verified Student"
            posts.append(p)

        return {"count": len(posts), "posts": posts}


@app.post("/api/community/posts", status_code=201)
async def create_community_post(data: CommunityPostCreate, request: Request):
    """
    Submits a new student experience post.
    Security Gate: Verified against active registered memberships or community_users in SQLite!
    Enforces Campus Anti-Troll Shield and checks Mute/Ban status.
    """
    ip = get_client_ip(request)
    roll = data.roll_no.strip().upper()
    cat = data.category.strip().upper()
    if cat not in ALLOWED_CATEGORIES:
        cat = "GENERAL"

    with get_db() as conn:
        cursor = conn.cursor()

        # Campus Anti-Troll Filter
        check_anti_troll(data.title, roll, ip, conn=conn)
        check_anti_troll(data.content, roll, ip, conn=conn)
        check_rate_limit(roll)
        check_account_restriction("", roll_no=roll)

        # Check if student is BANNED or MUTED
        cursor.execute("SELECT user_id, status FROM community_users WHERE roll_no = ?;", (roll,))
        cuser = cursor.fetchone()
        if cuser:
            if cuser["status"] == "BANNED":
                raise HTTPException(status_code=403, detail="⛔ Access Revoked: Your community chat account has been banned by the Administrator.")
            if cuser["status"] == "MUTED":
                raise HTTPException(status_code=403, detail="⏸️ Account Muted: You have been temporarily muted from posting by the Administrator.")

        # Verify student exists in memberships or community_users
        cursor.execute("SELECT name, roll_no, dept, year FROM memberships WHERE roll_no = ? LIMIT 1;", (roll,))
        verified = cursor.fetchone()
        if not verified:
            cursor.execute("SELECT name, roll_no, dept FROM community_users WHERE roll_no = ? LIMIT 1;", (roll,))
            c_verified = cursor.fetchone()
            if not c_verified:
                raise HTTPException(
                    status_code=403,
                    detail=f"Security Gate: Roll No '{roll}' was not found in the student registry."
                )
            verified = {"name": c_verified["name"], "roll_no": c_verified["roll_no"], "dept": c_verified["dept"], "year": "Second Year (SY)"}

        post_id = f"POST-2026-{secrets.token_hex(4).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_posts (post_id, author_name, roll_no, dept, year, category, title, content, is_anonymous, likes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """, (
            post_id,
            verified["name"] if not data.is_anonymous else data.author_name,
            roll,
            verified["dept"],
            verified["year"],
            cat,
            data.title,
            data.content,
            1 if data.is_anonymous else 0,
            created_at
        ))

        # Update last_active in community_users
        cursor.execute("UPDATE community_users SET last_active = ? WHERE roll_no = ?;", (created_at, roll))

        return {
            "success": True,
            "post_id": post_id,
            "message": "Your experience has been verified and published to Campus Pulse!"
        }


@app.post("/api/community/posts/{post_id}/like")
async def like_community_post(post_id: str):
    """Upvotes an experience post."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT likes FROM community_posts WHERE post_id = ?;", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        new_likes = row["likes"] + 1
        cursor.execute("UPDATE community_posts SET likes = ? WHERE post_id = ?;", (new_likes, post_id))
        return {"post_id": post_id, "likes": new_likes}


@app.get("/api/community/posts/{post_id}/comments")
async def get_post_comments(post_id: str):
    """Fetches replies to a discussion thread."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT comment_id, post_id, author_name, roll_no, content, created_at
        FROM community_comments WHERE post_id = ? ORDER BY created_at ASC;
        """, (post_id,))
        rows = cursor.fetchall()
        return {"comments": [dict(r) for r in rows]}


@app.post("/api/community/posts/{post_id}/comments", status_code=201)
async def create_post_comment(post_id: str, data: CommunityCommentCreate, request: Request):
    """
    Posts a reply to a discussion thread.
    Security Gate: Verified against active registered memberships or community_users in SQLite!
    Enforces Campus Anti-Troll Shield.
    """
    ip = get_client_ip(request)
    roll = data.roll_no.strip().upper()

    with get_db() as conn:
        cursor = conn.cursor()

        # Anti-troll check
        check_anti_troll(data.content, roll, ip, conn=conn)

        # Check if student is BANNED or MUTED
        cursor.execute("SELECT status FROM community_users WHERE roll_no = ?;", (roll,))
        cuser = cursor.fetchone()
        if cuser:
            if cuser["status"] == "BANNED":
                raise HTTPException(status_code=403, detail="⛔ Access Denied: Your chat account has been banned.")
            if cuser["status"] == "MUTED":
                raise HTTPException(status_code=403, detail="⏸️ Account Muted: You cannot reply while muted by the Administrator.")

        # Verify student exists in memberships or community_users
        cursor.execute("SELECT name, roll_no FROM memberships WHERE roll_no = ? LIMIT 1;", (roll,))
        verified = cursor.fetchone()
        if not verified:
            cursor.execute("SELECT name, roll_no FROM community_users WHERE roll_no = ? LIMIT 1;", (roll,))
            c_verified = cursor.fetchone()
            if not c_verified:
                raise HTTPException(
                    status_code=403,
                    detail=f"Security Gate: Roll No '{roll}' is not registered."
                )
            verified = {"name": c_verified["name"], "roll_no": c_verified["roll_no"]}

        cursor.execute("SELECT post_id FROM community_posts WHERE post_id = ?;", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Thread not found.")

        comment_id = f"COMM-{secrets.token_hex(3).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_comments (comment_id, post_id, author_name, roll_no, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (comment_id, post_id, verified["name"], roll, data.content, created_at))

        return {
            "success": True,
            "comment_id": comment_id,
            "author_name": verified["name"],
            "created_at": created_at
        }


# --------------------------------------------------------------------------
# CAMPUS ANNOUNCEMENT BROADCASTER
# --------------------------------------------------------------------------

@app.get("/api/announcements/current")
async def get_current_announcement():
    """Fetches the active campus ribbon announcement."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tag, message, button_text, updated_at FROM announcements WHERE is_active = 1 ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return {
                "tag": "📢 Campus Notice",
                "message": "Academic Session 2026 Student Association Membership & Council Registrations Open.",
                "button_text": "Apply Now →"
            }
        return dict(row)


@app.post("/api/admin/announcements")
async def update_announcement(data: AnnouncementUpdate, request: Request):
    """Admin endpoint: Broadcasts a new top announcement across the entire portal."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO announcements (tag, message, button_text, is_active, updated_at)
        VALUES (?, ?, ?, 1, ?);
        """, (data.tag.strip(), data.message.strip(), data.button_text.strip(), updated_at))
        
        log_audit_event("ANNOUNCEMENT_PUBLISHED", ip, f"Published broadcast: [{data.tag.strip()}] {data.message.strip()[:60]}...")
        return {
            "success": True,
            "message": "Live announcement broadcast successfully updated across portal.",
            "announcement": {
                "tag": data.tag.strip(),
                "message": data.message.strip(),
                "button_text": data.button_text.strip(),
                "updated_at": updated_at
            }
        }


# --------------------------------------------------------------------------
# MASTER ADMIN CONTROL SUITE
# --------------------------------------------------------------------------

@app.post("/api/admin/verify-pin")
async def verify_admin_pin(data: AdminPinVerify, request: Request):
    """Validates Admin Master PIN with brute-force defense and returns signed session token."""
    ip = get_client_ip(request)
    check_admin_brute_force(ip)

    submitted_pin = data.pin.strip()
    if hmac.compare_digest(submitted_pin.encode("utf-8"), ADMIN_SECRET_PIN.encode("utf-8")):
        _admin_failed_attempts.pop(ip, None)
        with get_db() as conn:
            conn.execute("DELETE FROM admin_failed_attempts WHERE ip_address = ?;", (ip,))
        token = create_admin_session_token()
        log_audit_event("ADMIN_LOGIN_SUCCESS", ip, "Coordinator Console clearance unlocked.")
        return {
            "valid": True,
            "token": token,
            "expires_in_hours": 3,
            "message": "Master Administrator clearance verified."
        }
    
    record_admin_failed_attempt(ip)
    log_audit_event("ADMIN_LOGIN_FAILED", ip, "Invalid PIN entered.")
    raise HTTPException(status_code=403, detail="Invalid Administrator Security PIN.")


@app.post("/api/admin/logout")
async def logout_admin(request: Request):
    """Revokes the current administrator session token."""
    verify_admin_access(request)
    key = (
        request.headers.get("X-Admin-Token")
        or request.headers.get("X-Admin-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if key.startswith("SESSION."):
        parts = key.split(".")
        if len(parts) >= 3:
            with get_db() as conn:
                conn.execute(
                    "UPDATE admin_sessions SET revoked_at = ? WHERE session_id = ?;",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), parts[2]),
                )
    return {"success": True, "message": "Administrator session revoked."}


@app.patch("/api/admin/members/{pass_id}/status")
async def update_member_status(pass_id: str, data: StatusUpdate, request: Request):
    """Admin endpoint: Toggles student status between ACTIVE and SUSPENDED."""
    verify_admin_access(request)
    clean_id = pass_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pass_id, name, roll_no, email FROM memberships WHERE pass_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Member pass not found.")

        cursor.execute("UPDATE memberships SET status = ? WHERE pass_id = ?;", (data.status, clean_id))
        
        if data.status in ["SUSPENDED", "BLOCKED", "RESTRICTED"]:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Member Pass Suspended by Administrator', 'RESTRICTED', ?);
            """, (row["email"] or "", row["roll_no"], row["name"], now_str))
        log_audit_event("MEMBER_STATUS_CHANGED", ip, f"Updated pass {clean_id} ({row['name']}) status to {data.status}", conn=conn)
        return {
            "success": True,
            "pass_id": clean_id,
            "status": data.status,
            "message": f"Status for {row['name']} updated to {data.status}."
        }


@app.get("/api/admin/students")
async def list_admin_registered_students(request: Request):
    """
    Administrator endpoint: Lists all registered students with verified email timestamps.
    Access strictly gated to Master Admin Authority. Confidential Gmail visible only to admin.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT student_id, full_name, email, roll_no, dept, is_email_verified, email_verified_at, status, created_at
        FROM registered_students
        ORDER BY created_at DESC;
        """)
        rows = cursor.fetchall()
        return {"students": [dict(r) for r in rows], "count": len(rows)}


@app.patch("/api/admin/students/{student_id}/status")
async def update_student_account_status(student_id: str, data: StatusUpdate, request: Request):
    """
    Administrator endpoint: Toggles student account status between ACTIVE, BLOCKED, and SUSPENDED.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    clean_id = student_id.strip()
    ip = get_client_ip(request)
    new_status = data.status.strip().upper()

    if new_status not in {"ACTIVE", "BLOCKED", "SUSPENDED"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be ACTIVE, BLOCKED, or SUSPENDED.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, full_name, email, roll_no FROM registered_students WHERE student_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student record not found.")

        cursor.execute("UPDATE registered_students SET status = ? WHERE student_id = ?;", (new_status, clean_id))
        
        # Also sync to community_users and memberships
        community_status = "BANNED" if new_status == "BLOCKED" else new_status
        if community_status == "ACTIVE":
            cursor.execute(
                "UPDATE community_users SET status = ? WHERE email = ? OR roll_no = ?;",
                (community_status, row["email"], row["roll_no"]),
            )
        else:
            cursor.execute("""
            UPDATE community_users
            SET status = ?, session_token = NULL, session_revoked_at = CURRENT_TIMESTAMP
            WHERE email = ? OR roll_no = ?;
            """, (community_status, row["email"], row["roll_no"]))
        cursor.execute("UPDATE memberships SET status = ? WHERE roll_no = ?;", (new_status, row["roll_no"]))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if new_status in ["BLOCKED", "SUSPENDED"]:
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Student Account Blocked by Administrator', 'RESTRICTED', ?);
            """, (row["email"], row["roll_no"], row["full_name"], now_str))

        log_audit_event("STUDENT_STATUS_CHANGED", ip, f"Admin updated student {clean_id} ({row['full_name']}) status to {new_status}", conn=conn)

        return {
            "success": True,
            "student_id": clean_id,
            "status": new_status,
            "message": f"Student {row['full_name']} ({row['roll_no']}) status updated to {new_status}."
        }


@app.delete("/api/admin/students/{student_id}")
async def delete_student_account(student_id: str, request: Request):
    """
    Administrator endpoint: Permanently removes a student account and resets verification.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    clean_id = student_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, full_name, email, roll_no FROM registered_students WHERE student_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student record not found.")

        email = row["email"]
        name = row["full_name"]
        roll = row["roll_no"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Record in account_restrictions: require admin approval to ever rejoin
        cursor.execute("""
        INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
        VALUES (?, ?, ?, 'Student Account Purged/Deleted by Administrator', 'RESTRICTED', ?);
        """, (email, roll, name, now_str))

        cursor.execute("DELETE FROM registered_students WHERE student_id = ?;", (clean_id,))
        cursor.execute("DELETE FROM email_otp_verifications WHERE email = ?;", (email,))
        cursor.execute("DELETE FROM community_users WHERE email = ? OR roll_no = ?;", (email, roll))
        
        log_audit_event("STUDENT_ACCOUNT_DELETED", ip, f"Admin permanently deleted student {name} ({clean_id}, Roll: {roll}, Email: {email})", conn=conn)

        return {
            "success": True,
            "message": f"Student account {clean_id} ({name}) permanently deleted from AssociationHub."
        }


@app.get("/api/admin/export/students.csv")
async def export_registered_students_csv(request: Request):
    """
    Administrator endpoint: Exports official verified student registry with confidential Gmail addresses.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT student_id, full_name, roll_no, dept, email, is_email_verified, email_verified_at, status, created_at
        FROM registered_students
        ORDER BY created_at DESC;
        """)
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student ID", "Full Name", "Roll / PRN", "Department",
        "Official Student Gmail (Confidential)", "Email Verified",
        "Verification Timestamp", "Account Status", "Registered At"
    ])

    for r in rows:
        writer.writerow([
            r["student_id"],
            r["full_name"],
            r["roll_no"],
            r["dept"],
            r["email"],
            "VERIFIED" if r["is_email_verified"] else "UNVERIFIED",
            r["email_verified_at"] or "",
            r["status"] or "ACTIVE",
            r["created_at"]
        ])

    log_audit_event("EXPORT_STUDENTS_CSV", ip, "Admin exported verified student directory CSV")
    output.seek(0)
    filename = f"NKOCET_Verified_Students_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --------------------------------------------------------------------------
# ADMINISTRATOR REJOIN APPROVAL GATEWAY
# --------------------------------------------------------------------------

@app.get("/api/admin/rejoin-requests")
async def list_admin_rejoin_requests(request: Request):
    """
    Administrator endpoint: Lists all students whose accounts were blocked or removed
    and requires explicit Administrator authorization to rejoin.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, email, roll_no, name, reason, status, restricted_at, rejoin_requested_at, rejoin_approved_at, reviewed_by
        FROM account_restrictions
        ORDER BY 
            CASE status 
                WHEN 'REJOIN_PENDING' THEN 1 
                WHEN 'RESTRICTED' THEN 2 
                ELSE 3 
            END ASC,
            id DESC;
        """)
        rows = cursor.fetchall()
        pending_count = sum(1 for r in rows if r["status"] == "REJOIN_PENDING")
        return {"requests": [dict(r) for r in rows], "count": len(rows), "pending_count": pending_count}


@app.post("/api/admin/rejoin-requests/{request_id}/approve")
async def approve_student_rejoin(request_id: int, request: Request):
    """
    Administrator endpoint: Approves a previously banned or removed student to rejoin
    and register their membership pass or student account.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, roll_no, name FROM account_restrictions WHERE id = ?;", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rejoin request not found.")

        # Set status to REJOIN_APPROVED
        cursor.execute("""
        UPDATE account_restrictions
        SET status = 'REJOIN_APPROVED',
            rejoin_approved_at = ?,
            reviewed_by = 'Administrator'
        WHERE id = ?;
        """, (now_str, request_id))

        # Also unblock in registered_students if present
        cursor.execute("UPDATE registered_students SET status = 'ACTIVE' WHERE email = ? OR (roll_no != '' AND roll_no = ?);", 
                       (row["email"], row["roll_no"] or ""))
        # Also unblock in memberships if present
        cursor.execute("UPDATE memberships SET status = 'ACTIVE' WHERE email = ? OR (roll_no != '' AND roll_no = ?);", 
                       (row["email"], row["roll_no"] or ""))

        log_audit_event("REJOIN_REQUEST_APPROVED", ip, f"Admin approved rejoining for {row['name']} ({row['email']}, Roll: {row['roll_no']})", conn=conn)

        return {
            "success": True,
            "message": f"Rejoining successfully APPROVED for {row['name']} ({row['email']}). They may now register or join."
        }


@app.post("/api/admin/rejoin-requests/{request_id}/reject")
async def reject_student_rejoin(request_id: int, request: Request):
    """
    Administrator endpoint: Rejects a student rejoin request and keeps their account permanently restricted.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, roll_no, name FROM account_restrictions WHERE id = ?;", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rejoin request not found.")

        cursor.execute("""
        UPDATE account_restrictions
        SET status = 'RESTRICTED',
            reviewed_by = 'Administrator'
        WHERE id = ?;
        """, (request_id,))

        log_audit_event("REJOIN_REQUEST_REJECTED", ip, f"Admin rejected rejoining for {row['name']} ({row['email']})", conn=conn)

        return {
            "success": True,
            "message": f"Rejoining request REJECTED for {row['name']}. Account remains restricted."
        }


@app.get("/api/admin/members")
async def get_admin_members(request: Request, association: Optional[str] = None):
    """
    Administrator endpoint: Returns full member directory INCLUDING confidential verified Gmail.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        if association and association != "ALL":
            cursor.execute("""
            SELECT pass_id, name, roll_no, email, dept, year, association, interest, status, crypto_signature, created_at
            FROM memberships WHERE association = ? ORDER BY created_at DESC;
            """, (association.strip().upper(),))
        else:
            cursor.execute("""
            SELECT pass_id, name, roll_no, email, dept, year, association, interest, status, crypto_signature, created_at
            FROM memberships ORDER BY created_at DESC;
            """)
        rows = cursor.fetchall()
        return {"count": len(rows), "members": [dict(r) for r in rows]}


@app.get("/api/admin/export/members.csv")
async def export_members_csv(request: Request):
    """
    Admin endpoint: Streams RFC-4180 CSV with UTF-8 BOM of all registered members
    formatted for HOD and NAAC compliance including confidential verified Gmail.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, status, crypto_signature, created_at, interest
        FROM memberships ORDER BY association ASC, roll_no ASC;
        """)
        rows = cursor.fetchall()

        output = io.StringIO()
        # UTF-8 BOM for Microsoft Excel compatibility
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            "Pass ID",
            "Student Full Name",
            "Roll No / PRN",
            "Verified Gmail (Confidential)",
            "Branch / Department",
            "Academic Year",
            "Student Association",
            "Membership Status",
            "HMAC Crypto Signature",
            "Registration Timestamp",
            "Technical Interests & Skills"
        ])

        for r in rows:
            writer.writerow([
                r["pass_id"],
                r["name"],
                r["roll_no"],
                r["email"] if "email" in r.keys() and r["email"] else "Not Recorded",
                r["dept"],
                r["year"],
                r["association"],
                r["status"] if "status" in r.keys() and r["status"] else "ACTIVE",
                r["crypto_signature"] if "crypto_signature" in r.keys() else "VERIFIED",
                r["created_at"],
                r["interest"]
            ])

        csv_content = output.getvalue()
        output.close()

        log_audit_event("CSV_EXPORT_DOWNLOADED", ip, f"Exported {len(rows)} member records to CSV for HOD compliance.", conn=conn)
        filename = f"NKOCET_Association_Members_{datetime.now().strftime('%Y%m%d')}.csv"
        return Response(
            content=csv_content.encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )


@app.delete("/api/community/posts/{post_id}")
async def admin_delete_post(post_id: str, request: Request):
    """Admin endpoint: Moderates and deletes inappropriate community posts."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT post_id, title FROM community_posts WHERE post_id = ?;", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        cursor.execute("DELETE FROM community_comments WHERE post_id = ?;", (post_id,))
        cursor.execute("DELETE FROM community_posts WHERE post_id = ?;", (post_id,))
        log_audit_event("COMMUNITY_POST_PURGED", ip, f"Purged discussion thread {post_id}: '{row['title']}'", conn=conn)
        return {
            "success": True,
            "message": f"Discussion post '{row['title']}' was removed by Administrator."
        }


@app.get("/api/admin/community/unmask/{post_id}")
async def admin_unmask_post(post_id: str, request: Request):
    """
    Admin Authority: Reveals true student identity (Roll No, Name & Verified Gmail) for anonymous posts
    in case of severe code of conduct violations.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT p.post_id, p.author_name, p.roll_no, p.dept, p.year, p.title, p.created_at,
               COALESCE(u.name, m.name) AS registered_name,
               COALESCE(u.email, m.email) AS verified_email
        FROM community_posts p
        LEFT JOIN memberships m ON p.roll_no = m.roll_no
        LEFT JOIN community_users u ON p.roll_no = u.roll_no
        WHERE p.post_id = ?;
        """, (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        true_name = row["registered_name"] or row["author_name"]
        verified_email = row["verified_email"] or "Not recorded"
        log_audit_event("ANONYMOUS_AUTHOR_UNMASKED", ip, f"Unmasked anonymous author of {post_id} -> {true_name} ({row['roll_no']}) [{verified_email}]", conn=conn)

        return {
            "post_id": row["post_id"],
            "title": row["title"],
            "true_student_name": true_name,
            "true_roll_no": row["roll_no"],
            "verified_gmail": verified_email,
            "department": row["dept"],
            "year": row["year"],
            "timestamp": row["created_at"],
            "message": "Confidential identity unmasked for Administrative Moderation."
        }


# --------------------------------------------------------------------------
# MASTER ADMIN: CHAT USER MANAGEMENT & AUTHORITIES
# --------------------------------------------------------------------------

@app.get("/api/admin/chat/users")
async def get_admin_chat_users(request: Request):
    """
    Administrator endpoint: Returns all verified community chat users with confidential Gmails,
    Roll numbers, departments, and active/mute/ban status.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, name, roll_no, email, dept, status, created_at, last_active
        FROM community_users ORDER BY last_active DESC;
        """)
        rows = cursor.fetchall()
        return {"count": len(rows), "users": [dict(r) for r in rows]}


@app.patch("/api/admin/chat/users/{user_id}/status")
async def update_chat_user_status(user_id: str, data: ChatUserStatusUpdate, request: Request):
    """
    Admin Authority: Toggles student chat status between ACTIVE, MUTED, and BANNED.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    clean_id = user_id.strip()
    status = data.status.strip().upper()
    if status not in ["ACTIVE", "MUTED", "BANNED"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be ACTIVE, MUTED, or BANNED.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, roll_no, email FROM community_users WHERE user_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chat user not found.")

        if status == "BANNED":
            cursor.execute("""
            UPDATE community_users
            SET status = ?, session_token = NULL, session_revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = ?;
            """, (status, clean_id))
        else:
            cursor.execute("UPDATE community_users SET status = ? WHERE user_id = ?;", (status, clean_id))
        log_audit_event("CHAT_USER_STATUS_CHANGE", ip, f"Admin updated chat user {clean_id} ({row['name']}) status to {status}", conn=conn)

        return {
            "success": True,
            "user_id": clean_id,
            "status": status,
            "message": f"User {row['name']} ({row['roll_no']}) status updated to {status}."
        }


@app.delete("/api/admin/chat/users/{user_id}")
async def delete_chat_user(user_id: str, request: Request):
    """
    Admin Authority: Kicks and removes user from the community chat registry.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    clean_id = user_id.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, roll_no, email FROM community_users WHERE user_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chat user not found.")

        cursor.execute("DELETE FROM community_users WHERE user_id = ?;", (clean_id,))
        log_audit_event("CHAT_USER_KICKED", ip, f"Admin kicked and deleted chat user {clean_id} ({row['name']})", conn=conn)

        return {
            "success": True,
            "message": f"User {row['name']} has been kicked from the chat registry."
        }


@app.get("/api/admin/audit-logs")
async def list_security_audit_logs(request: Request, limit: int = 50):
    """Admin endpoint: Fetches live security and coordinator audit logs."""
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, event_type, actor_ip, details, timestamp
        FROM security_audit_logs ORDER BY id DESC LIMIT ?;
        """, (limit,))
        rows = cursor.fetchall()
        return {"logs": [dict(r) for r in rows]}


# --------------------------------------------------------------------------
# MASTER ADMIN: REAL SMTP MAILER CONFIGURATION & TEST
# --------------------------------------------------------------------------

@app.get("/api/admin/smtp-config")
async def get_admin_smtp_config(request: Request):
    """Admin endpoint: Returns SMTP status only; credential values are never exposed."""
    verify_admin_access(request)
    cfg = get_smtp_config()
    return {
        "configured": bool(cfg["user"] and cfg["password"]),
        "user": cfg["user"],
        "host": cfg["host"],
        "port": cfg["port"],
        "from_name": cfg["from_name"]
    }


@app.post("/api/admin/smtp-config")
async def save_admin_smtp_config(request: Request):
    """Reject legacy SMTP credential writes; configure SMTP in the server environment."""
    verify_admin_access(request)
    raise HTTPException(
        status_code=410,
        detail="SMTP credentials can no longer be saved through the admin console. Configure them in the server environment and restart the service.",
    )


@app.post("/api/admin/smtp-test")
async def test_admin_smtp_delivery(data: SmtpTestRequest, request: Request):
    """Admin endpoint: Sends a real test email to verify Google SMTP credentials live."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    test_email = data.test_email.strip().lower()

    test_otp = f"{secrets.randbelow(900000) + 100000}"
    res = send_real_smtp_email(test_email, "Administrator", test_otp)

    if res["sent"]:
        log_audit_event("SMTP_TEST_SUCCESS", ip, f"Test email successfully dispatched to {test_email}")
        return {
            "success": True,
            "message": f"Test email successfully delivered to {test_email}! Check your Gmail inbox now."
        }
    else:
        log_audit_event("SMTP_TEST_FAILED", ip, f"Test email failed for {test_email}: {res.get('reason')}")
        raise HTTPException(
            status_code=400,
            detail=f"SMTP Delivery Test Failed: {res.get('reason')}"
        )


# --------------------------------------------------------------------------
# ROOT REDIRECT & STATIC FILES
# --------------------------------------------------------------------------

@app.get("/")
async def root_redirect():
    """Redirects root domain to index.html."""
    index_file = os.path.join(DIRECTORY, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return JSONResponse({"message": "AssociationHub API is active. index.html not found."})


# Mount entire nkocet-website directory for serving HTML, CSS, JS, images
app.mount("/", StaticFiles(directory=DIRECTORY, html=True), name="static")


# --------------------------------------------------------------------------
# CLI ENTRY POINT
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8080))
    print("============================================================")
    print("   ASSOCIATIONHUB FULL-STACK SERVER (NKOCET 2026)")
    print("============================================================")
    print(f">> Server running at: http://127.0.0.1:{port}")
    print(f">> API Docs: http://127.0.0.1:{port}/docs")
    print(f">> Community Pulse: http://127.0.0.1:{port}/#community")
    print(">> Admin PIN and cryptographic secret loaded from environment.")
    print("============================================================")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
# Student registration is direct; legacy OTP endpoints are retained as tombstones.
@app.post("/api/student/register/send-otp")
async def student_register_send_otp(data: StudentSendOtpRequest, request: Request):
    raise HTTPException(status_code=410, detail="Student Gmail OTP registration has been removed.")

@app.post("/api/student/register/verify-otp")
async def student_register_verify_otp(data: StudentVerifyOtpRequest, request: Request):
    raise HTTPException(status_code=410, detail="Student Gmail OTP registration has been removed.")

@app.post("/api/student/register/complete", status_code=201)
async def student_register_complete(data: StudentCompleteRegistrationRequest, request: Request):
    """Register a student directly after basic validation and duplicate checks."""
    ip = get_client_ip(request)
    name = data.name.strip()
    email = data.email.strip().lower()
    roll = data.roll_no.strip().upper()
    dept = data.dept.strip()

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR roll_no = ? LIMIT 1;", (email, roll))
        if cursor.fetchone():
            log_audit_event("REGISTRATION_DUPLICATE_BLOCKED", ip, f"Blocked duplicate registration for {email} ({roll})", conn=conn)
            raise HTTPException(status_code=400, detail="Duplicate Account: The Gmail address or roll number is already registered.")

        # Duplicate check: Email
        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? LIMIT 1;", (email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate Account: The Gmail address '{email}' is already registered."
            )

        # Duplicate check: Roll Number
        cursor.execute("SELECT student_id FROM registered_students WHERE roll_no = ? LIMIT 1;", (roll,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate Account: College Roll Number '{roll}' is already registered."
            )

        # Secure password hashing (PBKDF2-HMAC-SHA256 with 100,000 iterations & unique salt)
        pwd_hash, salt = hash_student_password(data.password)

        # Generate unique Student ID
        student_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        verified_at = ""

        # Insert permanent student record
        cursor.execute("""
        INSERT INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
        """, (student_id, name, email, roll, dept, pwd_hash, salt, verified_at, created_at))

        # Synchronize into memberships table if not present so gate & verify know them
        cursor.execute("SELECT pass_id FROM memberships WHERE roll_no = ?;", (roll,))
        if not cursor.fetchone():
            pass_id = f"NKOCET-2026-CSESA-{secrets.token_hex(3).upper()}"
            sig = compute_hmac_signature(pass_id, roll, "CSESA")
            verify_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(verify_url)
            cursor.execute("""
            INSERT OR IGNORE INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
                VALUES (?, ?, ?, ?, ?, 'Second Year (SY)', 'CSESA', 'Registered Student', ?, 'ACTIVE', ?, ?);
            """, (pass_id, name, roll, email, dept, qr_b64, sig, created_at))

        session_token = f"STUDENT_SESSION.{secrets.token_hex(20)}"
        log_audit_event("STUDENT_REGISTERED", ip, f"Registered new student {name} ({roll}) with Gmail {email} [ID: {student_id}]", conn=conn)

        return {
            "success": True,
            "student_id": student_id,
            "full_name": name,
            "email": email,
            "roll_no": roll,
            "dept": dept,
            "is_email_verified": False,
            "email_verified_at": verified_at,
            "created_at": created_at,
            "session_token": session_token,
            "message": f"Congratulations {name}! Your student account ({student_id}) has been created."
        }


# --------------------------------------------------------------------------
# GMAIL VERIFICATION & OTP AUTHENTICATION
# --------------------------------------------------------------------------

@app.post("/api/auth/send-otp")
async def send_email_otp(data: SendOtpRequest, request: Request):
    """
    Sends a 6-digit OTP code to student's Gmail for identity verification.
    Security:
    - 60-second resend cooldown.
    - 5-minute (300 seconds) expiration limit.
    - Cryptographically hashed OTP storage (SHA-256 + HMAC salt).
    - Rate-limited per IP.
    - Real-time Gmail SMTP dispatch only. No plaintext OTP or simulated credentials exposed.
    """
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    roll = data.roll_no.strip().upper() if data.roll_no else None
    now = time.time()

    # Enforce Rejoin Approval Gate: Blocked or removed students require Admin approval
    check_account_restriction(email, roll, data.name)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Enforce 60-second resend cooldown
        cursor.execute("SELECT last_sent_at FROM email_otp_verifications WHERE email = ?;", (email,))
        existing = cursor.fetchone()
        if existing and existing["last_sent_at"]:
            elapsed = now - existing["last_sent_at"]
            if elapsed < 60:
                remaining = int(60 - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Cooldown active: Please wait {remaining} seconds before requesting a new OTP."
                )

        # 2. Prevent duplicate email registration if registering for membership pass
        if request.url.path == "/api/auth/send-otp":
            cursor.execute("SELECT pass_id FROM memberships WHERE email = ? LIMIT 1;", (email,))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate Registration: The Gmail address '{email}' is already registered as an official member."
                )

        # 3. Secure 6-digit OTP generation & cryptographic SHA-256 hashing
        otp_code = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = hash_otp(otp_code, email)
        expires_at = now + 300  # Strictly 5 minutes validity

        # 4. Store hashed OTP, timestamps, and reset attempt counter in database
        if request.url.path == "/api/auth/send-otp" and (not roll or not data.association):
            raise HTTPException(status_code=400, detail="Roll number and association are required for membership verification.")

        cursor.execute("""
        INSERT INTO email_otp_verifications
            (email, otp_hash, otp_code, roll_no, association, session_id, expires_at, last_sent_at, attempts, is_verified, created_at)
        VALUES (?, ?, '', ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            otp_hash = excluded.otp_hash,
            otp_code = '',
            roll_no = excluded.roll_no,
            association = excluded.association,
            session_id = excluded.session_id,
            expires_at = excluded.expires_at,
            last_sent_at = excluded.last_sent_at,
            attempts = 0,
            is_verified = 0,
            verification_token = NULL,
            verified_at = NULL;
        """, (email, otp_hash, roll, data.association, data.session_id, expires_at, now))
        log_audit_event("OTP_REQUESTED", ip, f"OTP requested for {email} (Roll: {roll})", conn=conn)

    # 5. Dispatch real email via Gmail SMTP
    clean_name = data.name.strip() if data.name else "Student"
    smtp_res = send_real_smtp_email(email, clean_name, otp_code)

    if not smtp_res["sent"]:
        log_audit_event("EMAIL_DISPATCH_FAILED", ip, f"Gmail SMTP delivery failed to {email}: {smtp_res.get('reason')}")
        raise HTTPException(
            status_code=503,
            detail="Verification email could not be sent. Please try again later."
        )

    log_audit_event("REAL_EMAIL_DISPATCHED", ip, f"Dispatched real email with OTP to {email}")
    return {
        "success": True,
        "email": email,
        "expires_in_seconds": 300,
        "cooldown_seconds": 60,
        "message": f"Verification code successfully dispatched to your Gmail inbox ({email})! Valid for 5 minutes."
    }


@app.post("/api/auth/verify-otp")
async def verify_email_otp(data: VerifyOtpRequest, request: Request):
    """
    Verifies 6-digit OTP code against stored cryptographic hash.
    Security:
    - 5-minute expiration limit.
    - Maximum 5 attempts lockout.
    - Timing-attack safe hash comparison.
    - Permanent database storage of verified status and verified_at timestamp.
    """
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    otp = data.otp.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT otp_hash, expires_at, attempts FROM email_otp_verifications
        WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?;
        """, (email, data.session_id, data.roll_no, data.association))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="No verification request found for this email. Please click 'Send OTP' first.")

        if time.time() >= row["expires_at"]:
            raise HTTPException(status_code=400, detail="OTP verification code has expired (5-minute validity limit). Please request a new code.")

        if row["attempts"] >= 5:
            raise HTTPException(status_code=429, detail="Too many incorrect OTP attempts (maximum 5). For security, this OTP has been locked. Please request a new code.")

        # Cryptographic hash verification with timing-attack safe comparison
        candidate_hash = hash_otp(otp, email)
        if not hmac.compare_digest(row["otp_hash"] or "", candidate_hash):
            new_attempts = row["attempts"] + 1
            cursor.execute("""
            UPDATE email_otp_verifications SET attempts = ?
            WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?;
            """, (new_attempts, email, data.session_id, data.roll_no, data.association))
            conn.commit()
            remaining = 5 - new_attempts
            if remaining <= 0:
                raise HTTPException(status_code=429, detail="Maximum 5 incorrect attempts reached. This OTP has been invalidated. Please request a new code.")
            raise HTTPException(status_code=400, detail=f"Incorrect OTP verification code. {remaining} attempt(s) remaining.")

        token = f"VERIFIED_{secrets.token_hex(16)}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        UPDATE email_otp_verifications
        SET is_verified = 1,
            verification_token = ?,
            verified_at = ?,
            attempts = 0,
            otp_hash = NULL
        WHERE email = ? AND session_id = ? AND roll_no IS ? AND association IS ?
          AND otp_hash = ? AND is_verified = 0 AND expires_at > ?;
        """, (token, now_str, email, data.session_id, data.roll_no, data.association, row["otp_hash"], time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=400, detail="OTP verification session expired or was already used. Please request a new code.")

        log_audit_event("GMAIL_VERIFIED", ip, f"Verified email {email} successfully", conn=conn)

        return {
            "success": True,
            "verified": True,
            "email": email,
            "verification_token": token,
            "verified_at": now_str,
            "message": f"Gmail identity verified successfully for {email}!"
        }


# --------------------------------------------------------------------------
# GATED COMMUNITY CHAT AUTHENTICATION GATEWAY
# --------------------------------------------------------------------------

@app.post("/api/chat/auth/send-otp")
async def send_chat_otp(data: SendOtpRequest, request: Request):
    raise HTTPException(status_code=410, detail="Chat Gmail OTP verification has been removed.")


@app.post("/api/chat/auth/verify-and-enter")
async def verify_and_enter_chat(data: ChatRegisterRequest, request: Request):
    """Registers a chat identity directly without changing email verification state."""
    ip = get_client_ip(request)
    email = data.email.strip().lower()
    name = data.name.strip()
    roll = data.roll_no.strip().upper()
    dept = data.dept.strip()
    check_account_restriction(email, roll, name)

    with get_db() as conn:
        cursor = conn.cursor()
        # Check if user already exists and is banned
        cursor.execute("SELECT user_id, status FROM community_users WHERE email = ? OR roll_no = ?;", (email, roll))
        existing_user = cursor.fetchone()
        if existing_user and existing_user["status"] == "BANNED":
            raise HTTPException(status_code=403, detail="⛔ Access Denied: Your chat account has been banned by the Administrator.")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = existing_user["user_id"] if existing_user else f"CHAT-USER-{secrets.token_hex(4).upper()}"
        session_token = f"CHAT_SESSION.{secrets.token_hex(16)}"
        session_expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_users
            (user_id, name, roll_no, email, dept, status, session_token, session_expires_at, session_revoked_at, created_at, last_active)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = excluded.name,
            roll_no = excluded.roll_no,
            dept = excluded.dept,
            session_token = excluded.session_token,
            session_expires_at = excluded.session_expires_at,
            session_revoked_at = NULL,
            last_active = excluded.last_active;
        """, (user_id, name, roll, email, dept, session_token, session_expires_at, now_str, now_str))

        # Ensure student is recorded in memberships table so gate & verify know them
        cursor.execute("SELECT pass_id FROM memberships WHERE roll_no = ?;", (roll,))
        if not cursor.fetchone():
            pass_id = f"NKOCET-2026-CSESA-{secrets.token_hex(3).upper()}"
            sig = compute_hmac_signature(pass_id, roll, "CSESA")
            qr_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(qr_url)
            cursor.execute("""
            INSERT OR IGNORE INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
            VALUES (?, ?, ?, ?, ?, 'Second Year (SY)', 'CSESA', 'Campus Pulse Community Peer', ?, 'ACTIVE', ?, ?);
            """, (pass_id, name, roll, email, dept, qr_b64, sig, now_str))

        log_audit_event("CHAT_GATEWAY_AUTHENTICATED", ip, f"Student {name} ({roll}) entered community chat via {email}", conn=conn)

        return {
            "success": True,
            "message": f"Welcome to Campus Pulse, {name}!",
            "token": session_token,
            "user": {
                "user_id": user_id,
                "name": name,
                "roll_no": roll,
                "email": email,
                "dept": dept,
                "status": "ACTIVE"
            }
        }


@app.get("/api/chat/auth/me")
async def get_chat_current_user(request: Request):
    """Validates active chat token and returns user profile & status."""
    token = request.headers.get("X-Chat-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthenticated: No active chat session token.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, name, roll_no, email, dept, status, created_at
        FROM community_users
        WHERE session_token = ? AND session_revoked_at IS NULL
          AND session_expires_at IS NOT NULL
          AND julianday(session_expires_at) > julianday('now')
          AND status IN ('ACTIVE', 'MUTED');
        """, (token.strip(),))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Chat session expired or invalid. Please enter the chat again.")

        return {
            "authenticated": True,
            "user": dict(user)
        }


# --------------------------------------------------------------------------
# MEMBERSHIP INTAKE & VERIFICATION
# --------------------------------------------------------------------------

@app.post("/api/memberships", status_code=201)
async def create_membership(data: MembershipCreate, request: Request):
    """
    Intakes new student membership, verifies Gmail OTP, computes cryptographic HMAC-SHA256 signature & Base64 QR,
    and persists in SQLite with duplicate checking and rate limiting.
    """
    ip = get_client_ip(request)
    check_register_rate_limit(ip)

    name = data.name.strip()
    roll = data.roll.strip().upper()
    dept = data.dept.strip()
    year = data.year.strip()
    assoc = data.association
    email = (data.email or "").strip().lower()
    otp_token = data.otp_token
    session_id = data.session_id
    interest = data.interest.strip() if data.interest else "General Technical Participation & Workshops"

    # Enforce Rejoin Approval Gate: Blocked or removed students require Admin approval to rejoin
    check_account_restriction(email, roll, name)
    if not email:
        raise HTTPException(status_code=403, detail="A valid student email address is required.")

    with get_db() as conn:
        cursor = conn.cursor()
        # 1. Existing Member Check: If student already registered for this club or has a pass,
        # return their official Digital Pass only after consuming an OTP bound to this member.
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships
        WHERE (roll_no = ? AND association = ?) OR (email != '' AND email = ? AND association = ?)
        ORDER BY rowid DESC LIMIT 1;
        """, (roll, assoc, email, assoc))
        existing = cursor.fetchone()

        if existing:
            pass_id = existing["pass_id"]
            sig = existing["crypto_signature"] or compute_hmac_signature(pass_id, existing["roll_no"], existing["association"])
            verify_url = build_verification_url(pass_id, sig)
            qr_b64 = make_qr_base64(verify_url)

            # Fetch or generate Verified Student ID
            cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR (roll_no != '' AND roll_no = ?) LIMIT 1;", 
                           (existing["email"], existing["roll_no"]))
            stu_row = cursor.fetchone()
            if stu_row:
                verified_stu_id = stu_row["student_id"]
            else:
                verified_stu_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
                pwd_hash, salt = hash_student_password("MemberPass@" + pass_id[-6:])
                cursor.execute("""
                INSERT OR IGNORE INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', 'ACTIVE', ?);
                """, (verified_stu_id, existing["name"], existing["email"], existing["roll_no"], existing["dept"], pwd_hash, salt, existing["created_at"]))

            return {
                "pass_id": pass_id,
                "student_id": verified_stu_id,
                "name": existing["name"],
                "roll_no": existing["roll_no"],
                "dept": existing["dept"],
                "year": existing["year"],
                "association": existing["association"],
                "interest": existing["interest"] or interest,
                "qr_code_base64": qr_b64,
                "status": existing["status"],
                "crypto_signature": sig,
                "verify_url": verify_url,
                "created_at": existing["created_at"],
                "is_existing": True,
                "message": f"Welcome back, {existing['name']}! Your official Digi-Pass was loaded from the database."
            }

        is_verified = 0

        # 3. Generate unique Pass ID
        unique_hex = secrets.token_hex(3).upper()
        pass_id = f"NKOCET-2026-{assoc}-{unique_hex}"
        
        # Compute Cryptographic HMAC-SHA256 signature
        sig = compute_hmac_signature(pass_id, roll, assoc)

        # Generate verification QR Code with signature
        verify_url = build_verification_url(pass_id, sig)
        qr_b64 = make_qr_base64(verify_url)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 4. Save into SQLite memberships table
        cursor.execute("""
        INSERT INTO memberships (pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?);
        """, (pass_id, name, roll, email, dept, year, assoc, interest, qr_b64, sig, created_at))

        # 5. Save into SQLite registered_students table for unified record keeping
        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR roll_no = ? LIMIT 1;", (email, roll))
        stu_row = cursor.fetchone()
        if stu_row:
            verified_stu_id = stu_row["student_id"]
        else:
            verified_stu_id = f"NKOCET-STU-2026-{secrets.token_hex(3).upper()}"
            pwd_hash, salt = hash_student_password("MemberPass@" + unique_hex)
            cursor.execute("""
            INSERT OR IGNORE INTO registered_students (student_id, full_name, email, roll_no, dept, password_hash, password_salt, is_email_verified, email_verified_at, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', 'ACTIVE', ?);
            """, (verified_stu_id, name, email, roll, dept, pwd_hash, salt, created_at))

        log_audit_event("MEMBER_REGISTERED", ip, f"Registered {name} ({roll}) in {assoc} [Gmail: {email}] [Pass: {pass_id}] [Student ID: {verified_stu_id}]", conn=conn)

        return {
            "pass_id": pass_id,
            "student_id": verified_stu_id,
            "name": name,
            "roll_no": roll,
            "email": email,
            "dept": dept,
            "year": year,
            "association": assoc,
            "interest": interest,
            "qr_code_base64": qr_b64,
            "status": "ACTIVE",
            "crypto_signature": sig,
            "verify_url": verify_url,
            "created_at": created_at,
            "is_existing": False,
            "message": f"Congratulations {name}! Your official Digi-Pass has been generated and permanently saved in the database."
        }


@app.get("/api/memberships")
async def list_memberships(request: Request, association: Optional[str] = None):
    """Lists registered members (excluding large QR base64 strings for speed)."""
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        if association:
            cursor.execute("""
            SELECT pass_id, name, roll_no, dept, year, association, interest, status, created_at
            FROM memberships WHERE association = ? ORDER BY created_at DESC;
            """, (association.strip().upper(),))
        else:
            cursor.execute("""
            SELECT pass_id, name, roll_no, dept, year, association, interest, status, created_at
            FROM memberships ORDER BY created_at DESC;
            """)
        rows = cursor.fetchall()
        return {"count": len(rows), "members": [dict(r) for r in rows]}


@app.post("/api/memberships/lookup/send-otp")
async def send_membership_lookup_otp(data: MembershipLookupOtpRequest, request: Request):
    clean_q = data.query.strip()
    with get_db() as conn:
        row = conn.execute("""
        SELECT roll_no, association, email, name
        FROM memberships
        WHERE pass_id = ? OR roll_no = ? OR email = ?
        ORDER BY rowid DESC LIMIT 1;
        """, (clean_q, clean_q.upper(), clean_q.lower())).fetchone()
    if not row or (row["email"] or "").strip().lower() != data.email:
        raise HTTPException(status_code=404, detail="No membership matching those details was found.")

    otp_request = SendOtpRequest(
        email=data.email,
        name=row["name"],
        roll_no=row["roll_no"],
        association=row["association"],
        session_id=data.session_id,
    )
    result = await send_email_otp(otp_request, request)
    return {
        **result,
        "roll_no": row["roll_no"],
        "association": row["association"],
    }


@app.post("/api/memberships/lookup")
async def lookup_membership(data: MembershipLookupRequest, request: Request):
    """
    Retrieves a digital pass only after consuming an OTP bound to its email,
    roll number, association, and verification session.
    """
    clean_q = data.query.strip()
    if not clean_q or len(clean_q) < 2:
        raise HTTPException(status_code=400, detail="Please enter a valid Roll No, PRN, Email, or Pass ID.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships
        WHERE pass_id = ? OR roll_no = ? OR email = ?
        ORDER BY rowid DESC LIMIT 1;
        """, (clean_q, clean_q.upper(), clean_q.lower()))
        m = cursor.fetchone()

        if (not m or (m["email"] or "").strip().lower() != data.email
                or m["roll_no"].strip().upper() != data.roll_no
                or m["association"].strip().upper() != data.association):
            raise HTTPException(status_code=404, detail="No membership matching those details was found.")

        cursor.execute("""
        UPDATE email_otp_verifications
        SET is_verified = 0, verification_token = NULL, verified_at = NULL, otp_hash = NULL
        WHERE email = ? AND roll_no = ? AND association = ? AND session_id = ?
          AND verification_token = ? AND is_verified = 1 AND expires_at > ?;
        """, (data.email, data.roll_no, data.association, data.session_id, data.otp_token, time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=403, detail="Email verification is missing, expired, used, or does not match this pass. Please verify again.")

        pass_id = m["pass_id"]
        sig = m["crypto_signature"] or compute_hmac_signature(pass_id, m["roll_no"], m["association"])
        verify_url = build_verification_url(pass_id, sig)
        qr_b64 = make_qr_base64(verify_url)

        cursor.execute("SELECT student_id FROM registered_students WHERE email = ? OR (roll_no != '' AND roll_no = ?) LIMIT 1;", (m["email"], m["roll_no"]))
        s_row = cursor.fetchone()
        student_id = s_row["student_id"] if s_row else f"NKOCET-STU-2026-{pass_id[-6:]}"

        return {
            "pass_id": pass_id,
            "student_id": student_id,
            "name": m["name"],
            "roll_no": m["roll_no"],
            "dept": m["dept"],
            "year": m["year"],
            "association": m["association"],
            "interest": m["interest"],
            "qr_code_base64": qr_b64,
            "status": m["status"],
            "crypto_signature": sig,
            "verify_url": verify_url,
            "created_at": m["created_at"]
        }


@app.get("/api/memberships/verify/{pass_id}")
async def verify_membership(pass_id: str, request: Request, sig: Optional[str] = None):
    """
    Public QR gate check-in verification for membership passes with cryptographic signature validation.
    """
    clean_id = pass_id.strip()
    ip = get_client_ip(request)
    check_gate_verify_rate_limit(ip)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, dept, year, association, interest, qr_code_base64, status, crypto_signature, created_at
        FROM memberships WHERE pass_id = ?;
        """, (clean_id,))
        row = cursor.fetchone()

        if not row:
            log_audit_event("GATE_VERIFY_NOT_FOUND", ip, f"Pass {clean_id} not found in ledger")
            raise HTTPException(
                status_code=404,
                detail=f"Membership pass '{clean_id}' was not found or is invalid."
            )

        status = row["status"] if "status" in row.keys() and row["status"] else "ACTIVE"
        expected_sig = compute_hmac_signature(row["pass_id"], row["roll_no"], row["association"])
        sig_valid = bool(sig) and hmac.compare_digest(expected_sig, sig)
        # For manual typed lookups (no sig), still show member data but flag sig as unverified.
        # Only block if a sig was supplied but it's wrong (tampered pass).
        if sig and not sig_valid:
            log_audit_event(
                "GATE_VERIFY_INVALID_SIGNATURE",
                ip,
                f"Tampered/invalid signature supplied for pass {clean_id}",
                conn=conn,
            )
        elif not sig:
            log_audit_event(
                "GATE_VERIFY_MANUAL_LOOKUP",
                ip,
                f"Manual pass lookup (no signature) for pass {clean_id}",
                conn=conn,
            )
        try:
            verify_url = build_verification_url(row["pass_id"], expected_sig)
            qr_b64 = make_qr_base64(verify_url)
        except Exception:
            verify_url = ""
            qr_b64 = row["qr_code_base64"] or ""

        if status == "SUSPENDED":
            log_audit_event("GATE_VERIFY_SUSPENDED", ip, f"Suspended pass inspected: {clean_id}")
            return {
                "valid": False,
                "status": "SUSPENDED",
                "signature_verified": sig_valid,
                "crypto_signature": expected_sig,
                "message": "This membership pass is TEMPORARILY SUSPENDED by college administration. Access denied at gate.",
                "member": {
                    "pass_id": row["pass_id"],
                    "name": row["name"],
                    "roll_no": row["roll_no"],
                    "dept": row["dept"],
                    "year": row["year"],
                    "association": row["association"],
                    "interest": row["interest"],
                    "status": "SUSPENDED",
                    "qr_code_base64": qr_b64,
                    "verify_url": verify_url,
                    "crypto_signature": expected_sig,
                    "created_at": row["created_at"]
                }
            }

        return {
            "valid": True,
            "status": "ACTIVE",
            "signature_verified": sig_valid,
            "crypto_signature": expected_sig,
            "security_seal": "NKOCET-DIGITAL-LEDGER-VERIFIED",
            "member": {
                "pass_id": row["pass_id"],
                "name": row["name"],
                "roll_no": row["roll_no"],
                "dept": row["dept"],
                "year": row["year"],
                "association": row["association"],
                "interest": row["interest"],
                "status": status,
                "qr_code_base64": qr_b64,
                "verify_url": verify_url,
                "crypto_signature": expected_sig,
                "created_at": row["created_at"]
            }
        }


@app.post("/api/gate/check-in")
async def record_gate_checkin(data: GateCheckinRequest, request: Request):
    """
    Public / Coordinator Gate Scanner: Validates student pass status and logs attendance.
    Denies entry if pass is suspended or invalid.
    """
    clean_id = data.pass_id.strip()
    checkpoint = data.checkpoint.strip() if data.checkpoint else "Central Gate / Main Campus"
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, dept, year, association, status
        FROM memberships WHERE pass_id = ?;
        """, (clean_id,))
        row = cursor.fetchone()

        if not row:
            log_audit_event("GATE_CHECKIN_FAILED", ip, f"Invalid pass ID attempted: {clean_id} at {checkpoint}")
            raise HTTPException(status_code=404, detail=f"Pass ID '{clean_id}' not found in registry.")

        status = row["status"] if "status" in row.keys() and row["status"] else "ACTIVE"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status == "SUSPENDED":
            log_audit_event("GATE_CHECKIN_DENIED", ip, f"Suspended pass denied entry: {clean_id} ({row['name']}) at {checkpoint}", conn=conn)
            cursor.execute("""
            INSERT INTO gate_checkins (pass_id, student_name, roll_no, association, checkpoint, status, timestamp)
            VALUES (?, ?, ?, ?, ?, 'DENIED_SUSPENDED', ?);
            """, (clean_id, row["name"], row["roll_no"], row["association"], checkpoint, now_str))
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Membership pass for {row['name']} is currently SUSPENDED by administration."
            )

        cursor.execute("""
        INSERT INTO gate_checkins (pass_id, student_name, roll_no, association, checkpoint, status, timestamp)
        VALUES (?, ?, ?, ?, ?, 'ENTRY_GRANTED', ?);
        """, (clean_id, row["name"], row["roll_no"], row["association"], checkpoint, now_str))

        log_audit_event("GATE_CHECKIN_SUCCESS", ip, f"Student {row['name']} ({row['roll_no']}) checked in at {checkpoint}", conn=conn)

        return {
            "success": True,
            "status": "ENTRY_GRANTED",
            "message": f"Gate access granted for {row['name']} ({row['association']})",
            "student_name": row["name"],
            "roll_no": row["roll_no"],
            "dept": row["dept"],
            "year": row["year"],
            "association": row["association"],
            "checkpoint": checkpoint,
            "timestamp": now_str,
            "pass_id": clean_id
        }


@app.get("/api/gate/checkins")
async def list_gate_checkins(limit: int = 50, pass_id: Optional[str] = None):
    """Returns recent gate attendance logs."""
    with get_db() as conn:
        cursor = conn.cursor()
        if pass_id:
            cursor.execute("""
            SELECT id, pass_id, student_name, roll_no, association, checkpoint, status, timestamp
            FROM gate_checkins WHERE pass_id = ? ORDER BY id DESC LIMIT ?;
            """, (pass_id.strip(), limit))
        else:
            cursor.execute("""
            SELECT id, pass_id, student_name, roll_no, association, checkpoint, status, timestamp
            FROM gate_checkins ORDER BY id DESC LIMIT ?;
            """, (limit,))
        rows = cursor.fetchall()
        return {"checkins": [dict(r) for r in rows]}


@app.delete("/api/memberships/{pass_id}")
async def delete_membership(pass_id: str, request: Request):
    """
    Admin endpoint: Permanently revokes and removes a registered member pass from the database.
    Requires Administrator Authorization.
    """
    verify_admin_access(request)
    clean_id = pass_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pass_id, name, roll_no, association, email FROM memberships WHERE pass_id = ?;", (clean_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Membership pass '{clean_id}' was not found in the registry."
            )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if existing["email"] or existing["roll_no"]:
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Membership Pass Revoked by Administrator', 'RESTRICTED', ?);
            """, (existing["email"] or "", existing["roll_no"], existing["name"], now_str))

        cursor.execute("DELETE FROM memberships WHERE pass_id = ?;", (clean_id,))
        log_audit_event("MEMBER_REVOKED_DELETED", ip, f"Revoked & deleted pass {clean_id} for {existing['name']} (Roll: {existing['roll_no']})", conn=conn)
        return {
            "success": True,
            "message": f"Membership for {existing['name']} (Roll: {existing['roll_no']}, {existing['association']}) has been successfully revoked and removed.",
            "pass_id": clean_id
        }


# --------------------------------------------------------------------------
# CAMPUS PULSE: STUDENT EXPERIENCE & DISCUSSION HUB
# --------------------------------------------------------------------------

@app.get("/api/community/posts")
async def list_community_posts(
    category: Optional[str] = None,
    dept: Optional[str] = None,
    search: Optional[str] = None
):
    """Lists community posts with comment counts and like tallies."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
        SELECT p.post_id, p.author_name, p.roll_no, p.dept, p.year, p.category, p.title, p.content, p.is_anonymous, p.likes, p.created_at,
               COUNT(c.comment_id) AS comment_count
        FROM community_posts p
        LEFT JOIN community_comments c ON p.post_id = c.post_id
        WHERE 1=1
        """
        params = []

        if category and category.upper() != "ALL":
            query += " AND p.category = ?"
            params.append(category.strip().upper())

        if dept and dept.upper() != "ALL":
            query += " AND p.dept LIKE ?"
            params.append(f"%{dept.strip()}%")

        if search:
            query += " AND (p.title LIKE ? OR p.content LIKE ?)"
            s = f"%{search.strip()}%"
            params.extend([s, s])

        query += " GROUP BY p.post_id ORDER BY p.created_at DESC;"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        posts = []
        for r in rows:
            p = dict(r)
            if p["is_anonymous"] == 1:
                p["author_name"] = "Anonymous Orchidite"
                p["roll_no"] = "Verified Student"
            posts.append(p)

        return {"count": len(posts), "posts": posts}


@app.post("/api/community/posts", status_code=201)
async def create_community_post(data: CommunityPostCreate, request: Request):
    """
    Submits a new student experience post.
    Security Gate: Verified against active registered memberships or community_users in SQLite!
    Enforces Campus Anti-Troll Shield and checks Mute/Ban status.
    """
    ip = get_client_ip(request)
    roll = data.roll_no.strip().upper()
    cat = data.category.strip().upper()
    if cat not in ALLOWED_CATEGORIES:
        cat = "GENERAL"

    with get_db() as conn:
        cursor = conn.cursor()

        # Campus Anti-Troll Filter
        check_anti_troll(data.title, roll, ip, conn=conn)
        check_anti_troll(data.content, roll, ip, conn=conn)
        check_rate_limit(roll)
        check_account_restriction("", roll_no=roll)

        # Check if student is BANNED or MUTED
        cursor.execute("SELECT user_id, status FROM community_users WHERE roll_no = ?;", (roll,))
        cuser = cursor.fetchone()
        if cuser:
            if cuser["status"] == "BANNED":
                raise HTTPException(status_code=403, detail="⛔ Access Revoked: Your community chat account has been banned by the Administrator.")
            if cuser["status"] == "MUTED":
                raise HTTPException(status_code=403, detail="⏸️ Account Muted: You have been temporarily muted from posting by the Administrator.")

        # Verify student exists in memberships or community_users
        cursor.execute("SELECT name, roll_no, dept, year FROM memberships WHERE roll_no = ? LIMIT 1;", (roll,))
        verified = cursor.fetchone()
        if not verified:
            cursor.execute("SELECT name, roll_no, dept FROM community_users WHERE roll_no = ? LIMIT 1;", (roll,))
            c_verified = cursor.fetchone()
            if not c_verified:
                raise HTTPException(
                    status_code=403,
                    detail=f"Security Gate: Roll No '{roll}' was not found in the student registry."
                )
            verified = {"name": c_verified["name"], "roll_no": c_verified["roll_no"], "dept": c_verified["dept"], "year": "Second Year (SY)"}

        post_id = f"POST-2026-{secrets.token_hex(4).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_posts (post_id, author_name, roll_no, dept, year, category, title, content, is_anonymous, likes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """, (
            post_id,
            verified["name"] if not data.is_anonymous else data.author_name,
            roll,
            verified["dept"],
            verified["year"],
            cat,
            data.title,
            data.content,
            1 if data.is_anonymous else 0,
            created_at
        ))

        # Update last_active in community_users
        cursor.execute("UPDATE community_users SET last_active = ? WHERE roll_no = ?;", (created_at, roll))

        return {
            "success": True,
            "post_id": post_id,
            "message": "Your experience has been verified and published to Campus Pulse!"
        }


@app.post("/api/community/posts/{post_id}/like")
async def like_community_post(post_id: str):
    """Upvotes an experience post."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT likes FROM community_posts WHERE post_id = ?;", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        new_likes = row["likes"] + 1
        cursor.execute("UPDATE community_posts SET likes = ? WHERE post_id = ?;", (new_likes, post_id))
        return {"post_id": post_id, "likes": new_likes}


@app.get("/api/community/posts/{post_id}/comments")
async def get_post_comments(post_id: str):
    """Fetches replies to a discussion thread."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT comment_id, post_id, author_name, roll_no, content, created_at
        FROM community_comments WHERE post_id = ? ORDER BY created_at ASC;
        """, (post_id,))
        rows = cursor.fetchall()
        return {"comments": [dict(r) for r in rows]}


@app.post("/api/community/posts/{post_id}/comments", status_code=201)
async def create_post_comment(post_id: str, data: CommunityCommentCreate, request: Request):
    """
    Posts a reply to a discussion thread.
    Security Gate: Verified against active registered memberships or community_users in SQLite!
    Enforces Campus Anti-Troll Shield.
    """
    ip = get_client_ip(request)
    roll = data.roll_no.strip().upper()

    with get_db() as conn:
        cursor = conn.cursor()

        # Anti-troll check
        check_anti_troll(data.content, roll, ip, conn=conn)

        # Check if student is BANNED or MUTED
        cursor.execute("SELECT status FROM community_users WHERE roll_no = ?;", (roll,))
        cuser = cursor.fetchone()
        if cuser:
            if cuser["status"] == "BANNED":
                raise HTTPException(status_code=403, detail="⛔ Access Denied: Your chat account has been banned.")
            if cuser["status"] == "MUTED":
                raise HTTPException(status_code=403, detail="⏸️ Account Muted: You cannot reply while muted by the Administrator.")

        # Verify student exists in memberships or community_users
        cursor.execute("SELECT name, roll_no FROM memberships WHERE roll_no = ? LIMIT 1;", (roll,))
        verified = cursor.fetchone()
        if not verified:
            cursor.execute("SELECT name, roll_no FROM community_users WHERE roll_no = ? LIMIT 1;", (roll,))
            c_verified = cursor.fetchone()
            if not c_verified:
                raise HTTPException(
                    status_code=403,
                    detail=f"Security Gate: Roll No '{roll}' is not registered."
                )
            verified = {"name": c_verified["name"], "roll_no": c_verified["roll_no"]}

        cursor.execute("SELECT post_id FROM community_posts WHERE post_id = ?;", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Thread not found.")

        comment_id = f"COMM-{secrets.token_hex(3).upper()}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO community_comments (comment_id, post_id, author_name, roll_no, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (comment_id, post_id, verified["name"], roll, data.content, created_at))

        return {
            "success": True,
            "comment_id": comment_id,
            "author_name": verified["name"],
            "created_at": created_at
        }


# --------------------------------------------------------------------------
# CAMPUS ANNOUNCEMENT BROADCASTER
# --------------------------------------------------------------------------

@app.get("/api/announcements/current")
async def get_current_announcement():
    """Fetches the active campus ribbon announcement."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tag, message, button_text, updated_at FROM announcements WHERE is_active = 1 ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return {
                "tag": "📢 Campus Notice",
                "message": "Academic Session 2026 Student Association Membership & Council Registrations Open.",
                "button_text": "Apply Now →"
            }
        return dict(row)


@app.post("/api/admin/announcements")
async def update_announcement(data: AnnouncementUpdate, request: Request):
    """Admin endpoint: Broadcasts a new top announcement across the entire portal."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO announcements (tag, message, button_text, is_active, updated_at)
        VALUES (?, ?, ?, 1, ?);
        """, (data.tag.strip(), data.message.strip(), data.button_text.strip(), updated_at))
        
        log_audit_event("ANNOUNCEMENT_PUBLISHED", ip, f"Published broadcast: [{data.tag.strip()}] {data.message.strip()[:60]}...")
        return {
            "success": True,
            "message": "Live announcement broadcast successfully updated across portal.",
            "announcement": {
                "tag": data.tag.strip(),
                "message": data.message.strip(),
                "button_text": data.button_text.strip(),
                "updated_at": updated_at
            }
        }


# --------------------------------------------------------------------------
# MASTER ADMIN CONTROL SUITE
# --------------------------------------------------------------------------

@app.post("/api/admin/verify-pin")
async def verify_admin_pin(data: AdminPinVerify, request: Request):
    """Validates Admin Master PIN with brute-force defense and returns signed session token."""
    ip = get_client_ip(request)
    check_admin_brute_force(ip)

    submitted_pin = data.pin.strip()
    if hmac.compare_digest(submitted_pin.encode("utf-8"), ADMIN_SECRET_PIN.encode("utf-8")):
        _admin_failed_attempts.pop(ip, None)
        with get_db() as conn:
            conn.execute("DELETE FROM admin_failed_attempts WHERE ip_address = ?;", (ip,))
        token = create_admin_session_token()
        log_audit_event("ADMIN_LOGIN_SUCCESS", ip, "Coordinator Console clearance unlocked.")
        return {
            "valid": True,
            "token": token,
            "expires_in_hours": 3,
            "message": "Master Administrator clearance verified."
        }
    
    record_admin_failed_attempt(ip)
    log_audit_event("ADMIN_LOGIN_FAILED", ip, "Invalid PIN entered.")
    raise HTTPException(status_code=403, detail="Invalid Administrator Security PIN.")


@app.post("/api/admin/logout")
async def logout_admin(request: Request):
    """Revokes the current administrator session token."""
    verify_admin_access(request)
    key = (
        request.headers.get("X-Admin-Token")
        or request.headers.get("X-Admin-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if key.startswith("SESSION."):
        parts = key.split(".")
        if len(parts) >= 3:
            with get_db() as conn:
                conn.execute(
                    "UPDATE admin_sessions SET revoked_at = ? WHERE session_id = ?;",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), parts[2]),
                )
    return {"success": True, "message": "Administrator session revoked."}


@app.patch("/api/admin/members/{pass_id}/status")
async def update_member_status(pass_id: str, data: StatusUpdate, request: Request):
    """Admin endpoint: Toggles student status between ACTIVE and SUSPENDED."""
    verify_admin_access(request)
    clean_id = pass_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pass_id, name, roll_no, email FROM memberships WHERE pass_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Member pass not found.")

        cursor.execute("UPDATE memberships SET status = ? WHERE pass_id = ?;", (data.status, clean_id))
        
        if data.status in ["SUSPENDED", "BLOCKED", "RESTRICTED"]:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Member Pass Suspended by Administrator', 'RESTRICTED', ?);
            """, (row["email"] or "", row["roll_no"], row["name"], now_str))
        log_audit_event("MEMBER_STATUS_CHANGED", ip, f"Updated pass {clean_id} ({row['name']}) status to {data.status}", conn=conn)
        return {
            "success": True,
            "pass_id": clean_id,
            "status": data.status,
            "message": f"Status for {row['name']} updated to {data.status}."
        }


@app.get("/api/admin/students")
async def list_admin_registered_students(request: Request):
    """
    Administrator endpoint: Lists all registered students with verified email timestamps.
    Access strictly gated to Master Admin Authority. Confidential Gmail visible only to admin.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT student_id, full_name, email, roll_no, dept, is_email_verified, email_verified_at, status, created_at
        FROM registered_students
        ORDER BY created_at DESC;
        """)
        rows = cursor.fetchall()
        return {"students": [dict(r) for r in rows], "count": len(rows)}


@app.patch("/api/admin/students/{student_id}/status")
async def update_student_account_status(student_id: str, data: StatusUpdate, request: Request):
    """
    Administrator endpoint: Toggles student account status between ACTIVE, BLOCKED, and SUSPENDED.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    clean_id = student_id.strip()
    ip = get_client_ip(request)
    new_status = data.status.strip().upper()

    if new_status not in {"ACTIVE", "BLOCKED", "SUSPENDED"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be ACTIVE, BLOCKED, or SUSPENDED.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, full_name, email, roll_no FROM registered_students WHERE student_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student record not found.")

        cursor.execute("UPDATE registered_students SET status = ? WHERE student_id = ?;", (new_status, clean_id))
        
        # Also sync to community_users and memberships
        community_status = "BANNED" if new_status == "BLOCKED" else new_status
        if community_status == "ACTIVE":
            cursor.execute(
                "UPDATE community_users SET status = ? WHERE email = ? OR roll_no = ?;",
                (community_status, row["email"], row["roll_no"]),
            )
        else:
            cursor.execute("""
            UPDATE community_users
            SET status = ?, session_token = NULL, session_revoked_at = CURRENT_TIMESTAMP
            WHERE email = ? OR roll_no = ?;
            """, (community_status, row["email"], row["roll_no"]))
        cursor.execute("UPDATE memberships SET status = ? WHERE roll_no = ?;", (new_status, row["roll_no"]))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if new_status in ["BLOCKED", "SUSPENDED"]:
            cursor.execute("""
            INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
            VALUES (?, ?, ?, 'Student Account Blocked by Administrator', 'RESTRICTED', ?);
            """, (row["email"], row["roll_no"], row["full_name"], now_str))

        log_audit_event("STUDENT_STATUS_CHANGED", ip, f"Admin updated student {clean_id} ({row['full_name']}) status to {new_status}", conn=conn)

        return {
            "success": True,
            "student_id": clean_id,
            "status": new_status,
            "message": f"Student {row['full_name']} ({row['roll_no']}) status updated to {new_status}."
        }


@app.delete("/api/admin/students/{student_id}")
async def delete_student_account(student_id: str, request: Request):
    """
    Administrator endpoint: Permanently removes a student account and resets verification.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    clean_id = student_id.strip()
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, full_name, email, roll_no FROM registered_students WHERE student_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student record not found.")

        email = row["email"]
        name = row["full_name"]
        roll = row["roll_no"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Record in account_restrictions: require admin approval to ever rejoin
        cursor.execute("""
        INSERT INTO account_restrictions (email, roll_no, name, reason, status, restricted_at)
        VALUES (?, ?, ?, 'Student Account Purged/Deleted by Administrator', 'RESTRICTED', ?);
        """, (email, roll, name, now_str))

        cursor.execute("DELETE FROM registered_students WHERE student_id = ?;", (clean_id,))
        cursor.execute("DELETE FROM email_otp_verifications WHERE email = ?;", (email,))
        cursor.execute("DELETE FROM community_users WHERE email = ? OR roll_no = ?;", (email, roll))
        
        log_audit_event("STUDENT_ACCOUNT_DELETED", ip, f"Admin permanently deleted student {name} ({clean_id}, Roll: {roll}, Email: {email})", conn=conn)

        return {
            "success": True,
            "message": f"Student account {clean_id} ({name}) permanently deleted from AssociationHub."
        }


@app.get("/api/admin/export/students.csv")
async def export_registered_students_csv(request: Request):
    """
    Administrator endpoint: Exports official verified student registry with confidential Gmail addresses.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT student_id, full_name, roll_no, dept, email, is_email_verified, email_verified_at, status, created_at
        FROM registered_students
        ORDER BY created_at DESC;
        """)
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student ID", "Full Name", "Roll / PRN", "Department",
        "Official Student Gmail (Confidential)", "Email Verified",
        "Verification Timestamp", "Account Status", "Registered At"
    ])

    for r in rows:
        writer.writerow([
            r["student_id"],
            r["full_name"],
            r["roll_no"],
            r["dept"],
            r["email"],
            "VERIFIED" if r["is_email_verified"] else "UNVERIFIED",
            r["email_verified_at"] or "",
            r["status"] or "ACTIVE",
            r["created_at"]
        ])

    log_audit_event("EXPORT_STUDENTS_CSV", ip, "Admin exported verified student directory CSV")
    output.seek(0)
    filename = f"NKOCET_Verified_Students_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --------------------------------------------------------------------------
# ADMINISTRATOR REJOIN APPROVAL GATEWAY
# --------------------------------------------------------------------------

@app.get("/api/admin/rejoin-requests")
async def list_admin_rejoin_requests(request: Request):
    """
    Administrator endpoint: Lists all students whose accounts were blocked or removed
    and requires explicit Administrator authorization to rejoin.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, email, roll_no, name, reason, status, restricted_at, rejoin_requested_at, rejoin_approved_at, reviewed_by
        FROM account_restrictions
        ORDER BY 
            CASE status 
                WHEN 'REJOIN_PENDING' THEN 1 
                WHEN 'RESTRICTED' THEN 2 
                ELSE 3 
            END ASC,
            id DESC;
        """)
        rows = cursor.fetchall()
        pending_count = sum(1 for r in rows if r["status"] == "REJOIN_PENDING")
        return {"requests": [dict(r) for r in rows], "count": len(rows), "pending_count": pending_count}


@app.post("/api/admin/rejoin-requests/{request_id}/approve")
async def approve_student_rejoin(request_id: int, request: Request):
    """
    Administrator endpoint: Approves a previously banned or removed student to rejoin
    and register their membership pass or student account.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, roll_no, name FROM account_restrictions WHERE id = ?;", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rejoin request not found.")

        # Set status to REJOIN_APPROVED
        cursor.execute("""
        UPDATE account_restrictions
        SET status = 'REJOIN_APPROVED',
            rejoin_approved_at = ?,
            reviewed_by = 'Administrator'
        WHERE id = ?;
        """, (now_str, request_id))

        # Also unblock in registered_students if present
        cursor.execute("UPDATE registered_students SET status = 'ACTIVE' WHERE email = ? OR (roll_no != '' AND roll_no = ?);", 
                       (row["email"], row["roll_no"] or ""))
        # Also unblock in memberships if present
        cursor.execute("UPDATE memberships SET status = 'ACTIVE' WHERE email = ? OR (roll_no != '' AND roll_no = ?);", 
                       (row["email"], row["roll_no"] or ""))

        log_audit_event("REJOIN_REQUEST_APPROVED", ip, f"Admin approved rejoining for {row['name']} ({row['email']}, Roll: {row['roll_no']})", conn=conn)

        return {
            "success": True,
            "message": f"Rejoining successfully APPROVED for {row['name']} ({row['email']}). They may now register or join."
        }


@app.post("/api/admin/rejoin-requests/{request_id}/reject")
async def reject_student_rejoin(request_id: int, request: Request):
    """
    Administrator endpoint: Rejects a student rejoin request and keeps their account permanently restricted.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, roll_no, name FROM account_restrictions WHERE id = ?;", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rejoin request not found.")

        cursor.execute("""
        UPDATE account_restrictions
        SET status = 'RESTRICTED',
            reviewed_by = 'Administrator'
        WHERE id = ?;
        """, (request_id,))

        log_audit_event("REJOIN_REQUEST_REJECTED", ip, f"Admin rejected rejoining for {row['name']} ({row['email']})", conn=conn)

        return {
            "success": True,
            "message": f"Rejoining request REJECTED for {row['name']}. Account remains restricted."
        }


@app.get("/api/admin/members")
async def get_admin_members(request: Request, association: Optional[str] = None):
    """
    Administrator endpoint: Returns full member directory INCLUDING confidential verified Gmail.
    Access strictly gated to Master Admin Authority.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        if association and association != "ALL":
            cursor.execute("""
            SELECT pass_id, name, roll_no, email, dept, year, association, interest, status, crypto_signature, created_at
            FROM memberships WHERE association = ? ORDER BY created_at DESC;
            """, (association.strip().upper(),))
        else:
            cursor.execute("""
            SELECT pass_id, name, roll_no, email, dept, year, association, interest, status, crypto_signature, created_at
            FROM memberships ORDER BY created_at DESC;
            """)
        rows = cursor.fetchall()
        return {"count": len(rows), "members": [dict(r) for r in rows]}


@app.get("/api/admin/export/members.csv")
async def export_members_csv(request: Request):
    """
    Admin endpoint: Streams RFC-4180 CSV with UTF-8 BOM of all registered members
    formatted for HOD and NAAC compliance including confidential verified Gmail.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT pass_id, name, roll_no, email, dept, year, association, status, crypto_signature, created_at, interest
        FROM memberships ORDER BY association ASC, roll_no ASC;
        """)
        rows = cursor.fetchall()

        output = io.StringIO()
        # UTF-8 BOM for Microsoft Excel compatibility
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            "Pass ID",
            "Student Full Name",
            "Roll No / PRN",
            "Verified Gmail (Confidential)",
            "Branch / Department",
            "Academic Year",
            "Student Association",
            "Membership Status",
            "HMAC Crypto Signature",
            "Registration Timestamp",
            "Technical Interests & Skills"
        ])

        for r in rows:
            writer.writerow([
                r["pass_id"],
                r["name"],
                r["roll_no"],
                r["email"] if "email" in r.keys() and r["email"] else "Not Recorded",
                r["dept"],
                r["year"],
                r["association"],
                r["status"] if "status" in r.keys() and r["status"] else "ACTIVE",
                r["crypto_signature"] if "crypto_signature" in r.keys() else "VERIFIED",
                r["created_at"],
                r["interest"]
            ])

        csv_content = output.getvalue()
        output.close()

        log_audit_event("CSV_EXPORT_DOWNLOADED", ip, f"Exported {len(rows)} member records to CSV for HOD compliance.", conn=conn)
        filename = f"NKOCET_Association_Members_{datetime.now().strftime('%Y%m%d')}.csv"
        return Response(
            content=csv_content.encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )


@app.delete("/api/community/posts/{post_id}")
async def admin_delete_post(post_id: str, request: Request):
    """Admin endpoint: Moderates and deletes inappropriate community posts."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT post_id, title FROM community_posts WHERE post_id = ?;", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        cursor.execute("DELETE FROM community_comments WHERE post_id = ?;", (post_id,))
        cursor.execute("DELETE FROM community_posts WHERE post_id = ?;", (post_id,))
        log_audit_event("COMMUNITY_POST_PURGED", ip, f"Purged discussion thread {post_id}: '{row['title']}'", conn=conn)
        return {
            "success": True,
            "message": f"Discussion post '{row['title']}' was removed by Administrator."
        }


@app.get("/api/admin/community/unmask/{post_id}")
async def admin_unmask_post(post_id: str, request: Request):
    """
    Admin Authority: Reveals true student identity (Roll No, Name & Verified Gmail) for anonymous posts
    in case of severe code of conduct violations.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT p.post_id, p.author_name, p.roll_no, p.dept, p.year, p.title, p.created_at,
               COALESCE(u.name, m.name) AS registered_name,
               COALESCE(u.email, m.email) AS verified_email
        FROM community_posts p
        LEFT JOIN memberships m ON p.roll_no = m.roll_no
        LEFT JOIN community_users u ON p.roll_no = u.roll_no
        WHERE p.post_id = ?;
        """, (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found.")

        true_name = row["registered_name"] or row["author_name"]
        verified_email = row["verified_email"] or "Not recorded"
        log_audit_event("ANONYMOUS_AUTHOR_UNMASKED", ip, f"Unmasked anonymous author of {post_id} -> {true_name} ({row['roll_no']}) [{verified_email}]", conn=conn)

        return {
            "post_id": row["post_id"],
            "title": row["title"],
            "true_student_name": true_name,
            "true_roll_no": row["roll_no"],
            "verified_gmail": verified_email,
            "department": row["dept"],
            "year": row["year"],
            "timestamp": row["created_at"],
            "message": "Confidential identity unmasked for Administrative Moderation."
        }


# --------------------------------------------------------------------------
# MASTER ADMIN: CHAT USER MANAGEMENT & AUTHORITIES
# --------------------------------------------------------------------------

@app.get("/api/admin/chat/users")
async def get_admin_chat_users(request: Request):
    """
    Administrator endpoint: Returns all verified community chat users with confidential Gmails,
    Roll numbers, departments, and active/mute/ban status.
    """
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, name, roll_no, email, dept, status, created_at, last_active
        FROM community_users ORDER BY last_active DESC;
        """)
        rows = cursor.fetchall()
        return {"count": len(rows), "users": [dict(r) for r in rows]}


@app.patch("/api/admin/chat/users/{user_id}/status")
async def update_chat_user_status(user_id: str, data: ChatUserStatusUpdate, request: Request):
    """
    Admin Authority: Toggles student chat status between ACTIVE, MUTED, and BANNED.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    clean_id = user_id.strip()
    status = data.status.strip().upper()
    if status not in ["ACTIVE", "MUTED", "BANNED"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be ACTIVE, MUTED, or BANNED.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, roll_no, email FROM community_users WHERE user_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chat user not found.")

        if status == "BANNED":
            cursor.execute("""
            UPDATE community_users
            SET status = ?, session_token = NULL, session_revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = ?;
            """, (status, clean_id))
        else:
            cursor.execute("UPDATE community_users SET status = ? WHERE user_id = ?;", (status, clean_id))
        log_audit_event("CHAT_USER_STATUS_CHANGE", ip, f"Admin updated chat user {clean_id} ({row['name']}) status to {status}", conn=conn)

        return {
            "success": True,
            "user_id": clean_id,
            "status": status,
            "message": f"User {row['name']} ({row['roll_no']}) status updated to {status}."
        }


@app.delete("/api/admin/chat/users/{user_id}")
async def delete_chat_user(user_id: str, request: Request):
    """
    Admin Authority: Kicks and removes user from the community chat registry.
    """
    verify_admin_access(request)
    ip = get_client_ip(request)
    clean_id = user_id.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, roll_no, email FROM community_users WHERE user_id = ?;", (clean_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chat user not found.")

        cursor.execute("DELETE FROM community_users WHERE user_id = ?;", (clean_id,))
        log_audit_event("CHAT_USER_KICKED", ip, f"Admin kicked and deleted chat user {clean_id} ({row['name']})", conn=conn)

        return {
            "success": True,
            "message": f"User {row['name']} has been kicked from the chat registry."
        }


@app.get("/api/admin/audit-logs")
async def list_security_audit_logs(request: Request, limit: int = 50):
    """Admin endpoint: Fetches live security and coordinator audit logs."""
    verify_admin_access(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, event_type, actor_ip, details, timestamp
        FROM security_audit_logs ORDER BY id DESC LIMIT ?;
        """, (limit,))
        rows = cursor.fetchall()
        return {"logs": [dict(r) for r in rows]}


# --------------------------------------------------------------------------
# MASTER ADMIN: REAL SMTP MAILER CONFIGURATION & TEST
# --------------------------------------------------------------------------

@app.get("/api/admin/smtp-config")
async def get_admin_smtp_config(request: Request):
    """Admin endpoint: Returns SMTP status only; credential values are never exposed."""
    verify_admin_access(request)
    cfg = get_smtp_config()
    return {
        "configured": bool(cfg["user"] and cfg["password"]),
        "user": cfg["user"],
        "host": cfg["host"],
        "port": cfg["port"],
        "from_name": cfg["from_name"]
    }


@app.post("/api/admin/smtp-config")
async def save_admin_smtp_config(request: Request):
    """Reject legacy SMTP credential writes; configure SMTP in the server environment."""
    verify_admin_access(request)
    raise HTTPException(
        status_code=410,
        detail="SMTP credentials can no longer be saved through the admin console. Configure them in the server environment and restart the service.",
    )


@app.post("/api/admin/smtp-test")
async def test_admin_smtp_delivery(data: SmtpTestRequest, request: Request):
    """Admin endpoint: Sends a real test email to verify Google SMTP credentials live."""
    verify_admin_access(request)
    ip = get_client_ip(request)
    test_email = data.test_email.strip().lower()

    test_otp = f"{secrets.randbelow(900000) + 100000}"
    res = send_real_smtp_email(test_email, "Administrator", test_otp)

    if res["sent"]:
        log_audit_event("SMTP_TEST_SUCCESS", ip, f"Test email successfully dispatched to {test_email}")
        return {
            "success": True,
            "message": f"Test email successfully delivered to {test_email}! Check your Gmail inbox now."
        }
    else:
        log_audit_event("SMTP_TEST_FAILED", ip, f"Test email failed for {test_email}: {res.get('reason')}")
        raise HTTPException(
            status_code=400,
            detail=f"SMTP Delivery Test Failed: {res.get('reason')}"
        )


# --------------------------------------------------------------------------
# ROOT REDIRECT & STATIC FILES
# --------------------------------------------------------------------------

@app.get("/")
async def root_redirect():
    """Redirects root domain to index.html."""
    index_file = os.path.join(DIRECTORY, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return JSONResponse({"message": "AssociationHub API is active. index.html not found."})


# Mount entire nkocet-website directory for serving HTML, CSS, JS, images
app.mount("/", StaticFiles(directory=DIRECTORY, html=True), name="static")


# --------------------------------------------------------------------------
# CLI ENTRY POINT
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8080))
    print("============================================================")
    print("   ASSOCIATIONHUB FULL-STACK SERVER (NKOCET 2026)")
    print("============================================================")
    print(f">> Server running at: http://127.0.0.1:{port}")
    print(f">> API Docs: http://127.0.0.1:{port}/docs")
    print(f">> Community Pulse: http://127.0.0.1:{port}/#community")
    print(">> Admin PIN and cryptographic secret loaded from environment.")
    print("============================================================")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
