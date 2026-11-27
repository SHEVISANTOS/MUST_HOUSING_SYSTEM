"""Simple per-IP / per-user rate limits for actions bots like to repeat
(sign-ups, messages, booking requests). Login attempts are handled
separately by django-axes."""
import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render

logger = logging.getLogger(__name__)


def _who(request, by):
    if by == 'user' and request.user.is_authenticated:
        return f'u{request.user.pk}'
    return 'ip' + (settings.AXES_CLIENT_IP_CALLABLE(request) or '')


def rate_limit(name, limit, window, by='ip', methods=('POST',)):
    """Allow `limit` requests per `window` seconds; after that answer 429
    until the window passes. Only counts the given HTTP methods, so
    viewing a page is never limited - only submitting it."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods and getattr(settings, 'RATE_LIMITS_ENABLED', True):
                key = f'rl:{name}:{_who(request, by)}'
                try:
                    cache.add(key, 0, window)
                    try:
                        count = cache.incr(key)
                    except ValueError:      # expired between add and incr
                        cache.set(key, 1, window)
                        count = 1
                except OSError:             # cache folder not writable: don't break the site
                    logger.warning("Rate limit cache unavailable", exc_info=True)
                    count = 0
                if count > limit:
                    return render(request, '429.html', {'minutes': max(1, window // 60)}, status=429)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
