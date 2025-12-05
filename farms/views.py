# farms/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView, DeleteView
from django.db.models import Count, Avg, Max, Min, Sum, Q
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import PermissionDenied
import json
from datetime import datetime, timedelta, date
import csv

from .models import (
    CustomUser, Farm, County, SatelliteAnalysis, 
    InsurancePolicy, InsuranceClaim, Notification,
    GEEExportTask
)
from .forms import (
    FarmerRegistrationForm, FarmUploadForm, 
    InsurancePolicyForm, InsuranceClaimForm,
    UserProfileForm, FarmEditForm
)
from .utils.gee_utils import WorkingGEEAnalyzer, test_working_gee
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


# ======================
# AUTHENTICATION VIEWS
# ======================

def register(request):
    """User registration"""
    if request.method == 'POST':
        form = FarmerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('dashboard')
    else:
        form = FarmerRegistrationForm()
    
    return render(request, 'registration/register.html', {'form': form})


def user_login(request):
    """Custom login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_full_name()}!')
                
                # Redirect based on user type
                if user.is_admin:
                    return redirect('admin_dashboard')
                else:
                    return redirect('dashboard')
    else:
        form = AuthenticationForm()
    
    return render(request, 'registration/login.html', {'form': form})


@login_required
def user_profile(request):
    """User profile view"""
    user = request.user
    profile = getattr(user, 'profile', None)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = user
            profile.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('user_profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'farms/profile.html', {
        'form': form,
        'user': user,
        'profile': profile,
    })


@login_required
def change_password(request):
    """Change password view"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('user_profile')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'registration/change_password.html', {'form': form})


# ======================
# DASHBOARD VIEWS - FIXED
# ======================
# farms/views.py - Update just the DashboardView class

