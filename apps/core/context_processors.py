from django.utils.translation import gettext_lazy as _

# Breadcrumb label for each page, by URL name; anything not listed falls
# back to the URL name made readable ("landlord_bookings" -> "Landlord bookings").
_CRUMBS = {
    'list': _('Search Houses'), 'detail': _('Property'), 'login': _('Sign in'), 'register': _('Register'),
    'saved': _('Saved'), 'my_bookings': _('My Bookings'), 'create_booking': _('Book'), 'booking_sent': _('Request sent'),
    'my_contract': _('My Contract'), 'my_payments': _('Payments'), 'inbox': _('Messages'), 'profile': _('My Profile'),
    'write_review': _('Rate your stay'), 'privacy': _('Privacy Policy'), 'terms': _('Terms of Use'),
    'verify_by_code': _('Verify a contract'),
}


def breadcrumb(request):
    match = getattr(request, 'resolver_match', None)
    if not match or match.url_name == 'dashboard':
        return {}
    if match.namespace == 'notifications' and match.url_name == 'inbox':
        return {'crumb_label': _('Notifications')}
    label = _CRUMBS.get(match.url_name) or (match.url_name or '').replace('_', ' ').capitalize()
    return {'crumb_label': label}
