import calendar
from datetime import date
from .models import FinancialYear, Period
from apps.accounts.models import Firm

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def generate_financial_years_for_firm(firm: Firm, start_calendar_year: int = 2004, end_calendar_year: int = None):
    """
    Generates all Financial Years and sub-periods (Month, Quarter, Half, Year)
    for a firm based on its fy_start_month (default: 4 for India).
    """
    fy_start_month = firm.fy_start_month or 4
    if end_calendar_year is None:
        from apps.common.dates import firm_today
        end_calendar_year = fy_start_year_for(firm, firm_today(firm)) + 1
        from apps.common.logging import log_event
        log_event('fy.generate_default_end', 'Firm', firm.id, end_calendar_year=end_calendar_year)

    for y in range(start_calendar_year, end_calendar_year + 1):
        if fy_start_month == 1:
            fy_start = date(y, 1, 1)
            fy_end = date(y, 12, 31)
            label = str(y)
        else:
            fy_start = date(y, fy_start_month, 1)
            next_year = y + 1
            # Last day of month prior to start_month in next year
            end_month = fy_start_month - 1 if fy_start_month > 1 else 12
            _, last_day = calendar.monthrange(next_year, end_month)
            fy_end = date(next_year, end_month, last_day)
            label = f"{y}-{str(next_year)[-2:]}"

        fy, _ = FinancialYear.objects.get_or_create(
            firm=firm,
            label=label,
            defaults={
                'start_date': fy_start,
                'end_date': fy_end,
            }
        )

        # 1. Full Year Period
        Period.objects.get_or_create(
            fy=fy,
            kind=Period.Kind.YEAR,
            sequence=1,
            defaults={
                'label': f"FY {label}",
                'start_date': fy_start,
                'end_date': fy_end,
            }
        )

        # 2. Monthly Periods (12 months)
        cur_year = y
        cur_month = fy_start_month
        for m_seq in range(1, 13):
            _, last_day_m = calendar.monthrange(cur_year, cur_month)
            m_start = date(cur_year, cur_month, 1)
            m_end = date(cur_year, cur_month, last_day_m)
            m_label = f"{MONTH_NAMES[cur_month]} {cur_year}"

            Period.objects.get_or_create(
                fy=fy,
                kind=Period.Kind.MONTH,
                sequence=m_seq,
                defaults={
                    'label': m_label,
                    'start_date': m_start,
                    'end_date': m_end,
                }
            )

            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1

        # 3. Quarterly Periods (4 quarters)
        # Q1: Months 1-3, Q2: Months 4-6, Q3: Months 7-9, Q4: Months 10-12
        months_qs = list(fy.periods.filter(kind=Period.Kind.MONTH).order_by('sequence'))
        if len(months_qs) == 12:
            for q_idx in range(4):
                q_months = months_qs[q_idx * 3 : (q_idx + 1) * 3]
                q_start = q_months[0].start_date
                q_end = q_months[-1].end_date
                q_label = f"Q{q_idx + 1} {label}"
                Period.objects.get_or_create(
                    fy=fy,
                    kind=Period.Kind.QUARTER,
                    sequence=q_idx + 1,
                    defaults={
                        'label': q_label,
                        'start_date': q_start,
                        'end_date': q_end,
                    }
                )

            # 4. Half Yearly Periods (2 halves)
            h1_start = months_qs[0].start_date
            h1_end = months_qs[5].end_date
            Period.objects.get_or_create(
                fy=fy,
                kind=Period.Kind.HALF,
                sequence=1,
                defaults={
                    'label': f"H1 {label}",
                    'start_date': h1_start,
                    'end_date': h1_end,
                }
            )

            h2_start = months_qs[6].start_date
            h2_end = months_qs[11].end_date
            Period.objects.get_or_create(
                fy=fy,
                kind=Period.Kind.HALF,
                sequence=2,
                defaults={
                    'label': f"H2 {label}",
                    'start_date': h2_start,
                    'end_date': h2_end,
                }
            )


def fy_start_year_for(firm, ref_date):
    """Calendar year in which the FY containing ref_date starts."""
    start_month = firm.fy_start_month or 4
    return ref_date.year if ref_date.month >= start_month else ref_date.year - 1


def ensure_financial_years(firm, ref_date=None, years_ahead=1):
    """
    Make sure FYs and periods exist from the earliest FY (or 2004) up to the
    FY containing ref_date plus `years_ahead`. Safe to run many times.
    Returns (first_start_year, last_start_year).
    """
    from apps.common.dates import firm_today
    from apps.common.logging import log_event
    ref_date = ref_date or firm_today(firm)
    last = fy_start_year_for(firm, ref_date) + years_ahead
    earliest = FinancialYear.objects.filter(firm=firm).order_by('start_date').first()
    first = earliest.start_date.year if earliest else 2004
    before = FinancialYear.objects.filter(firm=firm).count()
    generate_financial_years_for_firm(firm, start_calendar_year=first, end_calendar_year=last)
    after = FinancialYear.objects.filter(firm=firm).count()
    log_event('fy.ensure', 'Firm', firm.id, first_start_year=first, last_start_year=last,
              created=after - before)
    return first, last


def find_period(firm, kind, ref_date, offset=0):
    """
    Period of `kind` that contains ref_date, moved by `offset` periods
    (offset=-1 -> the previous month / quarter / half / year).
    """
    current = Period.objects.filter(fy__firm=firm, kind=kind, start_date__lte=ref_date,
                                    end_date__gte=ref_date).select_related('fy').first()
    if current is None or not offset:
        return current
    qs = Period.objects.filter(fy__firm=firm, kind=kind).select_related('fy')
    if offset < 0:
        return qs.filter(end_date__lt=current.start_date).order_by('-start_date')[abs(offset) - 1:abs(offset)].first()
    return qs.filter(start_date__gt=current.end_date).order_by('start_date')[offset - 1:offset].first()
