from django.core.management.base import BaseCommand

from apps.notifications.reminders import send_due_reminders


class Command(BaseCommand):
    help = "Send today's rent, contract-ending and review reminders. Safe to run repeatedly."

    def handle(self, *args, **options):
        c = send_due_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Reminders sent - rent: {c['rent']}, contract ending: {c['contract']}, review invites: {c['review']}."))
