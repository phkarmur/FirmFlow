from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_can_create_tasks'),
    ]

    operations = [
        migrations.AddField(
            model_name='firm',
            name='max_upload_mb',
            field=models.PositiveSmallIntegerField(default=25),
        ),
    ]