class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard"""
    template_name = 'farms/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Common stats for all users
        context['user'] = user
        context['today'] = date.today()
        
        if user.is_farmer:
            # Farmer dashboard
            farms = Farm.objects.filter(farmer=user, is_active=True)
            policies = InsurancePolicy.objects.filter(farmer=user)
            claims = InsuranceClaim.objects.filter(policy__farmer=user)
            analyses = SatelliteAnalysis.objects.filter(farm__farmer=user).order_by('-analysis_date')[:5]
            
            context.update({
                'farms': farms,
                'farm_count': farms.count(),
                'total_area': farms.aggregate(Sum('area_ha'))['area_ha__sum'] or 0,
                'active_policies': policies.filter(status='active').count(),
                'pending_claims': claims.filter(status__in=['submitted', 'under_review']).count(),
                'latest_analyses': analyses,
                'notifications': user.notifications.filter(is_read=False)[:10],
            })
            
            # Risk overview
            if farms.exists():
                latest_risks = []
                for farm in farms:
                    latest = farm.get_latest_analysis()
                    if latest:
                        latest_risks.append(latest.drought_risk_level)
                
                if latest_risks:
                    context['risk_summary'] = {
                        'high': latest_risks.count('high'),
                        'moderate': latest_risks.count('moderate'),
                        'low': latest_risks.count('low'),
                    }
                else:
                    context['risk_summary'] = {'high': 0, 'moderate': 0, 'low': 0}
        
        elif user.is_admin:
            # Admin dashboard - FIXED: Use correct date filtering
            today = date.today()
            
            # Count new farms registered today - FIXED: Direct date comparison for DateField
            new_farms_today = Farm.objects.filter(registration_date=today).count()
            
            # Count policies issued today - FIXED: Use __date for DateTimeField
            new_policies_today = InsurancePolicy.objects.filter(created_at__date=today).count()
            
            # Count claims submitted today
            new_claims_today = InsuranceClaim.objects.filter(submitted_date=today).count()
            
            # Count analyses run today
            new_analyses_today = SatelliteAnalysis.objects.filter(created_at__date=today).count()
            
            context.update({
                'total_farmers': CustomUser.objects.filter(user_type='farmer').count(),
                'total_farms': Farm.objects.filter(is_active=True).count(),
                'total_area': Farm.objects.filter(is_active=True).aggregate(Sum('area_ha'))['area_ha__sum'] or 0,
                'active_policies': InsurancePolicy.objects.filter(status='active').count(),
                'pending_claims': InsuranceClaim.objects.filter(status__in=['submitted', 'under_review']).count(),
                'total_payout': InsuranceClaim.objects.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
                'recent_claims': InsuranceClaim.objects.order_by('-created_at')[:10],
                'system_alerts': Notification.objects.filter(
                    notification_type='system_alert',
                    is_read=False
                )[:5],
                'recent_activity': {
                    'farms_added': new_farms_today,
                    'policies_issued': new_policies_today,
                    'claims_submitted': new_claims_today,
                    'analyses_run': new_analyses_today,
                }
            })
        
        # Recent activity for all users
        context['recent_activity'] = self.get_recent_activity(user)
        
        return context
    
    def get_recent_activity(self, user):
        """Get recent activity based on user type"""
        today = date.today()
        
        if user.is_admin:
            # FIXED: Use correct field lookups
            return {
                'farms_added': Farm.objects.filter(registration_date=today).count(),
                'policies_issued': InsurancePolicy.objects.filter(created_at__date=today).count(),
                'claims_submitted': InsuranceClaim.objects.filter(submitted_date=today).count(),
                'analyses_run': SatelliteAnalysis.objects.filter(created_at__date=today).count(),
            }
        else:
            return {
                'my_farms': Farm.objects.filter(farmer=user, registration_date=today).count(),
                'my_policies': InsurancePolicy.objects.filter(farmer=user, created_at__date=today).count(),
                'my_claims': InsuranceClaim.objects.filter(policy__farmer=user, submitted_date=today).count(),
            }
        
class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Admin-only dashboard"""
    template_name = 'farms/admin_dashboard.html'
    
    def test_func(self):
        return self.request.user.is_admin
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistics - FIXED: Use correct field names
        context.update({
            'user_stats': self.get_user_stats(),
            'farm_stats': self.get_farm_stats(),
            'insurance_stats': self.get_insurance_stats(),
            'analysis_stats': self.get_analysis_stats(),
            'recent_tasks': GEEExportTask.objects.order_by('-created_at')[:10],
            'system_health': self.get_system_health(),
        })
        
        return context
    
    def get_user_stats(self):
        """Get user statistics"""
        return {
            'total': CustomUser.objects.count(),
            'farmers': CustomUser.objects.filter(user_type='farmer').count(),
            'admins': CustomUser.objects.filter(user_type='admin').count(),
            'agents': CustomUser.objects.filter(user_type='insurance_agent').count(),
            'analysts': CustomUser.objects.filter(user_type='analyst').count(),
            'new_today': CustomUser.objects.filter(date_joined__date=date.today()).count(),
            'verified': CustomUser.objects.filter(is_verified=True).count(),
        }
    
    def get_farm_stats(self):
        """Get farm statistics - FIXED: Use registration_date instead of created_at"""
        farms = Farm.objects.filter(is_active=True)
        
        # Count new farms today
        new_farms_today = farms.filter(registration_date__date=date.today()).count()
        
        return {
            'total': farms.count(),
            'total_area': farms.aggregate(Sum('area_ha'))['area_ha__sum'] or 0,
            'by_crop': dict(farms.values_list('crop_type').annotate(count=Count('id')).order_by('-count')),
            'by_county': dict(farms.values_list('county__subcounty').annotate(count=Count('id')).order_by('-count')),
            'new_today': new_farms_today,
            'irrigated': farms.filter(irrigation=True).count(),
        }
    
    def get_insurance_stats(self):
        """Get insurance statistics"""
        policies = InsurancePolicy.objects.all()
        claims = InsuranceClaim.objects.all()
        
        return {
            'total_policies': policies.count(),
            'active_policies': policies.filter(status='active').count(),
            'premium_collected': policies.aggregate(Sum('premium_amount'))['premium_amount__sum'] or 0,
            'total_claims': claims.count(),
            'pending_claims': claims.filter(status__in=['submitted', 'under_review']).count(),
            'total_payout': claims.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
            'claim_ratio': (claims.count() / policies.count() * 100) if policies.count() > 0 else 0,
        }
    
    def get_analysis_stats(self):
        """Get analysis statistics"""
        analyses = SatelliteAnalysis.objects.all()
        
        return {
            'total': analyses.count(),
            'this_month': analyses.filter(created_at__month=date.today().month).count(),
            'by_risk': dict(analyses.values_list('drought_risk_level').annotate(count=Count('id'))),
            'triggers': analyses.filter(insurance_triggered=True).count(),
            'avg_ndvi': analyses.aggregate(Avg('ndvi'))['ndvi__avg'] or 0,
            'avg_rainfall': analyses.aggregate(Avg('rainfall_mm'))['rainfall_mm__avg'] or 0,
        }
    
    def get_system_health(self):
        """Get system health status"""
        recent_tasks = GEEExportTask.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=1)
        )
        
        failed_tasks = recent_tasks.filter(status='failed').count()
        pending_tasks = recent_tasks.filter(status__in=['pending', 'running']).count()
        
        return {
            'gee_connection': test_working_gee(),
            'recent_tasks': recent_tasks.count(),
            'failed_tasks': failed_tasks,
            'pending_tasks': pending_tasks,
            'health_score': 100 - (failed_tasks * 10) - (pending_tasks * 5),
        }


# ======================
# FARM MANAGEMENT VIEWS - FIXED
# ======================

