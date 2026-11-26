import uuid
import django.db.models.deletion
from django.db import migrations, models


def add_defaults(apps, schema_editor):
    from apps.services.compliance import ensure_default_events
    Firm = apps.get_model('accounts', 'Firm')
    ComplianceEvent = apps.get_model('services', 'ComplianceEvent')
    total = 0
    for firm in Firm.objects.all():
        total += ensure_default_events(firm, model=ComplianceEvent)
    print(f'\n  [services.0002] compliance calendar defaults created={total}')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_can_create_tasks'),
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComplianceEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=30)),
                ('title', models.CharField(max_length=150)),
                ('scope', models.CharField(blank=True, default='', max_length=150)),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('due_day', models.PositiveSmallIntegerField()),
                ('due_months', models.JSONField(blank=True, default=list)),
                ('warn_days', models.PositiveSmallIntegerField(default=2)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('firm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compliance_events', to='accounts.firm')),
            ],
            options={
                'ordering': ['sort_order', 'title'],
                'unique_together': {('firm', 'code')},
            },
        ),
        migrations.RunPython(add_defaults, migrations.RunPython.noop),
    ]
