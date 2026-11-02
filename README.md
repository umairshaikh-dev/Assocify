# 🎓 AssociationHub — NK Orchid College of Engineering & Technology (NKOCET)

> **Enterprise Full-Stack Collegiate Engagement & Digital Access Control Gateway**  
> *Developed for N.K. Orchid College of Engineering & Technology, Solapur (Autonomous Institute)*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite3](https://img.shields.io/badge/SQLite-Ledger_Ready-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Status](https://img.shields.io/badge/Audit_Status-100%25_Green-brightgreen.svg)]()

---

## 🚀 Overview

**AssociationHub** is an enterprise-grade collegiate engagement platform and digital access control gateway built for **N.K. Orchid College of Engineering & Technology (NKOCET)**. It unifies all 6 engineering departments under a secure cryptographic system, providing junior students with interactive orientation pathways, verified digital membership passes with 3D smart-card flipping, real-time Gmail OTP identity verification, collegiate event calendars, and public gate check-in terminals.

---

## 🌟 Core System Modules

1. **Digital Membership Pass Generator (`/api/memberships`)**:
   - Issues verified digital passes with unique IDs (e.g. `NKOCET-2026-CSESA-A1B2C3`).
   - Generates dynamic, high-density Base64 QR codes signed with HMAC-SHA256 cryptographic hashes.
   - Interactive 3D flip card (front credentials, hologram, and back constitution/emergency contacts).
   - 1-click Print, PDF download, and local device persistence (`localStorage`).

2. **Gate Access Control & Live Camera Scanner (`/verify.html`)**:
   - Real-time verification terminal for campus security, event gates, and lab access.
   - **Interactive Live Camera Scanner**: Auto-detects QR passes in real time at 60 fps via native `BarcodeDetector` / `getUserMedia`.
   - **QR Image Uploader**: Drag-and-drop or upload pass screenshots for instant verification.
   - Audio feedback (synthesized Web Audio chimes for verified, alert, and check-in celebration).
   - Gatekeeper check-in logging (`gate_checkins` table in SQLite).

3. **Master Admin Console Suite (PIN supplied by server environment)**:
   - **Member Directory**: Search, filter by association, activate, suspend, or revoke passes.
   - **Revoke & Delete Pass**: Permanent SQLite record purge, device cache clearing, and restriction logging with Admin PIN modal.
   - **Campus Events Calendar**: Publish and delete hackathons, robotics challenges, and technical workshops across departments.
   - **Executive Analytics**: Real-time KPI telemetry (Registered Members, Gate Check-Ins, Discussions, Active Events, Ledger Health) and dynamic enrollment charts.
   - **Rejoin Approvals Queue**: Automated gateway preventing blocked/removed students from rejoining without explicit admin authorization.
   - **Security Audit Logs**: Timestamped ledger tracking all registrations, status changes, and troll violations.
   - **Real SMTP Gateway**: View environment-based mailer status and send test emails from the UI.
   - **1-Click CSV Exports**: Download HOD & NAAC compliance reports for students and active members.

4. **Campus Pulse Community Chat (`#community`)**:
   - Gated student discussion boards gated by Gmail OTP verification.
   - Upvotes ("Helpful"), threaded replies, and anonymous publishing mode.
   - **Campus Anti-Troll Shield**: Blocks profanity, toxic keywords, external scam links, and repetitive character floods.
   - Admin post unmasking and moderation deletion.

---

## 🎨 Department Color Identities

| Association | Engineering Department | Primary Accent |
| :--- | :--- | :--- |
| **CSESA** | Computer Science & Engineering | **Cyber Blue (`#1687FF`)** |
| **MESA** | Mechanical Engineering | **Industrial Orange (`#FF8A24`)** |
| **EESA** | Electrical Engineering | **Electric Emerald (`#19D68C`)** |
| **CESA** | Civil Engineering | **Architectural Violet (`#A855F7`)** |
| **AEXS** | Electronics & Telecommunication | **Signal Crimson (`#FF416C`)** |
| **AIESA** | AI & Data Science | **Neural Cyan (`#00D9E8`)** |

---

## 📂 Repository File Tree

```text
nkocet-website/
├── index.html                  # Main Portal Homepage with Live Telemetry & Modals
├── verify.html                 # Gate Verification Portal with Live Camera & QR Scanner
├── aids.html                   # AI & Data Science Association (AIESA) Sub-Portal
├── civil.html                  # Civil Engineering Association (CESA) Sub-Portal
├── entc.html                   # Electronics & Telecom Association (AEXS) Sub-Portal
├── esa.html                    # Electrical Engineering Association (EESA) Sub-Portal
├── cep-cesa.html               # Computer Science Association (CSESA) Sub-Portal
├── cep-mesa.html               # Mechanical Engineering Association (MESA) Sub-Portal
├── cep-about us.html           # Project Vision, Academic Background & Team Dossier
│
├── css.css                     # Unified Dark Theme Glassmorphism Design System
├── api-config.js               # Shared configurable backend API base URL
├── main.js                     # Full-Stack Client Engine & Admin Suite
├── server.py                   # FastAPI Enterprise Backend (48 Endpoints)
├── associationhub.db           # Local SQLite ledger (generated on startup; ignored by Git)
│
├── tests/
│   ├── test_membership_otp.py  # OTP and membership security regressions
│   └── test_server_configuration.py # Server configuration security regressions
│
├── .env.example                # Placeholder-only server configuration template
├── .gitignore                  # GitHub Exclusion Rules (Protects passwords & temp files)
├── requirements.txt            # Python Package Dependencies
└── README.md                   # Complete System Documentation
```

---

## ⚡ Quick Start & Local Setup

### 1. Prerequisites
- Python 3.10+ installed
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 2. Clone Repository
```bash
git clone https://github.com/your-username/nkocet-website.git
cd nkocet-website
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Server Environment
The backend will not start until unique administrator and cryptographic secrets are configured. Copy the example:
```bash
cp .env.example .env
```
Replace both required placeholders in `.env` with independently generated values. For example, run these commands separately and copy their output into the matching variables:
```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
python -c "import secrets; print(secrets.token_hex(32))"
```
`ADMIN_SECRET_PIN` must be at least 16 characters; `NKOCET_CRYPTO_SECRET` must be at least 64 characters and must differ from the PIN. Never commit or share `.env`.

Real Gmail OTP delivery is optional. To enable it, set both `SMTP_USER` and `SMTP_PASSWORD` in `.env` to the sender account and its Google App Password. SMTP settings are no longer stored in SQLite or accepted by the admin UI. Restart the backend after changing environment values. If SMTP is not configured, OTP delivery reports an explicit configuration error rather than simulating email.

The repository history contains a previously committed environment file and distribution archive with configuration data. The current archive and Git index no longer include those files, but removing them does not erase historical copies; treat those credentials as compromised, rotate them out of band, and review repository access. Rotating `NKOCET_CRYPTO_SECRET` invalidates existing admin sessions and may invalidate signatures on previously issued passes, so plan pass re-signing or reissuance before enabling the new key in production.

### 5. Launch Full-Stack Server
```bash
python server.py 8080
```

### 6. Access Portal
- **Main Portal**: [http://127.0.0.1:8080](http://127.0.0.1:8080)
- **Gate Check-In & Scanner**: [http://127.0.0.1:8080/verify.html](http://127.0.0.1:8080/verify.html)
- **Interactive OpenAPI Docs**: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)
- **Master Admin PIN**: the value configured in the server's `ADMIN_SECRET_PIN` environment variable; there is no default PIN.

## Render Deployment

The backend supports Python 3.10+ and Uvicorn is included in `requirements.txt`.
Create a Render Web Service with:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
- **Environment:** `ADMIN_SECRET_PIN`, `NKOCET_CRYPTO_SECRET`, and `PUBLIC_APP_URL` are required for pass issuance; set SMTP variables only as a complete `SMTP_USER` / `SMTP_PASSWORD` pair if real OTP email delivery is needed. Render supplies `PORT`.

The GitHub Pages site and backend are separate services. Before publishing, set
`window.ASSOCIATIONHUB_API_BASE_URL` in `api-config.js` to the actual HTTPS URL
Render assigns to the backend. The checked-in value is intentionally empty; on
GitHub Pages, API calls show a configuration error rather than silently calling
the Pages origin. Local development continues to use `http://127.0.0.1:8080`.
Set `PUBLIC_APP_URL` on the backend to the public GitHub Pages site root that
serves `verify.html` (include the repository path for a project site). It must
be HTTPS and cannot point to a localhost or private-network address. The backend
fails pass issuance visibly when this URL is unset rather than generating a
QR code that points at an internal host.
The backend allows browser CORS requests only from
`https://affanchoudhari2006-lang.github.io`.

### SQLite persistence and migration

SQLite remains suitable for a single Render instance when its database is on a
Render Persistent Disk. Mount the disk at `/var/data` and set
`DATABASE_PATH=/var/data/associationhub.db`. Without a persistent disk, the
default database beside `server.py` is ephemeral and may be lost on restart or
redeploy. This implementation uses a local SQLite file and is not configured
for multiple concurrent service instances. PostgreSQL is the better choice if
the service must scale horizontally, use multiple writers/instances, or avoid
single-disk availability limits; adopting it would require a separate database
adapter/migration and is not part of this deployment preparation.

To migrate an existing SQLite ledger safely, stop application writes and make a
consistent SQLite backup using the SQLite backup API (do not copy a live
`.db` file by itself while WAL writes may be active). Transfer that backup to
the mounted disk through a secure operator-controlled channel, preserve the
source backup, and point `DATABASE_PATH` at the transferred file before the
first production start. Do not upload a database to GitHub or include it in a
release archive. Startup uses additive schema creation/migrations and
`INSERT OR IGNORE` for seed rows; existing membership signatures are not
replaced. Validate record counts and a sample of each required table against
the backup before allowing writes. The application does not copy an existing
repository/local database to Render automatically.

Example local backup to a new destination file (run after stopping writes; do
not use an existing target file):

```python
import sqlite3
source = sqlite3.connect("associationhub.db")
backup = sqlite3.connect("associationhub-backup.db")
source.backup(backup)
backup.close()
source.close()
```

---

## 🧪 Automated Testing & Verification

Run the automated security regression tests:

```bash
python -m unittest discover -s tests -v
```

---

## 👥 Project Team & Authors

Developed as part of the **College Engagement Project (CEP)**, 2nd Year B.Tech, NKOCET Solapur:

* **Affan Choudhari** — Project Lead & Backend Systems Architect (Roll: C-62)
* **Suyash Gote** — UI/UX Lead & Design Systems Engineer (Roll: C-64)
* **Umair Shaikh** — Research & Association Documentation Lead (Roll: C-54)
* **Moin Shaikh** — Systems & Infrastructure Lead (Roll: C-67)
* **Sushil Habib** — Verification & Quality Assurance (Roll: C-58)
* **Siddeshwar Nagansure** — Technical Documentation (Roll: C-61)

---

## 📄 License

This project is developed for academic, collegiate, and access control purposes at **N.K. Orchid College of Engineering & Technology (NKOCET)**, Solapur.
#   A s s o c i f y  
 