import uuid
from django.db import models
from apps.common.models import BaseModel
from apps.accounts.models import Firm

class FinancialYear(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='financial_years')
    label = models.CharField(max_length=20) # e.g. "2025-26"
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ['-start_date']
        unique_together = ('firm', 'label')

    def __str__(self):
        return f"FY {self.label}"

    @property
    def assessment_year_label(self):
        """For ITR: AY is FY + 1 year (e.g. FY 2025-26 -> AY 2026-27)."""
        try:
            start_yr = self.start_date.year
            end_yr = self.end_date.year
            return f"{start_yr + 1}-{str(end_yr + 1)[-2:]}"
        except Exception:
            return f"AY ({self.label})"


class Period(BaseModel):
    class Kind(models.TextChoices):
        MONTH = 'month', 'Month'
        QUARTER = 'quarter', 'Quarter'
        HALF = 'half', 'Half Year'
        YEAR = 'year', 'Full Year'

    fy = models.ForeignKey(FinancialYear, on_delete=models.CASCADE, related_name='periods')
    kind = models.CharField(max_length=10, choices=Kind.choices, db_index=True)
    label = models.CharField(max_length=50) # "Apr 2025", "Q1 2025-26", "FY 2025-26"
    start_date = models.DateField()
    end_date = models.DateField()
    sequence = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['start_date', 'sequence']
        unique_together = ('fy', 'kind', 'sequence')

    def __str__(self):
        return f"{self.label} ({self.fy.label})"
