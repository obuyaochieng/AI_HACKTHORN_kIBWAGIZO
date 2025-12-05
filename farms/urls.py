# farms/urls.py
from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ======================
    # AUTHENTICATION
    # ======================
    path('accounts/login/', views.user_login, name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/register/', views.register, name='register'),
    path('accounts/profile/', views.user_profile, name='user_profile'),
    path('accounts/change-password/', views.change_password, name='change_password'),
    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('accounts/password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    
    # ======================
    # DASHBOARDS
    # ======================
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    
    # ======================
    # FARM MANAGEMENT
    # ======================
    path('farms/', views.FarmListView.as_view(), name='farm_list'),
    path('farms/add/', views.FarmCreateView.as_view(), name='farm_add'),
    path('farms/<str:farm_id>/', views.FarmDetailView.as_view(), name='farm_detail'),
    path('farms/<str:farm_id>/edit/', views.FarmUpdateView.as_view(), name='farm_edit'),
    path('farms/<str:farm_id>/delete/', views.FarmDeleteView.as_view(), name='farm_delete'),
    
    # ======================
    # INSURANCE
    # ======================
    path('policies/', views.PolicyListView.as_view(), name='policy_list'),
    path('policies/add/', views.PolicyCreateView.as_view(), name='policy_add'),
    path('policies/<int:pk>/', views.PolicyDetailView.as_view(), name='policy_detail'),
    path('policies/<int:pk>/edit/', views.PolicyUpdateView.as_view(), name='policy_edit'),
    
    path('claims/', views.ClaimListView.as_view(), name='claim_list'),
    path('claims/add/', views.ClaimCreateView.as_view(), name='claim_add'),
    path('claims/<int:pk>/', views.ClaimDetailView.as_view(), name='claim_detail'),
    path('claims/<int:pk>/edit/', views.ClaimUpdateView.as_view(), name='claim_edit'),
    path('claims/<int:pk>/approve/', views.approve_claim, name='claim_approve'),
    path('claims/<int:pk>/pay/', views.pay_claim, name='claim_pay'),
    
    # ======================
    # SATELLITE ANALYSIS
    # ======================
    path('analysis/', views.SatelliteAnalysisView.as_view(), name='satellite_analysis'),
    path('analysis/run/', views.run_single_analysis, name='run_analysis'),
    path('analysis/batch/', views.run_batch_analysis, name='batch_analysis'),
    path('analysis/<str:farm_id>/data/', views.get_analysis_data, name='get_analysis_data'),
    path('analysis/export/', views.export_analysis_data, name='export_analysis'),
    path('analysis/trigger-insurance/', views.trigger_insurance_check, name='trigger_insurance'),
    
    # ======================
    # MAP VIEW
    # ======================
    path('map/', views.MapView.as_view(), name='map_view'),
    
    # ======================
    # NOTIFICATIONS
    # ======================
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # ======================
    # API ENDPOINTS
    # ======================
    path('api/farms/<str:farm_id>/analysis/', views.api_farm_analysis, name='api_farm_analysis'),
    path('api/dashboard/stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/test-gee/', views.test_gee_connection, name='test_gee'),
    
    # ======================
    # SYSTEM
    # ======================
    path('upload/', views.FarmCreateView.as_view(), name='farm_upload'),
]