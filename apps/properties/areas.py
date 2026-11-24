"""Mwanza neighbourhoods that get their own search-friendly landing page
(/houses-for-rent/<slug>/ and /sw/nyumba-za-kupanga/<slug>/).

`match` are the spellings landlords type in the listing's location field;
a listing belongs to an area if its location contains any of them.
`note` is a short, factual landmark people search by.
"""
from django.utils.translation import gettext_lazy as _

AREAS = [
    {'slug': 'nyamagana', 'name': 'Nyamagana', 'match': ['nyamagana', 'city centre', 'city center', 'mjini'], 'note': _('central Mwanza city')},
    {'slug': 'ilemela', 'name': 'Ilemela', 'match': ['ilemela'], 'note': ''},
    {'slug': 'nyegezi', 'name': 'Nyegezi', 'match': ['nyegezi', 'saut', 'malimbe'], 'note': _('near St. Augustine University (SAUT)')},
    {'slug': 'bugando', 'name': 'Bugando', 'match': ['bugando'], 'note': _('near Bugando Medical Centre and CUHAS')},
    {'slug': 'buhongwa', 'name': 'Buhongwa', 'match': ['buhongwa'], 'note': ''},
    {'slug': 'mkolani', 'name': 'Mkolani', 'match': ['mkolani'], 'note': ''},
    {'slug': 'igoma', 'name': 'Igoma', 'match': ['igoma'], 'note': ''},
    {'slug': 'kishiri', 'name': 'Kishiri', 'match': ['kishiri'], 'note': ''},
    {'slug': 'buswelu', 'name': 'Buswelu', 'match': ['buswelu'], 'note': ''},
    {'slug': 'nyakato', 'name': 'Nyakato', 'match': ['nyakato'], 'note': ''},
    {'slug': 'mabatini', 'name': 'Mabatini', 'match': ['mabatini'], 'note': ''},
    {'slug': 'kirumba', 'name': 'Kirumba', 'match': ['kirumba'], 'note': ''},
    {'slug': 'pasiansi', 'name': 'Pasiansi', 'match': ['pasiansi'], 'note': ''},
    {'slug': 'isamilo', 'name': 'Isamilo', 'match': ['isamilo'], 'note': ''},
    {'slug': 'capri-point', 'name': 'Capri Point', 'match': ['capri point', 'capripoint'], 'note': _('on the Lake Victoria shore')},
    {'slug': 'kiseke', 'name': 'Kiseke', 'match': ['kiseke'], 'note': ''},
    {'slug': 'bwiru', 'name': 'Bwiru', 'match': ['bwiru'], 'note': ''},
    {'slug': 'kitangiri', 'name': 'Kitangiri', 'match': ['kitangiri'], 'note': ''},
    {'slug': 'mahina', 'name': 'Mahina', 'match': ['mahina'], 'note': ''},
    {'slug': 'igogo', 'name': 'Igogo', 'match': ['igogo'], 'note': ''},
    {'slug': 'kisesa', 'name': 'Kisesa', 'match': ['kisesa'], 'note': ''},
    {'slug': 'butimba', 'name': 'Butimba', 'match': ['butimba'], 'note': ''},
]
BY_SLUG = {a['slug']: a for a in AREAS}


def area_filter(area):
    from django.db.models import Q
    q = Q()
    for term in area['match']:
        q |= Q(location__icontains=term)
    return q


def areas_with_counts():
    """Each area with its number of public listings (one query per area is
    fine at this scale - 22 tiny indexed-ish queries, cached by callers)."""
    from .models import Property
    public = Property.objects.public()
    return [dict(a, count=public.filter(area_filter(a)).count()) for a in AREAS]
