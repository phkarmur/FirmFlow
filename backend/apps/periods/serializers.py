from rest_framework import serializers
from .models import FinancialYear, Period

class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ['id', 'fy', 'kind', 'label', 'start_date', 'end_date', 'sequence']


class FinancialYearSerializer(serializers.ModelSerializer):
    periods = PeriodSerializer(many=True, read_only=True)
    assessment_year_label = serializers.CharField(read_only=True)

    class Meta:
        model = FinancialYear
        fields = ['id', 'label', 'assessment_year_label', 'start_date', 'end_date', 'periods']
