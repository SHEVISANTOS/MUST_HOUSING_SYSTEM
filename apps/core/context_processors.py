from django.utils.translation import gettext_lazy as _

# Breadcrumb label for each page, by URL name; anything not listed falls
# back to the URL name made readable ("landlord_bookings" -> "Landlord bookings").
_CRUMBS = {
    'list': _('Search Houses'), 'detail': _('Property'), 'login': _('Sign in'), 'register': _('Register'),
    'saved': _('Saved'), 'my_bookings': _('My Bookings'), 'create_booking': _('Book'), 'booking_sent': _('Request sent'),
    'my_contract': _('My Contract'), 'my_payments': _('Payments'), 'inbox': _('Messages'), 'profile': _('My Profile'),
    'write_review': _('Rate your stay'), 'privacy': _('Privacy Policy'), 'terms': _('Terms of Use'),
    'verify_by_code': _('Verify a contract'), 'area': _('Area'),
}


def breadcrumb(request):
    match = getattr(request, 'resolver_match', None)
    if not match or match.url_name == 'dashboard':
        return {}
    if match.namespace == 'notifications' and match.url_name == 'inbox':
        return {'crumb_label': _('Notifications')}
    label = _CRUMBS.get(match.url_name) or (match.url_name or '').replace('_', ' ').capitalize()
    return {'crumb_label': label}


def seo(request):
    """canonical + hreflang links for the current page, and the Search
    Console verification token. Pages outside the language-prefixed URLs
    (e.g. /v/<token>/) get a canonical only."""
    from django.conf import settings
    from django.urls import translate_url
    from django.utils.translation import get_language

    base = settings.SITE_URL or request.build_absolute_uri('/').rstrip('/')
    path = request.path
    alternates = {}
    for code, _name in settings.LANGUAGES:
        alt = translate_url(path, code)
        alternates[code] = base + alt
    has_twins = len(set(alternates.values())) > 1
    # Phone set to Swahili, reading the English page, never chose a language:
    # offer the Swahili version (a banner, not a redirect - see middleware).
    suggest_sw = False
    if has_twins and get_language() == 'en' and settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
        from django.utils.translation.trans_real import parse_accept_lang_header
        langs = parse_accept_lang_header(request.META.get('HTTP_ACCEPT_LANGUAGE', ''))
        suggest_sw = bool(langs) and langs[0][0].split('-')[0].lower() == 'sw'
    return {
        'suggest_sw_url': alternates.get('sw', '') if suggest_sw else '',
        'site_base': base,
        'canonical_url': base + path,
        'hreflang_links': alternates if has_twins else {},
        'x_default_url': alternates.get('en') if has_twins else '',
        'og_locale': 'sw_TZ' if get_language() == 'sw' else 'en_US',
        'google_site_verification': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
    }
