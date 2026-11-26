"""
Due-date rules (spec §5.3). Rules are data on TaskType.default_due_rule.

Supported kinds:
  {kind: 'fixed_day_after_period_end', day: 20, months_after: 1}
      GSTR-3B: 20th of the month after the period ends.
      Day is limited to the last day of the target month (31 -> 30 Jun).
  {kind: 'fixed_date', month: 7, day: 31}
      With an FY: first such date AFTER the FY ends (ITR FY 2024-25 -> 31-07-2025).
      Without an FY: next such date on or after today (old behaviour).
  {kind: 'per_period_sequence', dates: {"1": "07-31", "2": "10-31", "3": "01-31", "4": "05-31"}}
      Quarterly returns (TDS, advance tax). Key = period sequence in the FY,
      value = "MM-DD". Result = first such date on or after the period START.
  {kind: 'days_after_creation', days: 15}
  {} or {kind: 'none'}  -> 15 days after today (Task.due_date is required).
"""
import calendar
from datetime import date, timedelta

DEFAULT_DAYS = 15


def _safe_date(year, month, day):
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(int(day), last))


def _first_on_or_after(month, day, start):
    cand = _safe_date(start.year, month, day)
    if cand < start:
        cand = _safe_date(start.year + 1, month, day)
    return cand


def calculate_due_date(rule, period=None, fy=None, today=None):
    """Return (due_date, explanation). Never raises for a bad rule; falls back."""
    today = today or date.today()
    rule = rule or {}
    kind = rule.get('kind') or 'days_after_creation'
    fy = fy or (period.fy if period is not None else None)
    try:
        if kind == 'fixed_day_after_period_end':
            end = period.end_date if period is not None else (fy.end_date if fy is not None else None)
            if end is not None:
                months_after = int(rule.get('months_after', 1))
                m_index = end.month - 1 + months_after
                year = end.year + m_index // 12
                month = m_index % 12 + 1
                return _safe_date(year, month, rule.get('day', 20)), f'{kind} from period end {end}'
        elif kind == 'fixed_date':
            m, d = int(rule.get('month', 7)), int(rule.get('day', 31))
            if fy is not None:
                return _first_on_or_after(m, d, fy.end_date + timedelta(days=1)), f'{kind} after FY end {fy.end_date}'
            return _first_on_or_after(m, d, today), f'{kind} from today (no FY)'
        elif kind == 'per_period_sequence':
            dates = rule.get('dates') or {}
            if period is not None and str(period.sequence) in dates:
                mm, dd = str(dates[str(period.sequence)]).split('-')
                return _first_on_or_after(int(mm), int(dd), period.start_date), f'{kind} seq {period.sequence}'
        elif kind == 'days_after_creation':
            return today + timedelta(days=int(rule.get('days', DEFAULT_DAYS))), kind
    except (ValueError, TypeError, AttributeError) as exc:
        return today + timedelta(days=DEFAULT_DAYS), f'fallback: bad rule ({exc})'
    return today + timedelta(days=DEFAULT_DAYS), f'fallback: rule {kind} not applicable'
