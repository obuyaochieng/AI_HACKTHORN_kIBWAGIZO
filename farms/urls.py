from django.urls import path, include
from . import views

urlpatterns = [
    # Map views
    path('', views.MapView.as_view(), name='map_viewer'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('analysis/', views.SatelliteAnalysisView.as_view(), name='satellite_analysis'),
    
    # API endpoints
    path('api/run-analysis/', views.run_analysis, name='run_analysis'),
    path('api/analysis/<str:farm_id>/', views.get_analysis_data, name='get_analysis_data'),
    path('api/trigger-insurance/', views.trigger_insurance_check, name='trigger_insurance'),
    path('api/test-gee/', views.test_gee_api, name='test_gee'),
    
    # Admin functions
    path('import/', views.import_shapefiles, name='import_shapefiles'),
    
    # Farm management
    path('farms/', include([
        path('', views.FarmListView.as_view(), name='farm_list'),
        path('<int:pk>/', views.FarmDetailView.as_view(), name='farm_detail'),
    ])),
]