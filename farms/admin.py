# farms/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

from .models import (
    CustomUser, UserProfile, County, Farm, 
    SatelliteAnalysis, InsurancePolicy, InsuranceClaim,
    Notification, GEEExportTask
)
from .forms import CustomUserCreationForm, CustomUserChangeForm


class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('date_of_birth', 'gender')
        }),
        ('Address', {
            'fields': ('physical_address', 'postal_address', 'postal_code')
        }),
        ('Banking Details', {
            'fields': ('bank_name', 'bank_branch', 'account_name', 'account_number')
        }),
        ('Mobile Money', {
            'fields': ('mpesa_number', 'mpesa_name')
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship')
        }),
        ('Verification', {
            'fields': ('id_document', 'id_number', 'verification_status')
        }),
        ('Notification Settings', {
            'fields': ('email_notifications', 'sms_notifications', 'push_notifications')
        }),
    )


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin interface for CustomUser"""
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    inlines = [UserProfileInline]
    
    list_display = ('username', 'email', 'first_name', 'last_name', 
                   'user_type', 'is_verified', 'is_active', 'date_joined')
    list_filter = ('user_type', 'is_verified', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'national_id', 'phone')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'national_id', 'profile_picture')}),
        ('User Type', {'fields': ('user_type',)}),
        ('Location', {'fields': ('county', 'subcounty', 'ward', 'village')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 
                                   'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
        ('Verification', {'fields': ('is_verified', 'verification_date')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'phone', 'national_id',
                      'first_name', 'last_name', 'user_type',
                      'password1', 'password2'),
        }),
    )
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)
    
    def verify_user(self, request, queryset):
        """Action to verify selected users"""
        updated = queryset.update(is_verified=True, verification_date=timezone.now())
        self.message_user(request, f'{updated} users verified successfully.', messages.SUCCESS)
    
    verify_user.short_description = "Verify selected users"
    
    actions = [verify_user]


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ('subcounty', 'county_name', 'drought_risk_level', 
                   'avg_rainfall', 'farm_count', 'farmer_count')
    list_filter = ('county_name', 'drought_risk_level')
    search_fields = ('subcounty', 'county_name', 'subcounty_code')
    ordering = ('county_name', 'subcounty')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('county_name', 'subcounty', 'subcounty_code')
        }),
        ('Location Data', {
            'fields': ('geometry_geojson', 'centroid_lat', 'centroid_lng')
        }),
        ('Environmental Data', {
            'fields': ('avg_rainfall', 'avg_temperature', 'soil_type', 'elevation')
        }),
        ('Risk Assessment', {
            'fields': ('drought_risk_level',)
        }),
    )
    
    readonly_fields = ('farm_count', 'farmer_count')
    
    def farm_count(self, obj):
        return obj.farm_count
    farm_count.short_description = 'Number of Farms'
    
    def farmer_count(self, obj):
        return obj.farmer_count
    farmer_count.short_description = 'Number of Farmers'


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('farm_id', 'name', 'farmer_link', 'county', 
                   'crop_type', 'area_ha', 'is_active', 'registration_date')
    list_filter = ('crop_type', 'is_active', 'county', 'irrigation', 'registration_date')
    search_fields = ('farm_id', 'name', 'farmer__username', 'farmer__first_name', 
                    'farmer__last_name', 'crop_type')
    ordering = ('-registration_date',)
    
    fieldsets = (
        ('Farm Identification', {
            'fields': ('farm_id', 'name', 'farmer', 'county')
        }),
        ('Location & Area', {
            'fields': ('latitude', 'longitude', 'area_ha', 'elevation',
                      'geometry_geojson', 'boundary_coordinates')
        }),
        ('Crop Information', {
            'fields': ('crop_type', 'crop_variety', 'planting_date', 
                      'expected_harvest_date', 'expected_yield')
        }),
        ('Soil & Water', {
            'fields': ('soil_type', 'soil_ph', 'irrigation', 'irrigation_type')
        }),
        ('Management', {
            'fields': ('cooperative', 'farm_manager', 'contact_phone')
        }),
        ('Status & GEE', {
            'fields': ('is_active', 'gee_asset_id', 'has_gee_data')
        }),
    )
    
    readonly_fields = ('farm_id', 'registration_date', 'last_updated')
    
    def farmer_link(self, obj):
        if obj.farmer:
            url = reverse('admin:farms_customuser_change', args=[obj.farmer.id])
            return format_html('<a href="{}">{}</a>', url, obj.farmer.get_full_name())
        return '-'
    farmer_link.short_description = 'Farmer'
    farmer_link.admin_order_field = 'farmer__first_name'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('farmer', 'county')
        return queryset


@admin.register(SatelliteAnalysis)
class SatelliteAnalysisAdmin(admin.ModelAdmin):
    list_display = ('farm', 'analysis_date', 'year', 'month', 
                   'ndvi', 'rainfall_mm', 'drought_risk_level', 
                   'insurance_triggered', 'created_at')
    list_filter = ('year', 'month', 'drought_risk_level', 
                  'insurance_triggered', 'created_at')
    search_fields = ('farm__farm_id', 'farm__name', 'farm__farmer__username')
    ordering = ('-analysis_date', '-created_at')
    
    fieldsets = (
        ('Farm & Date', {
            'fields': ('farm', 'analysis_date', 'year', 'month')
        }),
        ('Vegetation Indices', {
            'fields': ('ndvi', 'evi', 'ndmi', 'savi', 'ndre', 'bsi')
        }),
        ('Environmental Data', {
            'fields': ('land_surface_temp', 'soil_moisture', 
                      'rainfall_mm', 'rainfall_anomaly')
        }),
        ('Health Assessment', {
            'fields': ('vegetation_health', 'moisture_stress')
        }),
        ('Risk Assessment', {
            'fields': ('drought_risk_level', 'risk_score')
        }),
        ('Insurance', {
            'fields': ('insurance_triggered', 'trigger_reason')
        }),
        ('Analysis Metadata', {
            'fields': ('cloud_cover_percentage', 'image_count', 
                      'gee_task_id', 'analysis_duration')
        }),
    )
    
    readonly_fields = ('analysis_date', 'vegetation_health', 'moisture_stress',
                      'drought_risk_level', 'risk_score', 'insurance_triggered',
                      'trigger_reason', 'created_at', 'updated_at')
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('farm', 'farm__farmer')
        return queryset


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('policy_number', 'farmer_link', 'farm_link', 
                   'policy_type', 'sum_insured', 'premium_amount',
                   'coverage_start', 'coverage_end', 'status', 'is_active_display')
    list_filter = ('policy_type', 'status', 'coverage_start', 'coverage_end', 'created_at')
    search_fields = ('policy_number', 'farmer__username', 'farmer__first_name',
                    'farmer__last_name', 'farm__farm_id', 'farm__name')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Policy Information', {
            'fields': ('policy_number', 'farmer', 'farm', 'policy_type')
        }),
        ('Coverage Period', {
            'fields': ('coverage_start', 'coverage_end')
        }),
        ('Financial Details', {
            'fields': ('sum_insured', 'premium_amount', 'premium_rate',
                      'max_payout', 'deductible', 'payout_rate')
        }),
        ('Trigger Parameters', {
            'fields': ('ndvi_trigger', 'rainfall_trigger', 'risk_level_trigger')
        }),
        ('Status & Payment', {
            'fields': ('status', 'is_auto_renew', 'payment_method',
                      'payment_reference', 'payment_date')
        }),
        ('Documents', {
            'fields': ('policy_document', 'terms_document')
        }),
        ('Administration', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )
    
    readonly_fields = ('policy_number', 'premium_amount', 'created_at', 'updated_at')
    
    def farmer_link(self, obj):
        if obj.farmer:
            url = reverse('admin:farms_customuser_change', args=[obj.farmer.id])
            return format_html('<a href="{}">{}</a>', url, obj.farmer.get_full_name())
        return '-'
    farmer_link.short_description = 'Farmer'
    farmer_link.admin_order_field = 'farmer__first_name'
    
    def farm_link(self, obj):
        if obj.farm:
            url = reverse('admin:farms_farm_change', args=[obj.farm.id])
            return format_html('<a href="{}">{}</a>', url, obj.farm.farm_id)
        return '-'
    farm_link.short_description = 'Farm'
    farm_link.admin_order_field = 'farm__farm_id'
    
    def is_active_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Active</span>')
        else:
            return format_html('<span style="color: red;">✗ Inactive</span>')
    is_active_display.short_description = 'Active'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('farmer', 'farm', 'created_by')
        return queryset


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_number', 'policy_link', 'farm_link', 
                   'trigger_date', 'claimed_amount', 'approved_amount',
                   'status_display', 'submitted_date', 'paid_date')
    list_filter = ('status', 'trigger_date', 'submitted_date', 'paid_date')
    search_fields = ('claim_number', 'policy__policy_number', 
                    'farm__farm_id', 'farm__name')
    ordering = ('-trigger_date', '-submitted_date')
    
    fieldsets = (
        ('Claim Information', {
            'fields': ('claim_number', 'policy', 'farm', 'triggered_by')
        }),
        ('Claim Details', {
            'fields': ('trigger_date', 'claimed_amount', 'approved_amount', 'paid_amount')
        }),
        ('Evidence', {
            'fields': ('ndvi_value', 'rainfall_value', 'risk_level',
                      'satellite_image_url', 'gee_analysis_link', 'field_photos')
        }),
        ('Documents', {
            'fields': ('claim_form', 'supporting_docs')
        }),
        ('Processing', {
            'fields': ('status', 'submitted_by', 'submitted_date',
                      'reviewed_by', 'reviewed_date', 'review_notes',
                      'paid_by', 'paid_date', 'payment_reference', 'payment_method')
        }),
        ('Farmer Feedback', {
            'fields': ('farmer_feedback', 'farmer_rating')
        }),
    )
    
    readonly_fields = ('claim_number', 'submitted_date', 'created_at', 'updated_at')
    
    def policy_link(self, obj):
        if obj.policy:
            url = reverse('admin:farms_insurancepolicy_change', args=[obj.policy.id])
            return format_html('<a href="{}">{}</a>', url, obj.policy.policy_number)
        return '-'
    policy_link.short_description = 'Policy'
    policy_link.admin_order_field = 'policy__policy_number'
    
    def farm_link(self, obj):
        if obj.farm:
            url = reverse('admin:farms_farm_change', args=[obj.farm.id])
            return format_html('<a href="{}">{}</a>', url, obj.farm.farm_id)
        return '-'
    farm_link.short_description = 'Farm'
    farm_link.admin_order_field = 'farm__farm_id'
    
    def status_display(self, obj):
        colors = {
            'draft': 'secondary',
            'submitted': 'info',
            'under_review': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'paid': 'success',
            'closed': 'dark',
        }
        color = colors.get(obj.status, 'secondary')
        return format_html('<span class="badge badge-{}">{}</span>', color, obj.get_status_display())
    status_display.short_description = 'Status'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('policy', 'farm', 'triggered_by',
                                          'submitted_by', 'reviewed_by', 'paid_by')
        return queryset


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 
                   'is_read', 'created_at', 'related_farm')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message', 
                    'related_farm__farm_id', 'related_farm__name')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('user', 'notification_type', 'title', 'message', 'is_read')
        }),
        ('Related Objects', {
            'fields': ('related_farm', 'related_policy', 
                      'related_claim', 'related_analysis')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'read_at')
        }),
    )
    
    readonly_fields = ('created_at', 'read_at')
    
    def mark_as_read(self, request, queryset):
        """Action to mark notifications as read"""
        for notification in queryset:
            notification.mark_as_read()
        self.message_user(request, f'{queryset.count()} notifications marked as read.', messages.SUCCESS)
    
    mark_as_read.short_description = "Mark selected notifications as read"
    
    actions = [mark_as_read]


@admin.register(GEEExportTask)
class GEEExportTaskAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'task_type', 'year', 'month', 
                   'status_display', 'progress_percentage', 
                   'records_processed', 'created_at', 'duration')
    list_filter = ('task_type', 'status', 'created_at')
    search_fields = ('task_id', 'description', 'status_message')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Task Information', {
            'fields': ('task_id', 'task_type', 'description')
        }),
        ('Parameters', {
            'fields': ('parameters', 'year', 'month')
        }),
        ('Results', {
            'fields': ('result_url', 'result_size', 'records_processed')
        }),
        ('Status', {
            'fields': ('status', 'status_message', 'progress_percentage')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        ('Created By', {
            'fields': ('created_by', 'created_at')
        }),
    )
    
    readonly_fields = ('task_id', 'created_at', 'started_at', 'completed_at', 
                      'duration_seconds', 'records_processed')
    
    def status_display(self, obj):
        colors = {
            'pending': 'secondary',
            'running': 'info',
            'completed': 'success',
            'failed': 'danger',
            'cancelled': 'warning',
        }
        color = colors.get(obj.status, 'secondary')
        return format_html('<span class="badge badge-{}">{}</span>', color, obj.get_status_display())
    status_display.short_description = 'Status'
    
    def duration(self, obj):
        if obj.duration_seconds:
            return f"{obj.duration_seconds:.1f}s"
        return '-'
    duration.short_description = 'Duration'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('created_by')
        return queryset