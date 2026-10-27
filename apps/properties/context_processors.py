from django.utils.functional import SimpleLazyObject


def saved_property_ids(request):
    """
    Makes {{ saved_property_ids }} (a set of Property ids) available to
    every template, for _listing_card.html's heart button - lazy so pages
    that never render a listing card don't pay for the query.
    """
    def _compute():
        if not request.user.is_authenticated:
            return frozenset()
        from .models import SavedProperty
        return frozenset(SavedProperty.objects.filter(user=request.user).values_list('property_id', flat=True))

    return {'saved_property_ids': SimpleLazyObject(_compute)}
