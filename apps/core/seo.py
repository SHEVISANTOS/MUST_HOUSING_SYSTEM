"""Search-engine plumbing: sitemap, canonical/hreflang links, JSON-LD."""
import json

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse, translate_url
from django.utils.html import mark_safe
from django.utils.translation import gettext as _


def ld_json(data):
    """<script type=application/ld+json> body, safe to inline in HTML."""
    return mark_safe(json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


class _Base(Sitemap):
    i18n = True            # one <url> per language...
    alternates = True      # ...each listing its hreflang twins
    x_default = True
    protocol = 'http' if settings.DEBUG else 'https'


class StaticSitemap(_Base):
    changefreq = 'daily'

    def items(self):
        return ['core:dashboard', 'properties:list']

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return {'core:dashboard': 1.0, 'properties:list': 0.9}.get(item, 0.3)


class PropertySitemap(_Base):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        from apps.properties.models import Property
        return Property.objects.public().order_by('-updated_at')

    def location(self, prop):
        return reverse('properties:detail', args=[prop.pk])

    def lastmod(self, prop):
        return prop.updated_at


class AreaSitemap(_Base):
    changefreq = 'daily'
    priority = 0.7

    def items(self):
        from apps.properties.areas import areas_with_counts
        return [a['slug'] for a in areas_with_counts() if a['count']]   # empty areas are noindex

    def location(self, slug):
        return reverse('area', args=[slug])


class EnglishOnlySitemap(Sitemap):
    """Pages whose text exists only in English (legal pages) - listing a
    /sw/ copy would tell Google an English page is Swahili."""
    changefreq = 'monthly'
    priority = 0.3
    protocol = _Base.protocol

    def items(self):
        return ['privacy', 'terms']

    def location(self, item):
        from django.utils import translation
        with translation.override('en'):
            return reverse(item)


SITEMAPS = {'legal': EnglishOnlySitemap, 'pages': StaticSitemap, 'areas': AreaSitemap, 'homes': PropertySitemap}


def organization_ld(request):
    site = settings.SITE_URL or request.build_absolute_uri('/').rstrip('/')
    from django.templatetags.static import static
    return {
        '@context': 'https://schema.org', '@type': 'Organization', 'name': 'VOT House Finding',
        'legalName': 'VOT MWANZA LIMITED', 'url': site + '/',
        'logo': request.build_absolute_uri(static('img/vot_logo.png')),
        'email': 'info@votmwanza.co.tz',
        'address': {'@type': 'PostalAddress', 'addressLocality': 'Mwanza', 'addressCountry': 'TZ'},
        'areaServed': {'@type': 'City', 'name': 'Mwanza'},
        'alternateName': ['VOT Mwanza', 'VOT House Finding Mwanza'],
        'description': _('Houses, rooms, self contained units and apartments for rent in Mwanza, Tanzania, from landlords checked by VOT.'),
        'knowsLanguage': ['en', 'sw'],
    }


COMMERCIAL_TYPES = ('SHOP', 'OFFICE', 'GODOWN')


def home_faq():
    """Questions people in Mwanza actually search for, answered from what the
    site really does (and today's real rents). Shown on the home page and
    sent as FAQPage structured data, in the active language."""
    from django.db.models import Max, Min
    from apps.properties.models import Property
    rents = (Property.objects.public().exclude(property_type__in=COMMERCIAL_TYPES)
             .aggregate(lo=Min('monthly_rent'), hi=Max('monthly_rent')))
    if rents['lo'] is not None:
        rent_answer = _('On VOT House Finding, homes in Mwanza currently rent from TZS %(lo)s to TZS %(hi)s per month. '
                        'Single rooms and self contained units are usually the cheapest; apartments and family houses cost more.') % {
            'lo': f"{int(rents['lo']):,}", 'hi': f"{int(rents['hi']):,}"}
    else:
        rent_answer = _('Rent depends on the area and the type of house. Single rooms and self contained units are usually '
                        'the cheapest; apartments and family houses cost more. Every listing shows its monthly rent.')
    return [
        {'q': _('How much is rent for a house in Mwanza?'), 'a': rent_answer},
        {'q': _('Where can students find a room near SAUT or CUHAS?'),
         'a': _('Students at St. Augustine University (SAUT) usually look in Nyegezi, and students at CUHAS and '
                'Bugando Medical Centre look in Bugando. Each area has its own page listing the rooms available there.')},
        {'q': _('What kinds of houses can I rent in Mwanza?'),
         'a': _('Single rooms, bedsitters, self contained rooms, 1 to 4+ bedroom houses, apartments, standalone houses, '
                'maisonettes and servant quarters - as well as shops, offices and godowns for business.')},
        {'q': _('How do I know the landlord is genuine?'),
         'a': _("Every landlord is checked by VOT before their homes appear on the site. Each listing also shows "
                "reviews from the tenants who lived there.")},
        {'q': _('How do I rent a house through VOT House Finding?'),
         'a': _('Search by area, rent and type of house, then send a booking request with your move-in date. '
                'When the landlord approves, you pay the landlord directly and get a rental contract.')},
        {'q': _('Can I check that a rental contract is real?'),
         'a': _('Yes. Every contract has a QR code. Scanning it opens a page on vothousefinding.com that shows '
                'whether the contract is genuine.')},
        {'q': _('Is VOT House Finding available in Kiswahili?'),
         'a': _('Yes. Every page is available in both English and Kiswahili.')},
    ]


def faq_ld(faq):
    return {
        '@context': 'https://schema.org', '@type': 'FAQPage',
        'mainEntity': [{'@type': 'Question', 'name': f['q'],
                        'acceptedAnswer': {'@type': 'Answer', 'text': f['a']}} for f in faq],
    }
