"""Search-engine plumbing: sitemap, canonical/hreflang links, JSON-LD."""
import json

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse, translate_url
from django.utils.html import mark_safe


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
    }
