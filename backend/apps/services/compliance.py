"""Compliance calendar helpers: next due date, colour state, readable due text, defaults."""
import calendar
from datetime import date, timedelta

MONTH_SHORT = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Starter list (same items the dashboard showed before). Firms can change everything.
DEFAULT_EVENTS = [
    ('TDS-281', 'TDS / TCS Challan 281', 7, [], 'Deductors', 'Monthly deposit of tax deducted at source to Govt'),
    ('GSTR-1', 'GSTR-1 (Outward Supplies)', 11, [], 'Regular Taxpayers', 'Monthly statement of outward supplies / sales'),
    ('GSTR-3B', 'GSTR-3B (Monthly Return)', 20, [], 'Turnover > 5Cr / Monthly', 'Self-assessed summary return & ITC discharge'),
    ('IT-ADV', 'Advance Tax Installment', 15, [3, 6, 9, 12], 'Assessees > ₹10k tax', 'Quarterly statutory advance income tax payment'),
    ('ITR-REG', 'ITR Filing (Non-Audit)', 31, [7], 'Individuals / Firms', 'Annual Income Tax Return for non-audit entities'),
    ('TAR-44AB', 'Tax Audit Report u/s 44AB', 30, [9], 'Audit Assessees', 'Form 3CA / 3CB & 3CD statement submission'),
    ('ROC-AOC4', 'MCA AOC-4 (Financials)', 30, [10], 'All Companies', 'Filing of audited balance sheet & P&L with ROC'),
    ('ROC-MGT7', 'MCA MGT-7 (Annual Return)', 29, [11], 'All Companies', 'Annual Return filing under Companies Act, 2013'),
    ('GSTR-9', 'GSTR-9 & 9C Reconciliation', 31, [12], 'Turnover > 2Cr', 'Annual GST return and self-certified reconciliation'),
]


def ensure_default_events(firm, model=None):
    """Create the starter list for a firm that has no events yet. Returns the number created."""
    if model is None:
        from apps.services.models import ComplianceEvent as model
    if model.objects.filter(firm=firm).exists():
        return 0
    model.objects.bulk_create([
        model(firm=firm, code=c, title=t, due_day=d, due_months=m, scope=s, description=desc, sort_order=i)
        for i, (c, t, d, m, s, desc) in enumerate(DEFAULT_EVENTS)
    ])
    return len(DEFAULT_EVENTS)


def _on(year, month, day):
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_due_date(due_day, due_months, today):
    """First due date on or after today."""
    months = sorted(set(int(m) for m in (due_months or []))) or list(range(1, 13))
    for add in range(0, 25):
        idx = today.month - 1 + add
        y, m = today.year + idx // 12, idx % 12 + 1
        if m in months:
            d = _on(y, m, due_day)
            if d >= today:
                return d
    return None


def due_state(due, today, warn_days):
    """'due_today' (red), 'due_soon' (orange: the warn_days days before), or 'normal'."""
    if due is None:
        return 'normal', None
    days_left = (due - today).days
    if days_left == 0:
        return 'due_today', 0
    if 0 < days_left <= warn_days:
        return 'due_soon', days_left
    return 'normal', days_left


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def due_text(due_day, due_months):
    months = sorted(set(int(m) for m in (due_months or [])))
    if not months or len(months) == 12:
        return f"{ordinal(due_day)} of every month"
    return f"{ordinal(due_day)} " + ' / '.join(MONTH_SHORT[m] for m in months)
