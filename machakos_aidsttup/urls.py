"""
URL configuration for machakos_aidsttup project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from farms import views as farm_views

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Authentication
    path('accounts/', include('django.contrib.auth.urls')),
    
    # Main pages
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path('dashboard/', farm_views.dashboard, name='dashboard'),
    
    # Map viewer
    path('map/', farm_views.map_viewer, name='map_viewer'),
    path('api/farms/', farm_views.farm_geojson, name='farm_geojson'),
    path('api/subcounties/', farm_views.subcounty_geojson, name='subcounty_geojson'),
    
    # Farmer registration
    path('farmer/register/', farm_views.farmer_register, name='farmer_register'),
    path('farmer/<int:farmer_id>/', farm_views.farmer_detail, name='farmer_detail'),
    
    # Farm upload
    path('farm/upload/', farm_views.farm_upload, name='farm_upload'),
    path('farm/<str:farm_id>/', farm_views.farm_detail, name='farm_detail'),
    
    # Insurance
    path('insurance/', include('insurance.urls')),
    
    # Satellite analysis
    path('satellite/analyze/', farm_views.satellite_analysis, name='satellite_analysis'),
    path('satellite/results/<str:farm_id>/', farm_views.satellite_results, name='satellite_results'),
    
    # API
    path('api/', include('farms.api_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)