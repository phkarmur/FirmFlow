# Changelog

## Unreleased — Phase C, part 2 (operations)

Run `python manage.py migrate` (new migration `common.0002_auditlog_append_only`; it changes nothing on SQLite).
See `docs/OPERATIONS.md`.

### Dates and numbers
- All screens use Settings > Date format (DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD) and show times in the firm time
  zone (12-hour clock). Report numbers use Indian grouping (12,34,567). One helper: `frontend/src/utils/format.ts`.
  Console: `[format] settings {...}`.

### Audit log append-only
- Model, queryset and admin cannot change or delete entries (`AuditLogAppendOnly`). PostgreSQL triggers refuse
  UPDATE / DELETE for every client. Checked on PostgreSQL 16: migrate, down-migrate, re-migrate, full test suite.
- The audit IP uses X-Forwarded-For only when `TRUST_X_FORWARDED_FOR` is on; a bad value is stored as empty
  instead of causing a database error.

### Errors on screen
- Clients list, team list, notifications, dashboard calendar and upcoming tasks, create-task lists, client
  summary, batch client search and task-detail lists now show a message (and "Try again" where useful)
  instead of an empty screen with the error only in the browser console.

### Backups, health, CI
- `backup_firmflow`, `restore_firmflow --verify` (restore drill), `restore_firmflow --yes`. SQLite and
  PostgreSQL. Optional daily backup (`BACKUP_DAILY=true`, Celery beat 01:30). Logs `backup.*`, `restore.*`.
- `/healthz` also checks attachment storage and Redis; error details only with DEBUG; result logged (`healthz`).
- GitHub Actions CI (`.github/workflows/ci.yml`).

## Phase C, part 1 (sign-in security)

Run `python manage.py migrate` (new migration `accounts.0004_security_phase_c`).

### Sign-in protection
- 10 failed sign-ins for one e-mail in 15 minutes -> that e-mail is locked for the rest of the window (HTTP 429).
  50 failures from one IP -> that IP is locked. Same answer for unknown e-mails. A good sign-in clears the count.
  Settings: `LOGIN_MAX_FAILURES`, `LOGIN_MAX_FAILURES_PER_IP`, `LOGIN_LOCKOUT_MINUTES`, `TRUST_X_FORWARDED_FOR`.
- Logs: `auth.login` with `result` = ok / error (with `failures_in_window`) / locked / denied.

### Passwords
- "Forgot password?" on the sign-in page: e-mail link, one time, 60 minutes (`PASSWORD_RESET_TIMEOUT_MINUTES`),
  max 5 requests per e-mail per hour. Page `/reset-password`. Logs: `auth.password_reset.request` (sent / error /
  no_account / throttled), `auth.password_reset.confirm`.
- Team > "Reset password" (admin): makes a random temporary password, shown one time. The person is signed out
  everywhere and must choose a new password at the next sign-in (`User.must_change_password`; the API refuses other
  calls with code `password_change_required` until then).
- Change password: the new password must be different; other devices are signed out.

### Sessions
- A sign-in lasts 12 hours (`SESSION_HOURS`). Profile > "Sign out all other devices".

### Production safety (only when `DEBUG` is off)
- The server does not start when `SECRET_KEY` or `PAN_ENCRYPTION_KEY` is missing or is a known example value.
- Secure cookies on by default (`SECURE_COOKIES`), HSTS opt-in (`HSTS_SECONDS`), `USE_X_FORWARDED_PROTO` for nginx.
- Demo sign-in buttons show only in the development build (`npm run dev`).

### Tables and reports
- Every table: drag the vertical bar at the right edge of a column header to change the width; double-click it to
  reset. Widths are kept per page in this browser. Console: `[colresize] ...`.
- Audit log: "Details" (JSON) column removed; new "Who" filter (`?actor=<user id>` or `?actor=system`).
  The CSV export still has the old / new values.

### Fixes
- Dialogs were 24 px lower than the top of the screen on pages with vertical spacing (the top bar showed above
  the dark background). All full-screen dialogs now ignore that spacing.

## Phase B2 (power use + reports)

### Task list
- Bulk bar (admins): assign, priority, due date, delete for up to 500 selected tasks
  (`POST /api/v1/tasks/bulk_action/`). Each change goes through `TaskService` (logs + notifications).
- Export of the filtered list: CSV and Excel (`GET /api/v1/tasks/export/?format_type=csv|xlsx`), same
  visibility rules as the list.
- More filters: service, status (several), due from / to.
- Short cells (task number, period, due date, status) stay on one line.

### Service catalog
- Tree editor: services, task types, due-rule editor with checks, milestone / to-do reorder, labels tab.

### Clients
- Client detail dialog with summary (`GET /api/v1/clients/<id>/summary/`), client groups dialog.

### Bulk & Recurring page (`/batches`)
- Preview, commit, run history, next run date, period offset (previous / current period).

### Reports
- New: service x staff grid, issues, performers, audit log (paged, CSV).
- Fix: audit log action filter showed duplicate actions (React duplicate-key warning). The query now
  orders by `action` before `distinct()`.

### Layout
- Phone / tablet (< 1024 px): the sidebar is a drawer, opened by the menu button in the top bar. It closes
  on navigation, backdrop click or Escape. Browser console shows `[sidebar] mobile drawer opened`.
- Removed Tailwind classes that do not exist in Tailwind 3 (`shadow-xs`, `shadow-2xs` -> `shadow-sm`,
  `z-60` -> `z-[60]`).

## Phase B1 (daily use)

