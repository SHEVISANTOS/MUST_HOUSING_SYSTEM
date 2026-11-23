"""Tamper-evident verification for payment PDFs (slips and invoices).

Each PDF carries a QR code / link to /v/<token>/. The token is signed with
HMAC-SHA256 under SECRET_KEY, so nobody without the server's key can mint a
code for a fake or altered document. The verification page then shows the
official record from the database: edits to a printed PDF can't change what
that page says, and a copied genuine QR shows the genuine (different) values.
"""
import base64
from decimal import Decimal
from urllib.parse import urlparse

import segno
from django.conf import settings
from django.core import checks
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

SALT = 'vot.payment-document-verification'
DOC_TYPES = {'s': 'slip', 'i': 'invoice'}
DOC_CODES = {name: code for code, name in DOC_TYPES.items()}
STATUS_CODES = {'PENDING': 'P', 'TENANT_PAID': 'T', 'COMPLETED': 'C', 'OVERDUE': 'O'}
STATUSES = {code: status for status, code in STATUS_CODES.items()}

# Compact token, so the printed QR stays coarse enough to scan:
#   <doc 1><payment uuid, base64url 22><status 1><amount in cents, base36>.<issued unix time, base36>.<mac>
# mac = first 16 bytes (128 bits) of HMAC-SHA256 under SECRET_KEY - far past
# brute-forcing, at a third of the length of a full django.core.signing token.


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _base36(n):
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def _mac(body, secret):
    return _b64(salted_hmac(SALT, body, secret=secret, algorithm='sha256').digest()[:16])


def make_token(payment, doc_type):
    cents = int(Decimal(payment.amount) * 100)
    body = (DOC_CODES[doc_type] + _b64(payment.id.bytes) + STATUS_CODES[payment.status]
            + _base36(cents) + '.' + _base36(int(timezone.now().timestamp())))
    return f'{body}.{_mac(body, settings.SECRET_KEY)}'


def read_token(token):
    """{'d','p','a','s','t'} if genuine; None if forged, altered or garbage."""
    body, _, mac = token.rpartition('.')
    secrets = [settings.SECRET_KEY, *getattr(settings, 'SECRET_KEY_FALLBACKS', [])]
    if not body or not any(constant_time_compare(mac, _mac(body, s)) for s in secrets):
        return None
    try:
        head, issued = body.split('.')
        if head[0] not in DOC_TYPES:
            return None
        return {
            'd': head[0],
            'p': _unb64(head[1:23]).hex(),
            's': STATUSES[head[23]],
            'a': f'{Decimal(int(head[24:], 36)) / 100:.2f}',
            't': int(issued, 36),
        }
    except (ValueError, KeyError, IndexError):
        return None


def verify_url(request, token):
    # SITE_URL pins codes to the official domain whichever host the PDF was
    # downloaded from; falls back to the current host.
    path = reverse('verify_document', kwargs={'token': token})
    base = settings.SITE_URL or f'{request.scheme}://{request.get_host()}'
    return base + path


def qr_data_uri(url):
    return segno.make(url, error='m').png_data_uri(scale=3, border=2)


def document_context(request, payment, doc_type):
    """Extra template context for a verifiable PDF."""
    url = verify_url(request, make_token(payment, doc_type))
    return {'verify_url': url, 'verify_qr': qr_data_uri(url), 'verify_host': urlparse(url).netloc}


def check_signing_key(app_configs, **kwargs):
    """Document codes are only unforgeable if the signing key is secret."""
    key = settings.SECRET_KEY or ''
    if not settings.DEBUG and (key.startswith('fallback-') or len(key) < 40):
        return [checks.Error(
            'SECRET_KEY is missing, weak, or the public fallback value - payment '
            'document QR codes could be forged.',
            hint='Set DJANGO_SECRET_KEY in .env: '
                 'python -c "import secrets; print(secrets.token_urlsafe(50))"',
            id='payments.E001',
        )]
    return []
