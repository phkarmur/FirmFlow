"""
Date helpers. "Today" MUST be computed in the firm timezone (spec §11),
never with timezone.now().date() (that gives the UTC date, which is
one day behind India between 00:00 and 05:30 IST).
"""
from zoneinfo import ZoneInfo
from django.utils import timezone


def firm_today(firm=None):
    tz_name = getattr(firm, 'timezone', None) if firm is not None else None
    if tz_name:
        try:
            return timezone.localdate(timezone=ZoneInfo(tz_name))
        except Exception:
            pass
    return timezone.localdate()


def current_fy(firm, today=None):
    """Return the FinancialYear that contains today (firm timezone), or None."""
    from apps.periods.models import FinancialYear
    today = today or firm_today(firm)
    return FinancialYear.objects.filter(firm=firm, start_date__lte=today, end_date__gte=today).first()
