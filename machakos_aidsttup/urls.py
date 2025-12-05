# machakos_aidsttup/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Apps
    path('', RedirectView.as_view(url='/farms/', permanent=False)),
    path('farms/', include('farms.urls')),
    
    # API
    path('api-auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom admin site headers
admin.site.site_header = "Machakos Drought Monitoring Admin"
admin.site.site_title = "Machakos Drought Monitoring"
admin.site.index_title = "Dashboard Administration"