class FarmListView(LoginRequiredMixin, ListView):
    """List farms with filtering - FIXED: Use registration_date"""
    model = Farm
    template_name = 'farms/farm_list.html'
    context_object_name = 'farms'
    paginate_by = 20
    
    def get_queryset(self):
        user = self.request.user
        queryset = Farm.objects.filter(is_active=True).select_related('farmer', 'county')
        
        # Filter by user type
        if user.is_farmer:
            queryset = queryset.filter(farmer=user)
        
        # Apply filters
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(farm_id__icontains=search) |
                Q(name__icontains=search) |
                Q(farmer__first_name__icontains=search) |
                Q(farmer__last_name__icontains=search) |
                Q(crop_type__icontains=search)
            )
        
        crop_type = self.request.GET.get('crop_type', '')
        if crop_type:
            queryset = queryset.filter(crop_type=crop_type)
        
        county = self.request.GET.get('county', '')
        if county:
            queryset = queryset.filter(county__subcounty=county)
        
        risk_level = self.request.GET.get('risk_level', '')
        if risk_level:
            # Get farms with latest analysis matching risk level
            farm_ids = SatelliteAnalysis.objects.filter(
                drought_risk_level=risk_level
            ).values_list('farm_id', flat=True).distinct()
            queryset = queryset.filter(farm_id__in=farm_ids)
        
        irrigation = self.request.GET.get('irrigation', '')
        if irrigation == 'yes':
            queryset = queryset.filter(irrigation=True)
        elif irrigation == 'no':
            queryset = queryset.filter(irrigation=False)
        
        # FIXED: Use registration_date instead of created_at
        return queryset.order_by('-registration_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'selected_crop': self.request.GET.get('crop_type', ''),
            'selected_county': self.request.GET.get('county', ''),
            'selected_risk': self.request.GET.get('risk_level', ''),
            'selected_irrigation': self.request.GET.get('irrigation', ''),
            'crop_types': Farm.CROP_CHOICES,
            'counties': County.objects.all(),
            'risk_levels': ['low', 'moderate', 'high'],
            'is_admin': user.is_admin,
            'total_farms': self.get_queryset().count(),
        })
        
        return context


class FarmDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Farm details view"""
    model = Farm
    template_name = 'farms/farm_detail.html'
    context_object_name = 'farm'
    slug_field = 'farm_id'
    slug_url_kwarg = 'farm_id'
    
    def test_func(self):
        farm = self.get_object()
        user = self.request.user
        return user.is_admin or farm.farmer == user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        farm = self.object
        
        # Analysis history
        analyses = farm.analyses.all().order_by('-analysis_date')[:24]  # Last 2 years
        policies = farm.policies.all().order_by('-coverage_start')
        claims = farm.claims.all().order_by('-trigger_date')
        
        # Calculate statistics
        if analyses.exists():
            latest = analyses.first()
            monthly_stats = self.get_monthly_stats(analyses)
            
            context.update({
                'latest_analysis': latest,
                'analyses': analyses,
                'monthly_stats': monthly_stats,
                'trend_data': self.get_trend_data(analyses),
                'risk_history': self.get_risk_history(analyses),
            })
        
        context.update({
            'policies': policies,
            'claims': claims,
            'active_policy': policies.filter(status='active').first(),
            'can_edit': self.request.user.is_admin or self.request.user == farm.farmer,
        })
        
        return context
    
    def get_monthly_stats(self, analyses):
        """Calculate monthly average statistics"""
        monthly_data = {}
        
        for analysis in analyses:
            month_key = f"{analysis.year}-{analysis.month:02d}"
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    'ndvi': [],
                    'rainfall': [],
                    'count': 0,
                }
            
            if analysis.ndvi:
                monthly_data[month_key]['ndvi'].append(analysis.ndvi)
            if analysis.rainfall_mm:
                monthly_data[month_key]['rainfall'].append(analysis.rainfall_mm)
            monthly_data[month_key]['count'] += 1
        
        # Calculate averages
        result = {}
        for month_key, data in monthly_data.items():
            result[month_key] = {
                'avg_ndvi': sum(data['ndvi']) / len(data['ndvi']) if data['ndvi'] else None,
                'avg_rainfall': sum(data['rainfall']) / len(data['rainfall']) if data['rainfall'] else None,
                'count': data['count'],
            }
        
        return result
    
    def get_trend_data(self, analyses):
        """Prepare data for trend charts"""
        trend_data = {
            'dates': [],
            'ndvi': [],
            'rainfall': [],
            'risk_scores': [],
        }
        
        for analysis in analyses:
            date_str = f"{analysis.year}-{analysis.month:02d}"
            trend_data['dates'].append(date_str)
            trend_data['ndvi'].append(analysis.ndvi or 0)
            trend_data['rainfall'].append(analysis.rainfall_mm or 0)
            trend_data['risk_scores'].append(analysis.risk_score or 0)
        
        return trend_data
    
    def get_risk_history(self, analyses):
        """Get risk level history"""
        return [
            {
                'date': f"{a.year}-{a.month:02d}",
                'risk': a.drought_risk_level,
                'color': a.risk_color,
                'score': a.risk_score,
            }
            for a in analyses[:12]  # Last 12 months
        ]


class FarmCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create new farm"""
    model = Farm
    form_class = FarmEditForm
    template_name = 'farms/farm_form.html'
    success_url = reverse_lazy('farm_list')
    
    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_farmer
    
    def form_valid(self, form):
        form.instance.farmer = self.request.user
        messages.success(self.request, 'Farm created successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class FarmUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update farm"""
    model = Farm
    form_class = FarmEditForm
    template_name = 'farms/farm_form.html'
    slug_field = 'farm_id'
    slug_url_kwarg = 'farm_id'
    
    def test_func(self):
        farm = self.get_object()
        return self.request.user.is_admin or farm.farmer == self.request.user
    
    def get_success_url(self):
        return reverse_lazy('farm_detail', kwargs={'farm_id': self.object.farm_id})
    
    def form_valid(self, form):
        messages.success(self.request, 'Farm updated successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class FarmDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete farm"""
    model = Farm
    template_name = 'farms/farm_confirm_delete.html'
    success_url = reverse_lazy('farm_list')
    slug_field = 'farm_id'
    slug_url_kwarg = 'farm_id'
    
    def test_func(self):
        return self.request.user.is_admin
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Farm deleted successfully!')
        return super().delete(request, *args, **kwargs)


# ======================
# INSURANCE VIEWS - FIXED
# ======================

class PolicyListView(LoginRequiredMixin, ListView):
    """List insurance policies - FIXED: Use created_at"""
    model = InsurancePolicy
    template_name = 'farms/policy_list.html'
    context_object_name = 'policies'
    paginate_by = 20
    
    def get_queryset(self):
        user = self.request.user
        queryset = InsurancePolicy.objects.select_related('farmer', 'farm')
        
        if user.is_farmer:
            queryset = queryset.filter(farmer=user)
        
        # Apply filters
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        
        policy_type = self.request.GET.get('policy_type', '')
        if policy_type:
            queryset = queryset.filter(policy_type=policy_type)
        
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(policy_number__icontains=search) |
                Q(farm__farm_id__icontains=search) |
                Q(farm__name__icontains=search)
            )
        
        # FIXED: Use created_at (this field exists in InsurancePolicy)
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'status_filter': self.request.GET.get('status', ''),
            'type_filter': self.request.GET.get('policy_type', ''),
            'search_query': self.request.GET.get('search', ''),
            'policy_statuses': InsurancePolicy.POLICY_STATUS,
            'policy_types': InsurancePolicy.POLICY_TYPES,
            'is_admin': user.is_admin,
            'can_create': user.is_admin or user.user_type == 'insurance_agent',
        })
        
        return context


class PolicyDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Policy details view"""
    model = InsurancePolicy
    template_name = 'farms/policy_detail.html'
    context_object_name = 'policy'
    
    def test_func(self):
        policy = self.get_object()
        user = self.request.user
        return user.is_admin or policy.farmer == user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        policy = self.object
        
        context.update({
            'claims': policy.claims.all().order_by('-trigger_date'),
            'farm_analyses': SatelliteAnalysis.objects.filter(farm=policy.farm).order_by('-analysis_date')[:12],
            'can_edit': self.request.user.is_admin,
            'can_claim': policy.is_active and (self.request.user.is_admin or policy.farmer == self.request.user),
        })
        
        return context


class PolicyCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create new insurance policy"""
    model = InsurancePolicy
    form_class = InsurancePolicyForm
    template_name = 'farms/policy_form.html'
    success_url = reverse_lazy('policy_list')
    
    def test_func(self):
        return self.request.user.is_admin or self.request.user.user_type == 'insurance_agent'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Insurance policy created successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class PolicyUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update insurance policy"""
    model = InsurancePolicy
    form_class = InsurancePolicyForm
    template_name = 'farms/policy_form.html'
    
    def test_func(self):
        return self.request.user.is_admin
    
    def get_success_url(self):
        return reverse_lazy('policy_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'Insurance policy updated successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class ClaimListView(LoginRequiredMixin, ListView):
    """List insurance claims - FIXED: Use created_at"""
    model = InsuranceClaim
    template_name = 'farms/claim_list.html'
    context_object_name = 'claims'
    paginate_by = 20
    
    def get_queryset(self):
        user = self.request.user
        queryset = InsuranceClaim.objects.select_related('policy', 'farm')
        
        if user.is_farmer:
            queryset = queryset.filter(policy__farmer=user)
        
        # Apply filters
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)
        
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(claim_number__icontains=search) |
                Q(policy__policy_number__icontains=search) |
                Q(farm__farm_id__icontains=search)
            )
        
        date_from = self.request.GET.get('date_from', '')
        if date_from:
            queryset = queryset.filter(trigger_date__gte=date_from)
        
        date_to = self.request.GET.get('date_to', '')
        if date_to:
            queryset = queryset.filter(trigger_date__lte=date_to)
        
        # FIXED: Use created_at (this field exists in InsuranceClaim)
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'status_filter': self.request.GET.get('status', ''),
            'search_query': self.request.GET.get('search', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
            'claim_statuses': InsuranceClaim.CLAIM_STATUS,
            'is_admin': user.is_admin,
            'can_create': user.is_admin or user.user_type == 'insurance_agent',
        })
        
        return context


class ClaimDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Claim details view"""
    model = InsuranceClaim
    template_name = 'farms/claim_detail.html'
    context_object_name = 'claim'
    
    def test_func(self):
        claim = self.get_object()
        user = self.request.user
        return user.is_admin or claim.policy.farmer == user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        claim = self.object
        
        context.update({
            'trigger_analysis': claim.triggered_by,
            'can_edit': claim.can_be_edited(self.request.user),
            'can_approve': self.request.user.is_admin,
            'can_pay': self.request.user.is_admin,
        })
        
        return context


class ClaimCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create new insurance claim"""
    model = InsuranceClaim
    form_class = InsuranceClaimForm
    template_name = 'farms/claim_form.html'
    success_url = reverse_lazy('claim_list')
    
    def test_func(self):
        return self.request.user.is_admin or self.request.user.user_type == 'insurance_agent'
    
    def get_initial(self):
        initial = super().get_initial()
        
        # Pre-fill from GET parameters
        policy_id = self.request.GET.get('policy')
        if policy_id:
            try:
                policy = InsurancePolicy.objects.get(pk=policy_id)
                initial['policy'] = policy
                initial['farm'] = policy.farm
            except InsurancePolicy.DoesNotExist:
                pass
        
        analysis_id = self.request.GET.get('analysis')
        if analysis_id:
            try:
                analysis = SatelliteAnalysis.objects.get(pk=analysis_id)
                initial['triggered_by'] = analysis
                initial['trigger_date'] = analysis.analysis_date
                initial['ndvi_value'] = analysis.ndvi
                initial['rainfall_value'] = analysis.rainfall_mm
                initial['risk_level'] = analysis.drought_risk_level
                
                # Calculate claim amount
                if initial.get('policy'):
                    initial['claimed_amount'] = initial['policy'].calculate_payout(analysis)
            except SatelliteAnalysis.DoesNotExist:
                pass
        
        return initial
    
    def form_valid(self, form):
        form.instance.submitted_by = self.request.user
        form.instance.submitted_date = timezone.now()
        
        # Set status to submitted
        if form.instance.status == 'draft':
            form.instance.status = 'submitted'
        
        messages.success(self.request, 'Insurance claim submitted successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class ClaimUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update insurance claim"""
    model = InsuranceClaim
    form_class = InsuranceClaimForm
    template_name = 'farms/claim_form.html'
    
    def test_func(self):
        claim = self.get_object()
        return claim.can_be_edited(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('claim_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        if form.instance.status == 'draft' and 'submit' in self.request.POST:
            form.instance.status = 'submitted'
            form.instance.submitted_date = timezone.now()
        
        messages.success(self.request, 'Claim updated successfully!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


@login_required
def approve_claim(request, pk):
    """Approve an insurance claim"""
    if not request.user.is_admin:
        raise PermissionDenied
    
    claim = get_object_or_404(InsuranceClaim, pk=pk)
    
    if request.method == 'POST':
        approved_amount = request.POST.get('approved_amount')
        notes = request.POST.get('review_notes', '')
        
        try:
            approved_amount = float(approved_amount)
            claim.approved_amount = approved_amount
            claim.status = 'approved'
            claim.reviewed_by = request.user
            claim.reviewed_date = timezone.now()
            claim.review_notes = notes
            claim.save()
            
            messages.success(request, f'Claim {claim.claim_number} approved!')
        except ValueError:
            messages.error(request, 'Invalid amount')
    
    return redirect('claim_detail', pk=claim.pk)


@login_required
def pay_claim(request, pk):
    """Mark claim as paid"""
    if not request.user.is_admin:
        raise PermissionDenied
    
    claim = get_object_or_404(InsuranceClaim, pk=pk)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        payment_reference = request.POST.get('payment_reference', '')
        
        claim.paid_amount = claim.approved_amount or claim.claimed_amount
        claim.status = 'paid'
        claim.paid_by = request.user
        claim.paid_date = date.today()
        claim.payment_method = payment_method
        claim.payment_reference = payment_reference
        claim.save()
        
        messages.success(request, f'Claim {claim.claim_number} marked as paid!')
    
    return redirect('claim_detail', pk=claim.pk)


# ======================
# GEE ANALYSIS VIEWS
# ======================

class SatelliteAnalysisView(LoginRequiredMixin, TemplateView):
    """Satellite analysis dashboard"""
    template_name = 'farms/satellite_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get available years (2018-2025)
        years = list(range(2018, 2026))
        
        # Months
        months = [
            {'id': 1, 'name': 'January'},
            {'id': 2, 'name': 'February'},
            {'id': 3, 'name': 'March'},
            {'id': 4, 'name': 'April'},
            {'id': 5, 'name': 'May'},
            {'id': 6, 'name': 'June'},
            {'id': 7, 'name': 'July'},
            {'id': 8, 'name': 'August'},
            {'id': 9, 'name': 'September'},
            {'id': 10, 'name': 'October'},
            {'id': 11, 'name': 'November'},
            {'id': 12, 'name': 'December'},
        ]
        
        # Indices
        indices = [
            {'id': 'NDVI', 'name': 'NDVI', 'description': 'Normalized Difference Vegetation Index'},
            {'id': 'EVI', 'name': 'EVI', 'description': 'Enhanced Vegetation Index'},
            {'id': 'NDMI', 'name': 'NDMI', 'description': 'Normalized Difference Moisture Index'},
            {'id': 'SAVI', 'name': 'SAVI', 'description': 'Soil Adjusted Vegetation Index'},
            {'id': 'NDRE', 'name': 'NDRE', 'description': 'Normalized Difference Red Edge'},
            {'id': 'BSI', 'name': 'BSI', 'description': 'Bare Soil Index'},
        ]
        
        # Get user's farms for selection
        if user.is_farmer:
            farms = Farm.objects.filter(farmer=user, is_active=True)
        else:
            farms = Farm.objects.filter(is_active=True)
        
        context.update({
            'years': years,
            'months': months,
            'indices': indices,
            'farms': farms,
            'current_year': date.today().year,
            'current_month': date.today().month,
            'is_admin': user.is_admin,
        })
        
        return context


@login_required
def run_single_analysis(request):
    """Run GEE analysis for a single farm"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            farm_id = data.get('farm_id')
            year = data.get('year', date.today().year)
            month = data.get('month', date.today().month)
            
            farm = get_object_or_404(Farm, farm_id=farm_id)
            
            # Check permissions
            user = request.user
            if not (user.is_admin or farm.farmer == user):
                raise PermissionDenied
            
            # Initialize GEE analyzer
            analyzer = WorkingGEEAnalyzer()
            
            # Run analysis
            result = analyzer.analyze_farm(farm, year, month)
            
            if result:
                # Save to database
                analysis = SatelliteAnalysis(
                    farm=farm,
                    analysis_date=date(year, month, 1),
                    year=year,
                    month=month,
                    ndvi=result.get('ndvi'),
                    ndmi=result.get('ndmi'),
                    bsi=result.get('bsi'),
                    evi=result.get('evi'),
                    savi=result.get('savi'),
                    ndre=result.get('ndre'),
                    rainfall_mm=result.get('rainfall_mm'),
                    image_count=result.get('image_count', 0),
                )
                analysis.save()
                
                return JsonResponse({
                    'success': True,
                    'analysis_id': analysis.id,
                    'farm_id': farm.farm_id,
                    'ndvi': analysis.ndvi,
                    'rainfall': analysis.rainfall_mm,
                    'risk_level': analysis.drought_risk_level,
                    'insurance_triggered': analysis.insurance_triggered,
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No satellite data available for this period',
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def run_batch_analysis(request):
    """Run batch analysis for multiple farms"""
    if not request.user.is_admin:
        raise PermissionDenied
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            farm_ids = data.get('farm_ids', [])
            year = data.get('year', date.today().year)
            month = data.get('month', date.today().month)
            
            if not farm_ids:
                return JsonResponse({
                    'success': False,
                    'error': 'No farm IDs provided'
                }, status=400)
            
            # Initialize GEE analyzer
            analyzer = WorkingGEEAnalyzer()
            
            # Get farms
            farms = Farm.objects.filter(farm_id__in=farm_ids, is_active=True)
            
            # Run batch analysis
            results = analyzer.analyze_all_farms(year, month)
            
            saved_analyses = []
            for result in results:
                try:
                    farm = Farm.objects.get(farm_id=result['farm_id'])
                    
                    analysis = SatelliteAnalysis(
                        farm=farm,
                        analysis_date=date(year, month, 1),
                        year=year,
                        month=month,
                        ndvi=result.get('ndvi'),
                        ndmi=result.get('ndmi'),
                        bsi=result.get('bsi'),
                        evi=result.get('evi'),
                        savi=result.get('savi'),
                        ndre=result.get('ndre'),
                        rainfall_mm=result.get('rainfall_mm'),
                        image_count=result.get('image_count', 0),
                    )
                    analysis.save()
                    
                    saved_analyses.append({
                        'farm_id': farm.farm_id,
                        'analysis_id': analysis.id,
                        'ndvi': analysis.ndvi,
                        'risk_level': analysis.drought_risk_level,
                    })
                    
                except Farm.DoesNotExist:
                    continue
            
            return JsonResponse({
                'success': True,
                'results': saved_analyses,
                'total': len(saved_analyses),
                'message': f'Analysis completed for {len(saved_analyses)} farms'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def get_analysis_data(request, farm_id):
    """Get analysis data for a farm"""
    farm = get_object_or_404(Farm, farm_id=farm_id)
    
    # Check permissions
    user = request.user
    if not (user.is_admin or farm.farmer == user):
        raise PermissionDenied
    
    # Get all analyses for this farm
    analyses = SatelliteAnalysis.objects.filter(farm=farm).order_by('year', 'month')
    
    data = {
        'farm': {
            'id': farm.farm_id,
            'name': farm.name,
            'crop': farm.crop_type,
            'area_ha': farm.area_ha,
            'farmer': farm.farmer.get_full_name(),
        },
        'analyses': [],
        'monthly_averages': {},
        'yearly_trends': {},
    }
    
    # Prepare time series data
    for analysis in analyses:
        data['analyses'].append({
            'date': f"{analysis.year}-{analysis.month:02d}",
            'year': analysis.year,
            'month': analysis.month,
            'month_name': analysis.month_name,
            'ndvi': analysis.ndvi,
            'evi': analysis.evi,
            'ndmi': analysis.ndmi,
            'savi': analysis.savi,
            'ndre': analysis.ndre,
            'bsi': analysis.bsi,
            'rainfall_mm': analysis.rainfall_mm,
            'risk_level': analysis.drought_risk_level,
            'risk_score': analysis.risk_score,
            'risk_color': analysis.risk_color,
            'insurance_triggered': analysis.insurance_triggered,
        })
    
    # Calculate monthly averages across years
    months = list(range(1, 13))
    for month in months:
        month_analyses = analyses.filter(month=month)
        if month_analyses.exists():
            data['monthly_averages'][month] = {
                'ndvi': month_analyses.aggregate(Avg('ndvi'))['ndvi__avg'],
                'rainfall': month_analyses.aggregate(Avg('rainfall_mm'))['rainfall_mm__avg'],
                'count': month_analyses.count(),
            }
    
    # Calculate yearly trends
    years = analyses.values_list('year', flat=True).distinct()
    for year in sorted(years):
        year_analyses = analyses.filter(year=year)
        if year_analyses.exists():
            data['yearly_trends'][year] = {
                'avg_ndvi': year_analyses.aggregate(Avg('ndvi'))['ndvi__avg'],
                'avg_rainfall': year_analyses.aggregate(Avg('rainfall_mm'))['rainfall_mm__avg'],
                'high_risk_months': year_analyses.filter(drought_risk_level='high').count(),
                'triggers': year_analyses.filter(insurance_triggered=True).count(),
            }
    
    return JsonResponse(data)


@login_required
def export_analysis_data(request):
    """Export analysis data to CSV"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            format_type = data.get('format', 'csv')
            farm_ids = data.get('farm_ids', [])
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            # Get analysis data
            analyses = SatelliteAnalysis.objects.all()
            
            if farm_ids:
                analyses = analyses.filter(farm__farm_id__in=farm_ids)
            
            if start_date:
                analyses = analyses.filter(analysis_date__gte=start_date)
            
            if end_date:
                analyses = analyses.filter(analysis_date__lte=end_date)
            
            # Limit to user's farms if not admin
            user = request.user
            if not user.is_admin:
                analyses = analyses.filter(farm__farmer=user)
            
            # Convert to requested format
            if format_type == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="analysis_export.csv"'
                
                writer = csv.writer(response)
                writer.writerow([
                    'Farm ID', 'Farm Name', 'Year', 'Month',
                    'NDVI', 'EVI', 'NDMI', 'SAVI', 'NDRE', 'BSI',
                    'Rainfall (mm)', 'Risk Score', 'Risk Level',
                    'Insurance Triggered', 'Trigger Reason'
                ])
                
                for analysis in analyses:
                    writer.writerow([
                        analysis.farm.farm_id,
                        analysis.farm.name or '',
                        analysis.year,
                        analysis.month,
                        analysis.ndvi or '',
                        analysis.evi or '',
                        analysis.ndmi or '',
                        analysis.savi or '',
                        analysis.ndre or '',
                        analysis.bsi or '',
                        analysis.rainfall_mm or '',
                        analysis.risk_score or '',
                        analysis.drought_risk_level,
                        'Yes' if analysis.insurance_triggered else 'No',
                        analysis.trigger_reason or ''
                    ])
                
                return response
                
            elif format_type == 'json':
                data = []
                for analysis in analyses:
                    data.append({
                        'farm_id': analysis.farm.farm_id,
                        'farm_name': analysis.farm.name,
                        'year': analysis.year,
                        'month': analysis.month,
                        'ndvi': analysis.ndvi,
                        'evi': analysis.evi,
                        'ndmi': analysis.ndmi,
                        'savi': analysis.savi,
                        'ndre': analysis.ndre,
                        'bsi': analysis.bsi,
                        'rainfall_mm': analysis.rainfall_mm,
                        'risk_score': analysis.risk_score,
                        'risk_level': analysis.drought_risk_level,
                        'insurance_triggered': analysis.insurance_triggered,
                        'trigger_reason': analysis.trigger_reason,
                    })
                
                return JsonResponse({'data': data}, safe=False)
            
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Unsupported format: {format_type}'
                }, status=400)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def trigger_insurance_check(request):
    """Check and trigger insurance claims based on analysis"""
    if not request.user.is_admin:
        raise PermissionDenied
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            analysis_id = data.get('analysis_id')
            
            analysis = get_object_or_404(SatelliteAnalysis, id=analysis_id)
            farm = analysis.farm
            
            # Check if insurance should be triggered
            if analysis.insurance_triggered:
                # Check for active policies
                active_policies = farm.policies.filter(status='active')
                
                claims_created = []
                for policy in active_policies:
                    # Check if claim already exists for this analysis
                    existing_claim = InsuranceClaim.objects.filter(
                        policy=policy,
                        triggered_by=analysis
                    ).exists()
                    
                    if not existing_claim:
                        # Calculate payout
                        payout_amount = policy.calculate_payout(analysis)
                        
                        if payout_amount > 0:
                            # Create claim
                            claim = InsuranceClaim(
                                policy=policy,
                                farm=farm,
                                triggered_by=analysis,
                                trigger_date=analysis.analysis_date,
                                claimed_amount=payout_amount,
                                ndvi_value=analysis.ndvi,
                                rainfall_value=analysis.rainfall_mm,
                                risk_level=analysis.drought_risk_level,
                                status='submitted',
                                submitted_by=request.user,
                                submitted_date=timezone.now(),
                            )
                            claim.save()
                            
                            claims_created.append({
                                'claim_number': claim.claim_number,
                                'policy_number': policy.policy_number,
                                'amount': float(payout_amount),
                            })
                
                if claims_created:
                    return JsonResponse({
                        'success': True,
                        'claims_created': True,
                        'claims': claims_created,
                        'message': f'{len(claims_created)} insurance claim(s) created',
                    })
                else:
                    return JsonResponse({
                        'success': True,
                        'claims_created': False,
                        'message': 'Insurance triggered but no active policies found or claims already exist',
                    })
            else:
                return JsonResponse({
                    'success': True,
                    'claims_created': False,
                    'message': 'Insurance thresholds not met',
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def test_gee_connection(request):
    """Test GEE API connection"""
    success = test_working_gee()
    
    return JsonResponse({
        'success': success,
        'message': 'GEE connection test completed',
        'timestamp': timezone.now().isoformat(),
    })


# ======================
# NOTIFICATION VIEWS
# ======================

@login_required
def notifications(request):
    """View notifications"""
    notifications = request.user.notifications.all().order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    
    return render(request, 'farms/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.mark_as_read()
    
    return JsonResponse({'success': True})


@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    request.user.notifications.filter(is_read=False).update(
        is_read=True,
        read_at=timezone.now()
    )
    
    return JsonResponse({'success': True})


# ======================
# MAP VIEW
# ======================

class MapView(LoginRequiredMixin, TemplateView):
    """Interactive map view"""
    template_name = 'farms/map_viewer.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get farms for display
        if user.is_farmer:
            farms = Farm.objects.filter(farmer=user, is_active=True)
        else:
            farms = Farm.objects.filter(is_active=True)
        
        # Prepare farm data for map
        farm_data = []
        for farm in farms.select_related('farmer', 'county'):
            latest_analysis = farm.get_latest_analysis()
            
            farm_data.append({
                'id': farm.farm_id,
                'name': farm.name or f'Farm {farm.farm_id}',
                'farmer': farm.farmer.get_full_name(),
                'crop': farm.crop_type,
                'area_ha': farm.area_ha,
                'latitude': farm.latitude,
                'longitude': farm.longitude,
                'risk_level': latest_analysis.drought_risk_level if latest_analysis else 'unknown',
                'risk_color': latest_analysis.risk_color if latest_analysis else 'secondary',
                'ndvi': latest_analysis.ndvi if latest_analysis else None,
                'rainfall': latest_analysis.rainfall_mm if latest_analysis else None,
                'insurance_triggered': latest_analysis.insurance_triggered if latest_analysis else False,
                'has_policy': farm.policies.filter(status='active').exists(),
            })
        
        # Get counties for overlay
        counties = County.objects.all()
        county_data = []
        for county in counties:
            county_data.append({
                'name': county.subcounty,
                'risk_level': county.drought_risk_level,
                'avg_rainfall': county.avg_rainfall,
                'farm_count': county.farm_count,
            })
        
        context.update({
            'farm_data_json': json.dumps(farm_data),
            'county_data_json': json.dumps(county_data),
            'total_farms': farms.count(),
            'map_center_lat': -1.5167,  # Machakos center
            'map_center_lng': 37.2667,
            'map_default_zoom': 10,
            'is_admin': user.is_admin,
        })
        
        return context


# ======================
# API ENDPOINTS
# ======================

@login_required
def api_farm_analysis(request, farm_id):
    """API endpoint for farm analysis data"""
    farm = get_object_or_404(Farm, farm_id=farm_id)
    
    # Check permissions
    user = request.user
    if not (user.is_admin or farm.farmer == user):
        raise PermissionDenied
    
    analyses = SatelliteAnalysis.objects.filter(farm=farm).order_by('-analysis_date')[:12]
    
    data = {
        'farm': {
            'id': farm.farm_id,
            'name': farm.name,
            'crop': farm.crop_type,
            'area': farm.area_ha,
            'location': {
                'lat': farm.latitude,
                'lng': farm.longitude,
            }
        },
        'analyses': [
            {
                'date': f"{a.year}-{a.month:02d}",
                'ndvi': a.ndvi,
                'rainfall': a.rainfall_mm,
                'risk': a.drought_risk_level,
                'risk_score': a.risk_score,
            }
            for a in analyses
        ]
    }
    
    return JsonResponse(data)


@login_required
def api_dashboard_stats(request):
    """API endpoint for dashboard statistics"""
    user = request.user
    
    if user.is_admin:
        stats = {
            'farmers': CustomUser.objects.filter(user_type='farmer').count(),
            'farms': Farm.objects.filter(is_active=True).count(),
            'active_policies': InsurancePolicy.objects.filter(status='active').count(),
            'pending_claims': InsuranceClaim.objects.filter(status__in=['submitted', 'under_review']).count(),
            'total_payout': InsuranceClaim.objects.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
        }
    else:
        stats = {
            'farms': Farm.objects.filter(farmer=user, is_active=True).count(),
            'active_policies': InsurancePolicy.objects.filter(farmer=user, status='active').count(),
            'pending_claims': InsuranceClaim.objects.filter(policy__farmer=user, status__in=['submitted', 'under_review']).count(),
            'total_received': InsuranceClaim.objects.filter(policy__farmer=user, status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
            'unread_notifications': user.notifications.filter(is_read=False).count(),
        }
    
    return JsonResponse(stats)