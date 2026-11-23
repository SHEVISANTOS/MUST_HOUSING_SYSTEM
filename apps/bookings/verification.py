"""Verification for tenancy contract PDFs, two independent ways:

- QR code -> /v/<token>/. The token records the contract terms at the moment
  the PDF was issued (dates, rent), MAC'd with SECRET_KEY like payment codes,
  so altered terms or a later change to the contract both show up.
- Confirmation code, e.g. VHF-C12-K7Q4-M9XZ-3B, printed on the contract and
  typed at /verify/ (or read over the phone). 50 bits of HMAC per contract:
  can't be derived from the contract number and can't be guessed.

Separate HMAC salts from payment codes, so one document's code can never be
passed off as another kind of document.
"""
import base64
import re
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.payments.verification import _base36, _mac, _secrets, qr_data_uri, verify_url

TOKEN_SALT = 'vot.contract-verification'
CODE_SALT = 'vot.contract-confirmation-code'


def make_contract_token(tenancy):
    rent_cents = int(Decimal(tenancy.property.monthly_rent) * 100)
    body = '.'.join([
        'c' + _base36(tenancy.id),
        _base36(tenancy.start_date.toordinal()),
        _base36(tenancy.end_date.toordinal()),
        _base36(rent_cents),
        _base36(int(timezone.now().timestamp())),
    ])
    return f'{body}.{_mac(body, settings.SECRET_KEY, TOKEN_SALT)}'


def read_contract_token(token):
    """Contract id + terms at issue if genuine; None if forged or altered."""
    body, _, mac = token.rpartition('.')
    if not body.startswith('c') or not any(
        constant_time_compare(mac, _mac(body, s, TOKEN_SALT)) for s in _secrets()
    ):
        return None
    try:
        tid, start, end, rent, issued = body[1:].split('.')
        return {
            'id': int(tid, 36),
            'start': date.fromordinal(int(start, 36)),
            'end': date.fromordinal(int(end, 36)),
            'rent': Decimal(int(rent, 36)) / 100,
            'issued': int(issued, 36),
        }
    except (ValueError, OverflowError):
        return None


def _code_mac(tenancy_id, secret):
    digest = salted_hmac(CODE_SALT, f'contract:{tenancy_id}', secret=secret, algorithm='sha256').digest()
    return base64.b32encode(digest).decode()[:10]


def confirmation_code(tenancy):
    mac = _code_mac(tenancy.id, settings.SECRET_KEY)
    return f'VHF-C{tenancy.id}-{mac[:4]}-{mac[4:8]}-{mac[8:]}'


def read_confirmation_code(text):
    """Contract id if the typed code is genuine, else None. Forgiving of case,
    spaces/dashes, and 0/1/8 typed for O/I/B (base32 has no 0, 1 or 8)."""
    raw = re.sub(r'[^A-Z0-9]', '', (text or '').upper())
    match = re.fullmatch(r'VHFC(\d+)([A-Z0-9]{10})', raw)
    if not match:
        return None
    tenancy_id = int(match.group(1))
    mac = match.group(2).translate(str.maketrans('018', 'OIB'))
    if any(constant_time_compare(mac, _code_mac(tenancy_id, s)) for s in _secrets()):
        return tenancy_id
    return None


def code_entry_url(request):
    base = settings.SITE_URL or f'{request.scheme}://{request.get_host()}'
    return base + reverse('verify_by_code')


def contract_document_context(request, tenancy):
    """Extra template context for a verifiable contract PDF."""
    url = verify_url(request, make_contract_token(tenancy))
    entry = code_entry_url(request)
    return {
        'verify_url': url,
        'verify_qr': qr_data_uri(url),
        'confirmation_code': confirmation_code(tenancy),
        'code_entry_url': entry.split('://', 1)[-1],
    }
