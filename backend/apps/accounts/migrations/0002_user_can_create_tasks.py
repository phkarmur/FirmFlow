from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_create_tasks',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
