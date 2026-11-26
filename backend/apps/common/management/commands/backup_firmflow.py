from django.core.management.base import BaseCommand, CommandError
from apps.common.backup import create_backup, BackupError


class Command(BaseCommand):
    help = 'Make one backup file (database + attachments + logo). See apps/common/backup.py.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', help='Folder for backup files (default: setting BACKUP_DIR)')
        parser.add_argument('--keep', type=int, help='Keep only the newest N backups (default: setting BACKUP_KEEP)')

    def handle(self, *args, **opts):
        try:
            path = create_backup(opts.get('dir'), opts.get('keep'))
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'Backup written: {path}'))
        self.stdout.write('Reminder: PAN_ENCRYPTION_KEY is not in the backup. Keep a copy of the .env file in a safe place.')
