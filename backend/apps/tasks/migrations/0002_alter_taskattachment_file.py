import apps.common.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskattachment',
            name='file',
            field=models.FileField(max_length=255, storage=apps.common.storage.private_storage, upload_to='task_attachments/%Y/%m/'),
        ),
    ]
