import json
from django.core.management.base import BaseCommand, CommandError
from apps.common.backup import verify_backup, restore_backup, BackupError


class Command(BaseCommand):
    help = 'Check (--verify) or restore (--yes) a FirmFlow backup file.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--verify', action='store_true', help='Check the file only. Changes nothing.')
        parser.add_argument('--yes', action='store_true', help='Replace the live data. Stop the web server and Celery first.')

    def handle(self, *args, **opts):
        try:
            if opts['verify'] or not opts['yes']:
                res = verify_backup(opts['file'])
                self.stdout.write(json.dumps(res, indent=2, default=str))
                if not res['ok']:
                    raise CommandError('The backup check FAILED. Do not rely on this file.')
                self.stdout.write(self.style.SUCCESS('Backup check OK.'))
                if not opts['yes']:
                    self.stdout.write('Nothing was changed. To restore, stop the servers and run again with --yes.')
                    return
            res = restore_backup(opts['file'])
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(json.dumps(res, indent=2, default=str))
        self.stdout.write(self.style.SUCCESS('Restore done. Run "python manage.py migrate", then start the servers.'))
