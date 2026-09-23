from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

class VotAdminSite(AdminSite):
    """Custom admin site with VOT House Finding branding"""
    site_header = _('VOT House Finding Administration')
    site_title = _('VOT House Finding Admin')
    index_title = _('Site Administration')

    def each_context(self, request):
        context = super().each_context(request)
        context['site_header'] = 'VOT House Finding Administration'
        return context

# Create custom admin site instance
vot_admin_site = VotAdminSite(name='vot_admin')