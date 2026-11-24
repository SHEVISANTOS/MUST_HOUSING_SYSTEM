from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.urls import translate_url
from django.utils.translation import get_language_from_path


class CanonicalHostMiddleware:
    """One address for the whole site. www.vothousefinding.com and the old
    sslip.io address served identical pages, which search engines treat as
    duplicate sites splitting the ranking. They now 301 to SITE_URL's host,
    path and query kept (so old printed QR links still land correctly).
    /healthz stays answerable on any host for the monitor."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical = urlsplit(settings.SITE_URL).netloc if settings.SITE_URL else ''

    def __call__(self, request):
        host = request.get_host().split(':')[0] if self.canonical else ''
        if (self.canonical and not settings.DEBUG and host != self.canonical.split(':')[0]
                and host not in ('localhost', '127.0.0.1') and request.path != '/healthz'):
            return HttpResponsePermanentRedirect(f"{settings.SITE_URL}{request.get_full_path()}")
        return self.get_response(request)


class RememberedLanguageMiddleware:
    """English pages live at /..., Swahili at /sw/... (so Google can index
    both). Someone who chose SW with the switcher and later follows an
    English link (e.g. from a notification or a bookmark) is taken to the
    Swahili version. Only the visitor's own explicit choice (the cookie)
    triggers this - never the browser language - so search engines always
    get the page they asked for."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.method == 'GET'
                and request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) == 'sw'
                and not get_language_from_path(request.path_info)):
            target = translate_url(request.get_full_path(), 'sw')
            if target != request.get_full_path():
                return HttpResponseRedirect(target)
        return self.get_response(request)
