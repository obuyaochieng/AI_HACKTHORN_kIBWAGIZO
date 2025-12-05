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
    path('list/', views.FarmListView.as_view(), name='farm_list'),
    path('<str:farm_id>/', views.FarmDetailView.as_view(), name='farm_detail'),
    
    # API views from views_api.py
    path('api/tile-url/', views.gee_tile_url, name='gee_tile_url'),
    path('api/batch-analysis/', views.run_batch_analysis, name='batch_analysis'),
    path('api/boundary/', views.get_machakos_boundary, name='machakos_boundary'),
    path('api/export/', views.export_analysis_data, name='export_analysis'),
]