from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

class MUSTAdminSite(AdminSite):
    """Custom admin site with MUST branding"""
    site_header = _('MUST Housing Administration')
    site_title = _('MUST Housing Admin')
    index_title = _('Site Administration')
    
    def each_context(self, request):
        context = super().each_context(request)
        context['site_header'] = 'MUST Housing Administration'
        return context

# Create custom admin site instance
must_admin_site = MUSTAdminSite(name='must_admin')