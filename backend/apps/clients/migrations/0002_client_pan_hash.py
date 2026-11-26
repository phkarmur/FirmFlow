from django.db import migrations, models


def fill_pan_hash(apps, schema_editor):
    """Compute the PAN blind index for existing clients (needs the same PAN_ENCRYPTION_KEY)."""
    from apps.common.crypto import decrypt_pan, pan_blind_index
    Client = apps.get_model('clients', 'Client')
    filled = failed = 0
    for client in Client.objects.exclude(pan_encrypted='').only('id', 'pan_encrypted'):
        pan = decrypt_pan(client.pan_encrypted)
        if pan:
            Client.objects.filter(id=client.id).update(pan_hash=pan_blind_index(pan))
            filled += 1
        else:
            failed += 1
    print(f'\n  [clients.0002] pan_hash filled={filled} decrypt_failed={failed}')


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='pan_hash',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.RunPython(fill_pan_hash, migrations.RunPython.noop),
    ]
