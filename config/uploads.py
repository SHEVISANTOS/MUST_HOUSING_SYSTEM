import os
import uuid

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.deconstruct import deconstructible

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_MB = 10


def validate_image_upload(f):
    """Allow only JPG/PNG/WEBP images under MAX_IMAGE_MB."""
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValidationError("Only JPG, PNG or WEBP images are allowed.")
    if f.size > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Image must be smaller than {MAX_IMAGE_MB} MB.")


@deconstructible
class RandomName:
    """Save uploads as <folder>/<random-uuid>.<ext>; folder may use %Y/%m/%d."""

    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()
        folder = timezone.now().strftime(self.folder)
        return f"{folder}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, RandomName) and self.folder == other.folder


from django.core.files.storage import FileSystemStorage  # noqa: E402


class PrivateStorage(FileSystemStorage):
    """Files under PRIVATE_MEDIA_ROOT - outside MEDIA_ROOT, so the web server
    never serves them directly. They have no public URL: a view checks who
    is asking and streams the file (e.g. apps.payments.views.payment_proof)."""

    @property
    def base_location(self):
        from django.conf import settings
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        return ''


def private_storage():
    return PrivateStorage()
