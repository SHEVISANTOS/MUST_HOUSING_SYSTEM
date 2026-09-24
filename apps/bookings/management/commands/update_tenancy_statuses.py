from django.core.management.base import BaseCommand
from apps.bookings.services import sync_tenancy_statuses


class Command(BaseCommand):
    help = (
        "Moves Tenancy.status to match today's date (upcoming->active-> "
        "ending_soon->ended) and marks a Booking COMPLETED once its "
        "Tenancy naturally ends. Safe to run repeatedly - a no-op for rows "
        "that are already up to date."
    )

    def handle(self, *args, **options):
        result = sync_tenancy_statuses()
        self.stdout.write(self.style.SUCCESS(
            f"Tenancy statuses updated: {result['tenancies_updated']}. "
            f"Bookings marked COMPLETED: {result['bookings_completed']}."
        ))
