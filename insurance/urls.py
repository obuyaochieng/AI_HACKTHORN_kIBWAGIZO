from django.urls import path
from . import views

urlpatterns = [
    path('policies/', views.policy_list, name='policy_list'),
    path('policy/create/', views.policy_create, name='policy_create'),
    path('policy/<str:policy_number>/', views.policy_detail, name='policy_detail'),
    path('claims/', views.claim_list, name='claim_list'),
    path('claim/create/<str:policy_number>/', views.claim_create, name='claim_create'),
    path('claim/<str:claim_number>/', views.claim_detail, name='claim_detail'),
    path('dashboard/', views.insurance_dashboard, name='insurance_dashboard'),
    path('reports/', views.insurance_reports, name='insurance_reports'),
]