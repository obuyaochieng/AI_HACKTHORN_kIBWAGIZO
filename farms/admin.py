from django.contrib import admin
from django.contrib.gis.admin import OSMGeoAdmin
from leaflet.admin import LeafletGeoAdmin
from .models import County, Farmer, Farm, SatelliteAnalysis, InsurancePolicy, InsuranceClaim


@admin.register(County)
class CountyAdmin(LeafletGeoAdmin):
    list_display = ('county', 'subcounty', 'county_code', 'subcounty_code')
    list_filter = ('county',)
    search_fields = ('county', 'subcounty')
    ordering = ('county', 'subcounty')


@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'national_id', 'phone_number', 'subcounty')
    list_filter = ('gender', 'subcounty')
    search_fields = ('first_name', 'last_name', 'national_id', 'phone_number')
    ordering = ('last_name', 'first_name')


@admin.register(Farm)
class FarmAdmin(LeafletGeoAdmin):
    list_display = ('farm_id', 'name', 'farmer', 'crop_type', 'area_ha', 'is_active')
    list_filter = ('crop_type', 'is_active', 'county', 'irrigation')
    search_fields = ('farm_id', 'name', 'farmer__first_name', 'farmer__last_name')
    ordering = ('farm_id',)
    
    # Make geometry fields editable on map
    settings_overrides = {
        'DEFAULT_CENTER': (-1.5167, 37.2667),  # Machakos center
        'DEFAULT_ZOOM': 10,
    }


@admin.register(SatelliteAnalysis)
class SatelliteAnalysisAdmin(admin.ModelAdmin):
    list_display = ('farm', 'year', 'month', 'ndvi', 'rainfall_mm', 'drought_risk_level', 'insurance_triggered')
    list_filter = ('year', 'month', 'drought_risk_level', 'insurance_triggered')
    search_fields = ('farm__farm_id', 'farm__name')
    ordering = ('-year', '-month', 'farm')
    
    readonly_fields = ('analysis_timestamp',)


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('policy_number', 'farm', 'farmer', 'sum_insured', 'coverage_start', 'coverage_end', 'status')
    list_filter = ('status', 'coverage_start', 'coverage_end')
    search_fields = ('policy_number', 'farm__farm_id', 'farmer__first_name', 'farmer__last_name')
    ordering = ('-coverage_start',)
    
    readonly_fields = ('created_date', 'last_updated')


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_number', 'policy', 'farm', 'trigger_date', 'claim_amount', 'status')
    list_filter = ('status', 'trigger_date')
    search_fields = ('claim_number', 'policy__policy_number', 'farm__farm_id')
    ordering = ('-trigger_date',)
    
    readonly_fields = ('submitted_date', 'claim_number')