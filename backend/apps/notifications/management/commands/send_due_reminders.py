from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Send the daily "due today / overdue" notifications now (the scheduler runs this at 08:00).'

    def handle(self, *args, **options):
        from apps.notifications.tasks import send_due_reminders
        self.stdout.write(str(send_due_reminders()))
