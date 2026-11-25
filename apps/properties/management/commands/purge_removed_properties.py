from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.properties.models import Property


class Command(BaseCommand):
    help = (
        "Permanently deletes listings an admin removed more than "
        "DELETED_PROPERTY_RETENTION_DAYS ago, together with their bookings, "
        "contracts and payments. Runs from the daily update_tenancy_statuses job."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="List what would be deleted, delete nothing.")

    def handle(self, *args, dry_run=False, **options):
        cutoff = timezone.now() - timezone.timedelta(days=settings.DELETED_PROPERTY_RETENTION_DAYS)
        expired = Property.all_objects.removed().filter(deleted_at__lt=cutoff)
        names = [f"#{p.pk} {p.title}" for p in expired]
        if dry_run:
            self.stdout.write(f"Would erase {len(names)} removed listing(s): {', '.join(names) or '-'}")
            return
        for prop in expired:
            prop.delete()
        self.stdout.write(self.style.SUCCESS(f"Removed listings erased for good: {len(names)}."
                                             + (f" ({', '.join(names)})" if names else "")))
