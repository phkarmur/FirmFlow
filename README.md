# FirmFlow — CA Practice Management System

> Production-ready practice management system designed specifically for Indian Chartered Accountant (CA), Company Secretary (CS), and tax practitioner firms (2–50 staff).

---

## 🚀 Key Highlights & Phase 1 Capabilities

- **Practice Command Center**: Real-time tile metrics (Pending, Overdue, Due Today, Due in 7 Days, High Priority, Blocked with Issues, Completed FY, Unbilled).
- **Jira-Style Unassigned Task Pool (§5.4 A3)**: Staff can browse unassigned compliance tasks and self-assign ("Pick up").
- **Statutory Service Tree & Due Dates**:
  - GST: GSTR-3B (monthly, 20th), GSTR-1 (monthly, 11th), GSTR-9 (yearly), GST Registrations.
  - Income Tax: ITR Individual (AY mode, 31 Jul), ITR Audit (31 Oct), Tax Audit 3CA/3CB-3CD (30 Sep), Advance Tax.
  - TDS: 24Q, 26Q quarterly returns.
  - ROC / MCA: AOC-4, MGT-7, DIR-3 KYC.
  - Statutory & Internal Audit, Monthly Bookkeeping.
- **Stage Milestones & Mandatory Checklists**: Step-by-step pipeline advancing with auto-resolution of matching blocker issues.
- **Client & Security Standards**:
  - PAN encrypted at rest via **AES-256-GCM** with masked display (`XXXXX1234X`).
  - Strict PAN format & GSTIN checksum validators.
  - Admin PAN reveal feature with audit-logged reasons.
- **Collaborative Commenting & Access Control (§5.7 M1)**: Mentioning active staff members (`@name`) automatically adds them as collaborators to the task.
- **Time Logging (§3.2)**: 24-hour (1 day) edit lock window for staff time entries.
- **Structured JSON Logging & Audit Trails**: Every state change, assignment, and health check is tracked with latency and request IDs.

---

## 🛠 Tech Stack

| Component | Technology | License |
|---|---|---|
| **Backend API** | Python 3.12 / 3.15 + Django 5 + Django REST Framework | Free / Open Source (BSD) |
| **Frontend SPA** | React 18 + Vite + TypeScript + Tailwind CSS + Lucide Icons | Free / Open Source (MIT) |
| **Database** | PostgreSQL 16 | Free / Open Source |
| **Task Queue & Scheduler** | Celery 5 + Redis 7 + Django Celery Beat | Free / Open Source (BSD) |
| **Reverse Proxy** | Nginx Alpine | Free / Open Source |
| **Dev Email Testing** | Mailpit | Free / Open Source |

---

## ⚡ Quick Start

### Option A: Running with Docker Compose (Recommended)

1. Clone or navigate to the repository:
   ```bash
   cd FirmFlow
   ```
2. Start the full stack (API, Frontend, Postgres, Redis, Worker, Beat, Mailpit, Nginx):
   ```bash
   cd deploy
   docker compose up -d --build
   ```
3. Open your browser:
   - **FirmFlow Web App**: [http://localhost](http://localhost)
   - **Mailpit Email Inbox**: [http://localhost:8025](http://localhost:8025)
   - **Interactive API Docs (Swagger)**: [http://localhost/api/docs/](http://localhost/api/docs/)

---

### Option B: Local Development

#### 1. Backend (Django + SQLite/Postgres)
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_firmflow
python manage.py runserver 127.0.0.1:8000
```

#### 2. Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173).

---

## 🔑 Seeded Demo Credentials

| Role | Email | Password | Details |
|---|---|---|---|
| **Superadmin (Managing Partner)** | `admin@shahca.com` | `Admin@123456` | Full administrative control & firm settings |
| **Admin (Senior Associate)** | `amit.kumar@shahca.com` | `Staff@123456` | Task management, assignment, reviews |
| **Staff (Article Trainee)** | `priya.verma@shahca.com` | `Staff@123456` | My Tasks, self-pickup, time logging |

---

## 🧪 Running Tests

To run the automated test suite (verifying state machine rules, crypto, validators, and endpoints):
```bash
backend/venv/bin/python backend/manage.py test apps.common apps.tasks
```
