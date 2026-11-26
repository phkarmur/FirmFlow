from celery import shared_task
from apps.common.logging import log_event


@shared_task
def ensure_financial_years_all_firms():
    """Daily: keep FYs/periods generated up to next year (stops the 1-April cliff)."""
    from apps.accounts.models import Firm
    from apps.periods.generator import ensure_financial_years
    log_event('job.start', 'Job', 'ensure_financial_years')
    done = 0
    try:
        for firm in Firm.objects.all():
            ensure_financial_years(firm)
            done += 1
    except Exception as exc:  # noqa: BLE001 - must log every job failure
        import traceback
        log_event('job.fail', 'Job', 'ensure_financial_years', result='error', level='ERROR',
                  error=str(exc), traceback=traceback.format_exc()[-2000:])
        raise
    log_event('job.end', 'Job', 'ensure_financial_years', firms=done)
