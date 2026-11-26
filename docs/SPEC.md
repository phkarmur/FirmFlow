# FirmFlow — CA Practice Management System
## Build Specification (Phase 1 Focus)

| Item | Value |
|---|---|
| Document | Build specification, Phase 1 implementation |
| Version | 1.0 (decisions locked) |
| Date | 2026-11-09 |
| App name | FirmFlow |
| Target users | Indian CA / CS / tax practitioner firms, 2–50 staff |

---

## 0. Locked Decisions

| # | Decision | Chosen Standard | Details |
|---|---|---|---|
| D1 | App name | FirmFlow | Confirmed |
| D2 | Backend stack | Python (Django 5 + Django REST Framework) | 100% Free, open source, robust ORM, admin panel, session & auth security |
| D3 | Frontend | React 18/19 + Vite + TypeScript + Tailwind CSS | 100% Free, modern industry standard, responsive component library |
| D4 | Database | PostgreSQL 16 | Free, enterprise-grade, JSONB, row-level security |
| D5 | Auth | Session cookies + CSRF protection | Web industry standard, secure against XSS/token theft. JWT reserved for mobile apps |
| D6 | Deployment | Docker Compose | Multi-container setup (app, worker, beat, postgres, redis, nginx, mailpit for dev) |
| D7 | Multi-tenant? | Single firm per install with `firm_id` on all tables | Free, clean isolation, future-proof for SaaS multi-tenancy |
| D8 | Financial year rule | Configurable per firm (Default: India Apr–Mar) | Indian financial year FY (Apr–Mar) and AY (FY+1) |
| D9 | Email provider | Standard SMTP (Works with Gmail/Google Workspace/M365/SES/Resend) | Dev uses Mailpit (free local web inbox) |
| D10 | File storage | Local disk storage with Django storage abstraction | 100% free; drop-in swap to S3/MinIO later without code changes |

### Locked Business Rule Decisions:
- **§5.4 A3 (Task Pickup / Self-assign)**: **Enabled**. Staff can browse the Unassigned Task Pool and self-assign tasks to themselves (like Jira). Logged in `TaskAssignmentLog(trigger='pickup')`.
- **§5.7 M1 (@Mentions & Access)**: **Industry Standard Collaboration Model** (Linear/Jira style). When a task collaborator `@mentions` an active staff member in a comment, that staff member is automatically added to `TaskMember` (if not already assigned/leader/manager), granting them view and comment access, with an audit log entry `trigger='mention'`.
- **§2.2 (Staff Task Creation & Completion)**:
  - `staff_can_create_task`: Configurable setting on `Firm` (Default `False`, Admin can enable firm-wide or per-user).
  - `staff_can_complete`: Configurable setting on `Firm` (Default `True` for Assigned User or Task Leader, provided all mandatory todos/milestones are done and no blocking issues exist).
- **§3.2 (Time Log Edit Window)**: **1 day (24 hours)**. The creator can edit or delete their time log within 24 hours. After 24 hours, editing requires Admin or Superadmin role.

---

## 1. Scope

### 1.1 Phase 1 — "Get the firm started"
1. Admin panel (partner / superadmin / admin)
2. User panel (employee)
3. Clients & Contacts (PAN/GSTIN validation and encryption)
4. Service tree + task types + checklists + milestones
5. Create, assign, re-assign, and self-pickup tasks (single and bulk)
6. Track tasks (status, due dates, pending issues, comments, attachments, time logs)
7. Dashboards and 16 core reports
8. Notifications (in-app + email)
9. Daily email digest (07:00 AM)
10. Audit log and structured logging

### 1.2 Phase 2 (Future)
- Invoices, receipts, credit/debit notes, outstanding fees, auto follow-up
- Inward / Outward document physical register
- Billed / Free / Deleted end-of-life enforcement on completed tasks
- Fixed assignment rules per milestone

### 1.3 Phase 3 (Future)
- Client login portal and client-facing app
- Timesheet costing, job profitability, staff cost rates
- Attendance (geo-tagged), leave, expenses, disbursements
- DSC (digital signature token) register with expiry alerts

### 1.4 Later
- GST return status check (GSTN portal), ITR status check via APIs
- WhatsApp / SMS messaging portal
- Multi-branch, multi-currency
- Mobile apps (iOS / Android)

### 1.5 Explicitly NOT in Scope
- Bookkeeping / general ledger
- Filing returns directly with government tax portals
- Tax computation calculation engines

---

## 2. Actors and Roles

| Role | Who | Can do |
|---|---|---|
| Superadmin | Firm owner / managing partner | Everything. Firm settings. Create admins. Delete anything. See all branches. |
| Admin | Partner / senior manager | All task, client, service, user operations. Cannot change firm-level settings or delete the superadmin. |
| Staff | Employee, article, paid assistant | Sees only tasks where they have a role (assigned / leader / manager / member) or unassigned pool tasks. Can update those tasks. |
| System | Scheduler / worker | Creates bulk tasks, sends digests, auto-assigns. All its actions are logged with actor = `system`. |

### 2.1 Task Roles
| Task role | Meaning |
|---|---|
| Assigned user | The one doing the work right now. Exactly one. (Can be unassigned in the pool). |
| Task leader | Senior CA/manager who reviews and signs off. Zero or one. |
| Task manager | Oversees delivery and client contact. Zero or one. |
| Members | Others collaborating, mentioned, or posting time logs. Zero or many. |

---

## 3. Data Model Entities

- `Firm`, `Branch`, `User`, `UserBranch`
- `Client`, `ClientGroup`, `ClientContact`
- `ServiceCategory`, `Service`, `TaskType`, `TaskTypeTodoTemplate`, `Milestone`, `PendingIssueLabel`
- `FinancialYear`, `Period`
- `Task`, `TaskMember`, `TaskMilestoneProgress`, `TaskTodo`, `TaskIssue`, `TaskComment`, `TaskAttachment`, `TaskTimeLog`, `TaskAssignmentLog`, `TaskStatusLog`
- `BulkBatch`, `BulkBatchRun`, `BulkBatchRunItem`
- `Notification`, `NotificationPreference`
- `PersonalTodo`, `StickyNote`
- `AuditLog`

---

## 4. Security & Privacy
- PAN at rest: AES-256-GCM encrypted, key in `.env`, masked on display (`XXXXX1234X`).
- Passwords: Argon2id.
- Rate limiting on auth endpoints.
- CSRF protection and strict CORS.
- Structured JSON logging with `request_id`, user, duration, action, and outcome.
- Audit log is append-only.