### Notifications (spec §7)
- `apps/notifications/service.py: notify()` — in-app always; e-mail per user preference, sent after commit
  (`NOTIFY_EMAIL_ASYNC=true` sends with Celery; default sends in the web process). Actor is never notified.
- Events: assigned, re-assigned away, re-assigned (to the leader), role given (leader/manager/member),
  comment (all roles except author; mentioned people get "mentioned"), issue raised / resolved,
  milestone done, completed, deleted, batch finished.
- Daily 08:00 "due today" / "overdue" summary: one notification per user (not per task), no repeat on the
  same day. Command: `python manage.py send_due_reminders`.
- `Notification.link` (migration `notifications.0002`) for summary notifications.
- Digest respects `digest_enabled`.

### Attachments (spec §5.8)
- Upload / download / remove on the task. Type from file content (magic bytes + Office/ZIP structure),
  must match the extension. Size limit `Firm.max_upload_mb` (default 25, Settings). Duplicate (sha256)
  -> 409 warning, "Upload anyway" keeps both.
- Stored in `PRIVATE_MEDIA_ROOT` (not public), random name; download only through
  `/api/v1/tasks/<id>/attachments/<att>/download/` with a role on the task. Soft delete.

### Task detail (rewritten)
- Buttons follow `my_permissions`: Mark completed, Move to…, Assign to me, Edit, Re-assign, Reopen, Delete,
  Print / PDF. Members can be added / removed. New Files and History tabs. Allowed status moves only.

### Users
- Edit user dialog. Deactivate = forced "move open tasks" step (preview, then move, then deactivate).
- "Move tasks" from user A to user B (`POST /api/v1/accounts/users/<id>/move_tasks/`).
- Profile page (`/profile`, click your name): name, phone, e-mail preferences, change password.

### Fixes
- Task import "Download template" link pointed to a missing URL.

## Compliance calendar, logo, dashboard clean-up

- Dashboard: removed the "Unassigned Task Pool" banner (the Unassigned Pool tile stays).
- Compliance calendar is now data (`ComplianceEvent`, migration `services.0002` adds the 9 starter
  items to every firm). Admin+ add / edit / delete / enable / disable it in Settings.
  API: `/api/v1/services/compliance-calendar/` (`?active=true` = dashboard list, sorted by next due).
- Dashboard cards: orange during the warning days before the due day (default 2), red on the due day.
  "Today" = firm timezone. A day past the month end uses the last day (31 -> 30 Sep).
- Firm logo: `POST/DELETE /api/v1/accounts/firm/logo/` (Superadmin, PNG/JPEG/WEBP <= 1 MB,
  checked with Pillow, random file name). Shown in the top bar. `Pillow` added to requirements.
- Vite dev server proxies `/media` to Django.

## Settings page + per-user task creation

- New Settings page (`/settings`): Superadmin edits, Admin views. Firm name, legal name,
  staff can create / complete / pick up tasks, long-due days, timezone, FY start month
  (locked once tasks exist), date format. Server validates every value.
- New field `User.can_create_tasks` (migration `accounts.0002`): null = follow firm setting,
  true = allow, false = block. Admins can always create tasks.
  Set on the Team page ("Can create tasks" column, Admin+).
- `/auth/me` and the users API return `effective_can_create_tasks`; the UI shows or hides
  New Task / Create Task with it. Task create and the client picker use the same rule.

## Phase A (permissions + confirmed bugs)

### Security / permissions
- One task permission module (`apps/tasks/permissions.py`) used by views and the service layer.
- Task PATCH accepts only title, description, priority, due_date, start_date, and requires `version`.
  Status, roles and billing can no longer be changed through PATCH.
- Re-assign: Admin+, or the leader/manager of the task. Status change: Admin+ or assigned/leader/manager.
  Complete as staff: `firm.staff_can_complete` + assigned or leader. Milestones honour `can_be_completed_by`.
- Deleted tasks are final (no restore). Staff never see deleted tasks.
- Staff: read-only on clients (only clients of their own tasks), service tree and issue labels.
- Firm settings: Superadmin only. `fy_start_month` locked once tasks exist.
- Admin cannot create / edit / promote a Superadmin. Users cannot be hard-deleted (deactivate only).
- Time-log list: staff see only their own logs. Report `?user_id=` for another user → 403.

### Bugs fixed
- Dashboard tiles showed 0 (task query with `status=a,b` returned 400). Comma status filter now works.
- Every dashboard tile and the list it opens use the same server rule (`?tile=<key>`).
- "Today" uses the firm timezone (IST) instead of the UTC date.
- Due dates are calculated from the FY / period (ITR, GSTR-9, tax audit) and support quarterly
  date tables (`per_period_sequence`, used for TDS and advance tax). Day 31 is no longer cut to 28.
- FYs are generated up to next year automatically (daily job + seed).
- GSTIN checksum is now checked; GSTIN is stored in upper case.
- Full-PAN search and duplicate check use a keyed hash (`Client.pan_hash`, migration `clients.0002`).
- Bad ids / input give 400/404 instead of 500 (milestone, todo, issue, re-assign, time log, bulk).
- Task list, client list and create-task dropdowns use server paging and search.
- Global search box works (Enter); the `/` shortcut no longer blocks typing `/` in fields.

### New
- Recurring batches: `schedule.period_offset` = -1 (previous period, default) or 0 (current period).
- `GET /api/v1/periods/periods/suggest/?task_type=<id>&offset=-1` — suggested FY + period.
- Structured JSON logs (`apps/common/logging.py`) for every write path, job and permission denial.
- Phase A regression tests: `apps/tasks/tests_phase_a.py`.
