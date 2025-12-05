# farms/models.py
from django.db import models
from django.contrib.auth.models import User, AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
import os
import uuid
from django.conf import settings
import json
from datetime import date
from django.core.exceptions import ValidationError

class CustomUser(AbstractUser):
    """Extended User model with user type"""
    USER_TYPES = [
        ('admin', 'Administrator'),
        ('farmer', 'Farmer'),
        ('insurance_agent', 'Insurance Agent'),
        ('analyst', 'Data Analyst'),
    ]
    
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='farmer')
    phone = models.CharField(max_length=20, blank=True)
    national_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    # Location
    county = models.CharField(max_length=100, blank=True)
    subcounty = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    
    # Metadata
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_user_type_display()})"
    
    @property
    def is_farmer(self):
        return self.user_type == 'farmer'
    
    @property
    def is_admin(self):
        return self.user_type == 'admin'
    
    def get_farm_count(self):
        if self.is_farmer:
            return self.farms.count()
        return 0
    
    def get_active_policies(self):
        return self.policies.filter(status='active').count()


class County(models.Model):
    """Machakos County and sub-counties"""
    county_name = models.CharField(max_length=100, default='Machakos')
    subcounty = models.CharField(max_length=100, unique=True)
    subcounty_code = models.CharField(max_length=50, unique=True)
    
    # Geometry data
    geometry_geojson = models.TextField(blank=True, null=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lng = models.FloatField(null=True, blank=True)
    
    # Analysis parameters
    avg_rainfall = models.FloatField(null=True, blank=True, help_text="Average annual rainfall in mm")
    avg_temperature = models.FloatField(null=True, blank=True, help_text="Average temperature in °C")
    soil_type = models.CharField(max_length=100, blank=True)
    elevation = models.FloatField(null=True, blank=True, help_text="Average elevation in meters")
    
    # Risk assessment
    drought_risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low Risk'),
        ('moderate', 'Moderate Risk'),
        ('high', 'High Risk'),
        ('very_high', 'Very High Risk'),
    ], default='moderate')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Counties"
        ordering = ['subcounty']
    
    def __str__(self):
        return f"{self.county_name} - {self.subcounty}"
    
    @property
    def farm_count(self):
        return self.farms.count()
    
    @property
    def farmer_count(self):
        return CustomUser.objects.filter(user_type='farmer', subcounty=self.subcounty).count()


class Farm(models.Model):
    """Farm information"""
    CROP_CHOICES = [
        ('maize', 'Maize'),
        ('beans', 'Beans'),
        ('wheat', 'Wheat'),
        ('potatoes', 'Potatoes'),
        ('vegetables', 'Vegetables'),
        ('coffee', 'Coffee'),
        ('tea', 'Tea'),
        ('other', 'Other'),
    ]
    
    # Farm identification
    farm_id = models.CharField(max_length=50, unique=True, primary_key=True)
    name = models.CharField(max_length=200, blank=True)
    farmer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='farms', limit_choices_to={'user_type': 'farmer'})
    
    # Location
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='farms')
    latitude = models.FloatField()
    longitude = models.FloatField()
    area_ha = models.FloatField(validators=[MinValueValidator(0.1)], help_text="Area in hectares")
    elevation = models.FloatField(null=True, blank=True)
    
    # Geometry data
    geometry_geojson = models.TextField(blank=True, null=True)
    boundary_coordinates = models.TextField(blank=True, null=True, help_text="JSON array of boundary coordinates")
    
    # Crop information
    crop_type = models.CharField(max_length=50, choices=CROP_CHOICES, default='maize')
    crop_variety = models.CharField(max_length=100, blank=True)
    planting_date = models.DateField(null=True, blank=True)
    expected_harvest_date = models.DateField(null=True, blank=True)
    expected_yield = models.FloatField(null=True, blank=True, help_text="Expected yield in tons")
    
    # Soil and water
    soil_type = models.CharField(max_length=100, blank=True)
    soil_ph = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(14)])
    irrigation = models.BooleanField(default=False)
    irrigation_type = models.CharField(max_length=50, blank=True, choices=[
        ('drip', 'Drip'),
        ('sprinkler', 'Sprinkler'),
        ('flood', 'Flood'),
        ('rainfed', 'Rain-fed'),
    ])
    
    # Management
    cooperative = models.CharField(max_length=200, blank=True)
    farm_manager = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    registration_date = models.DateField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    # GEE Integration
    gee_asset_id = models.CharField(max_length=500, blank=True, 
                                   help_text="GEE Asset ID for this farm")
    has_gee_data = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['farm_id']
        indexes = [
            models.Index(fields=['farm_id']),
            models.Index(fields=['farmer']),
            models.Index(fields=['county']),
            models.Index(fields=['crop_type']),
        ]
    
    def __str__(self):
        return f"{self.farm_id} - {self.name or 'Unnamed Farm'}"
    
    def clean(self):
        if self.expected_harvest_date and self.planting_date:
            if self.expected_harvest_date <= self.planting_date:
                raise ValidationError('Harvest date must be after planting date')
    
    def save(self, *args, **kwargs):
        if not self.farm_id:
            # Generate farm ID: FARM-YYYY-MM-XXXX
            year_month = date.today().strftime('%Y-%m')
            last_farm = Farm.objects.filter(farm_id__startswith=f'FARM-{year_month}').order_by('farm_id').last()
            if last_farm:
                last_num = int(last_farm.farm_id.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.farm_id = f'FARM-{year_month}-{new_num:04d}'
        
        super().save(*args, **kwargs)
    
    @property
    def centroid(self):
        """Return centroid as dictionary"""
        return {'lat': self.latitude, 'lng': self.longitude}
    
    @property
    def crop_days(self):
        """Days since planting"""
        if self.planting_date:
            return (date.today() - self.planting_date).days
        return None
    
    @property
    def days_to_harvest(self):
        """Days until expected harvest"""
        if self.expected_harvest_date:
            return (self.expected_harvest_date - date.today()).days
        return None
    
    def get_latest_analysis(self):
        """Get latest satellite analysis"""
        return self.analyses.order_by('-analysis_date').first()
    
    def get_risk_level(self):
        """Get current risk level"""
        latest = self.get_latest_analysis()
        return latest.drought_risk_level if latest else 'unknown'


class SatelliteAnalysis(models.Model):
    """Satellite-based indices analysis"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='analyses')
    
    # Time period
    analysis_date = models.DateField()
    year = models.IntegerField()
    month = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    
    # Sentinel-2 Indices (from GEE)
    ndvi = models.FloatField(null=True, blank=True, help_text="Normalized Difference Vegetation Index")
    evi = models.FloatField(null=True, blank=True, help_text="Enhanced Vegetation Index")
    ndmi = models.FloatField(null=True, blank=True, help_text="Normalized Difference Moisture Index")
    savi = models.FloatField(null=True, blank=True, help_text="Soil Adjusted Vegetation Index")
    ndre = models.FloatField(null=True, blank=True, help_text="Normalized Difference Red Edge")
    bsi = models.FloatField(null=True, blank=True, help_text="Bare Soil Index")
    
    # Additional GEE data
    land_surface_temp = models.FloatField(null=True, blank=True, help_text="Land Surface Temperature in °C")
    soil_moisture = models.FloatField(null=True, blank=True, help_text="Soil Moisture Index")
    
    # Rainfall data
    rainfall_mm = models.FloatField(null=True, blank=True, help_text="Total rainfall in mm for period")
    rainfall_anomaly = models.FloatField(null=True, blank=True, help_text="Rainfall anomaly from average")
    
    # Crop health classification
    vegetation_health = models.CharField(max_length=20, choices=[
        ('excellent', 'Excellent (NDVI > 0.6)'),
        ('good', 'Good (NDVI 0.4-0.6)'),
        ('moderate', 'Moderate (NDVI 0.3-0.4)'),
        ('poor', 'Poor (NDVI 0.2-0.3)'),
        ('critical', 'Critical (NDVI < 0.2)'),
    ], blank=True)
    
    moisture_stress = models.CharField(max_length=20, choices=[
        ('none', 'No Stress'),
        ('mild', 'Mild Stress'),
        ('moderate', 'Moderate Stress'),
        ('severe', 'Severe Stress'),
    ], blank=True)
    
    # Drought risk assessment
    drought_risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low Risk'),
        ('moderate', 'Moderate Risk'),
        ('high', 'High Risk'),
    ], default='low')
    
    risk_score = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Insurance trigger
    insurance_triggered = models.BooleanField(default=False)
    trigger_reason = models.TextField(blank=True, help_text="Reason for insurance trigger")
    
    # Analysis metadata
    cloud_cover_percentage = models.FloatField(null=True, blank=True)
    image_count = models.IntegerField(default=0)
    gee_task_id = models.CharField(max_length=100, blank=True, help_text="GEE Task ID for this analysis")
    analysis_duration = models.FloatField(null=True, blank=True, help_text="Analysis duration in seconds")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Satellite Analyses"
        ordering = ['-analysis_date', 'farm']
        unique_together = ['farm', 'year', 'month']
        indexes = [
            models.Index(fields=['farm', 'analysis_date']),
            models.Index(fields=['drought_risk_level']),
            models.Index(fields=['insurance_triggered']),
        ]
    
    def __str__(self):
        return f"{self.farm.farm_id} - {self.year}-{self.month:02d} - {self.drought_risk_level}"
    
    def calculate_risk_score(self):
        """Calculate comprehensive risk score (0-100)"""
        score = 0
        
        # NDVI contributes 40%
        if self.ndvi is not None:
            if self.ndvi < 0.2:
                score += 40
            elif self.ndvi < 0.3:
                score += 30
            elif self.ndvi < 0.4:
                score += 20
            elif self.ndvi < 0.6:
                score += 10
        
        # Rainfall contributes 30%
        if self.rainfall_mm is not None:
            if self.rainfall_mm < 25:
                score += 30
            elif self.rainfall_mm < 50:
                score += 20
            elif self.rainfall_mm < 75:
                score += 10
        
        # NDMI contributes 20%
        if self.ndmi is not None:
            if self.ndmi < 0:
                score += 20
            elif self.ndmi < 0.2:
                score += 10
        
        # BSI contributes 10%
        if self.bsi is not None:
            if self.bsi > 0.3:
                score += 10
        
        return min(score, 100)
    
    def save(self, *args, **kwargs):
        # Auto-calculate vegetation health
        if self.ndvi is not None:
            if self.ndvi > 0.6:
                self.vegetation_health = 'excellent'
            elif self.ndvi > 0.4:
                self.vegetation_health = 'good'
            elif self.ndvi > 0.3:
                self.vegetation_health = 'moderate'
            elif self.ndvi > 0.2:
                self.vegetation_health = 'poor'
            else:
                self.vegetation_health = 'critical'
        
        # Auto-calculate moisture stress
        if self.ndmi is not None:
            if self.ndmi > 0.2:
                self.moisture_stress = 'none'
            elif self.ndmi > 0.1:
                self.moisture_stress = 'mild'
            elif self.ndmi > 0:
                self.moisture_stress = 'moderate'
            else:
                self.moisture_stress = 'severe'
        
        # Calculate risk score
        self.risk_score = self.calculate_risk_score()
        
        # Determine risk level
        if self.risk_score >= 70:
            self.drought_risk_level = 'high'
        elif self.risk_score >= 40:
            self.drought_risk_level = 'moderate'
        else:
            self.drought_risk_level = 'low'
        
        # Check insurance triggers
        self.check_insurance_trigger()
        
        super().save(*args, **kwargs)
    
    def check_insurance_trigger(self):
        """Check if insurance should be triggered"""
        triggers = []
        
        # NDVI threshold
        ndvi_threshold = float(os.getenv('NDVI_THRESHOLD_SEVERE', 0.3))
        if self.ndvi is not None and self.ndvi < ndvi_threshold:
            triggers.append(f"NDVI ({self.ndvi:.2f}) below threshold ({ndvi_threshold})")
        
        # Rainfall threshold
        rainfall_threshold = float(os.getenv('RAINFALL_THRESHOLD_MM', 50))
        if self.rainfall_mm is not None and self.rainfall_mm < rainfall_threshold:
            triggers.append(f"Rainfall ({self.rainfall_mm:.1f}mm) below threshold ({rainfall_threshold}mm)")
        
        # Risk level
        if self.drought_risk_level in ['moderate', 'high']:
            triggers.append(f"Drought risk level: {self.drought_risk_level}")
        
        if triggers:
            self.insurance_triggered = True
            self.trigger_reason = "; ".join(triggers)
        else:
            self.insurance_triggered = False
            self.trigger_reason = ""
    
    @property
    def risk_color(self):
        """Get color for risk level"""
        colors = {
            'low': 'success',
            'moderate': 'warning',
            'high': 'danger',
        }
        return colors.get(self.drought_risk_level, 'secondary')
    
    @property
    def month_name(self):
        """Get month name"""
        from datetime import datetime
        return datetime(2000, self.month, 1).strftime('%B')


class InsurancePolicy(models.Model):
    """Insurance policy for farms"""
    POLICY_STATUS = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('claimed', 'Claim Made'),
        ('cancelled', 'Cancelled'),
    ]
    
    POLICY_TYPES = [
        ('drought', 'Drought Insurance'),
        ('crop_failure', 'Crop Failure Insurance'),
        ('comprehensive', 'Comprehensive Coverage'),
        ('rainfall_index', 'Rainfall Index Insurance'),
        ('vegetation_index', 'Vegetation Index Insurance'),
    ]
    
    # Policy identification
    policy_number = models.CharField(max_length=50, unique=True)
    farmer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='policies', limit_choices_to={'user_type': 'farmer'})
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='policies')
    
    # Policy details
    policy_type = models.CharField(max_length=50, choices=POLICY_TYPES, default='drought')
    coverage_start = models.DateField()
    coverage_end = models.DateField()
    sum_insured = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total insured amount in KES")
    premium_amount = models.DecimalField(max_digits=12, decimal_places=2)
    premium_rate = models.FloatField(help_text="Premium as percentage of sum insured")
    
    # Trigger parameters
    ndvi_trigger = models.FloatField(default=0.3, help_text="NDVI threshold for payout")
    rainfall_trigger = models.FloatField(default=50, help_text="Rainfall threshold in mm")
    risk_level_trigger = models.CharField(max_length=20, choices=[
        ('moderate', 'Moderate or Higher'),
        ('high', 'High Only'),
    ], default='moderate')
    
    # Payout parameters
    payout_rate = models.FloatField(default=0.7, help_text="Payout as fraction of sum insured")
    max_payout = models.DecimalField(max_digits=12, decimal_places=2, help_text="Maximum payout amount")
    deductible = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Deductible amount")
    
    # Status
    status = models.CharField(max_length=20, choices=POLICY_STATUS, default='pending')
    is_auto_renew = models.BooleanField(default=True)
    
    # Payment information
    payment_method = models.CharField(max_length=50, choices=[
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
    ], default='mpesa')
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    
    # Documents
    policy_document = models.FileField(upload_to='policy_docs/', blank=True, null=True)
    terms_document = models.FileField(upload_to='policy_docs/', blank=True, null=True)
    
    # Metadata
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_policies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Insurance Policies"
        ordering = ['-coverage_start']
        indexes = [
            models.Index(fields=['policy_number']),
            models.Index(fields=['farmer']),
            models.Index(fields=['status']),
            models.Index(fields=['coverage_end']),
        ]
    
    def __str__(self):
        return f"Policy {self.policy_number} - {self.farm.farm_id}"
    
    def clean(self):
        if self.coverage_end <= self.coverage_start:
            raise ValidationError('Coverage end date must be after start date')
        
        if self.premium_amount > self.sum_insured * 0.3:  # Premium can't exceed 30% of sum insured
            raise ValidationError('Premium amount is too high')
    
    def save(self, *args, **kwargs):
        if not self.policy_number:
            # Generate policy number: POL-YYYY-MM-XXXX
            year_month = date.today().strftime('%Y-%m')
            last_policy = InsurancePolicy.objects.filter(policy_number__startswith=f'POL-{year_month}').order_by('policy_number').last()
            if last_policy:
                last_num = int(last_policy.policy_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.policy_number = f'POL-{year_month}-{new_num:04d}'
        
        # Auto-calculate premium if not set
        if not self.premium_amount and self.sum_insured and self.premium_rate:
            self.premium_amount = self.sum_insured * (self.premium_rate / 100)
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        today = date.today()
        return self.status == 'active' and self.coverage_start <= today <= self.coverage_end
    
    @property
    def days_remaining(self):
        """Days until coverage ends"""
        today = date.today()
        if self.coverage_end and self.coverage_end > today:
            return (self.coverage_end - today).days
        return 0
    
    @property
    def coverage_duration(self):
        """Coverage duration in days"""
        return (self.coverage_end - self.coverage_start).days
    
    @property
    def premium_per_day(self):
        """Premium per day"""
        if self.coverage_duration > 0:
            return float(self.premium_amount) / self.coverage_duration
        return 0
    
    def calculate_payout(self, analysis):
        """Calculate payout amount based on analysis"""
        if not analysis:
            return 0
        
        payout = 0
        triggers = []
        
        # Check NDVI trigger
        if analysis.ndvi and analysis.ndvi < self.ndvi_trigger:
            severity = (self.ndvi_trigger - analysis.ndvi) / self.ndvi_trigger
            payout += float(self.sum_insured) * severity * 0.4
            triggers.append(f"NDVI: {analysis.ndvi:.2f}")
        
        # Check rainfall trigger
        if analysis.rainfall_mm and analysis.rainfall_mm < self.rainfall_trigger:
            severity = (self.rainfall_trigger - analysis.rainfall_mm) / self.rainfall_trigger
            payout += float(self.sum_insured) * severity * 0.4
            triggers.append(f"Rainfall: {analysis.rainfall_mm:.1f}mm")
        
        # Check risk level
        if self.risk_level_trigger == 'moderate' and analysis.drought_risk_level in ['moderate', 'high']:
            payout += float(self.sum_insured) * 0.2
            triggers.append(f"Risk: {analysis.drought_risk_level}")
        elif self.risk_level_trigger == 'high' and analysis.drought_risk_level == 'high':
            payout += float(self.sum_insured) * 0.2
            triggers.append(f"Risk: {analysis.drought_risk_level}")
        
        # Apply payout rate and deductibles
        payout = payout * self.payout_rate
        payout = max(payout - float(self.deductible), 0)
        payout = min(payout, float(self.max_payout))
        
        return round(payout, 2)


class InsuranceClaim(models.Model):
    """Insurance claims"""
    CLAIM_STATUS = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('closed', 'Closed'),
    ]
    
    # Claim identification
    claim_number = models.CharField(max_length=50, unique=True)
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.CASCADE, related_name='claims')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='claims')
    
    # Trigger details
    triggered_by = models.ForeignKey(SatelliteAnalysis, on_delete=models.SET_NULL, 
                                    null=True, related_name='triggered_claims')
    trigger_date = models.DateField()
    
    # Claim details
    claimed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Evidence
    ndvi_value = models.FloatField(null=True, blank=True)
    rainfall_value = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=20, blank=True)
    
    # Satellite evidence
    satellite_image_url = models.URLField(blank=True)
    gee_analysis_link = models.URLField(blank=True)
    field_photos = models.TextField(blank=True, help_text="JSON array of field photo URLs")
    
    # Documents
    claim_form = models.FileField(upload_to='claim_docs/', blank=True, null=True)
    supporting_docs = models.FileField(upload_to='claim_docs/', blank=True, null=True)
    
    # Processing
    status = models.CharField(max_length=20, choices=CLAIM_STATUS, default='draft')
    submitted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='submitted_claims')
    submitted_date = models.DateTimeField(null=True, blank=True)
    
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='reviewed_claims')
    reviewed_date = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    paid_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, 
                               related_name='paid_claims')
    paid_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, choices=[
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
    ])
    
    # Farmer feedback
    farmer_feedback = models.TextField(blank=True)
    farmer_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-trigger_date']
        indexes = [
            models.Index(fields=['claim_number']),
            models.Index(fields=['policy']),
            models.Index(fields=['status']),
            models.Index(fields=['trigger_date']),
        ]
    
    def __str__(self):
        return f"Claim {self.claim_number} - {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.claim_number:
            # Generate claim number: CLM-YYYY-MM-XXXX
            year_month = date.today().strftime('%Y-%m')
            last_claim = InsuranceClaim.objects.filter(claim_number__startswith=f'CLM-{year_month}').order_by('claim_number').last()
            if last_claim:
                last_num = int(last_claim.claim_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.claim_number = f'CLM-{year_month}-{new_num:04d}'
        
        # Auto-set trigger date if not provided
        if not self.trigger_date and self.triggered_by:
            self.trigger_date = self.triggered_by.analysis_date
        
        # Auto-set values from triggered analysis
        if self.triggered_by and not self.ndvi_value:
            self.ndvi_value = self.triggered_by.ndvi
            self.rainfall_value = self.triggered_by.rainfall_mm
            self.risk_level = self.triggered_by.drought_risk_level
        
        super().save(*args, **kwargs)
    
    @property
    def is_approved(self):
        return self.status in ['approved', 'paid']
    
    @property
    def processing_days(self):
        """Days since submission"""
        if self.submitted_date:
            from django.utils import timezone
            return (timezone.now() - self.submitted_date).days
        return None
    
    @property
    def status_color(self):
        """Get Bootstrap color for status"""
        colors = {
            'draft': 'secondary',
            'submitted': 'info',
            'under_review': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'paid': 'success',
            'closed': 'dark',
        }
        return colors.get(self.status, 'secondary')
    
    def can_be_edited(self, user):
        """Check if user can edit this claim"""
        if user.is_admin or user == self.submitted_by:
            return self.status in ['draft', 'submitted']
        return False


class UserProfile(models.Model):
    """Extended user profile"""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')
    
    # Personal details
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], blank=True)
    
    # Address
    physical_address = models.TextField(blank=True)
    postal_address = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Banking details (for payouts)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    
    # Mobile money
    mpesa_number = models.CharField(max_length=20, blank=True)
    mpesa_name = models.CharField(max_length=100, blank=True)
    
    # Emergency contact
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    
    # Verification
    id_document = models.FileField(upload_to='verification/', blank=True, null=True)
    id_number = models.CharField(max_length=50, blank=True)
    verification_status = models.CharField(max_length=20, choices=[
        ('unverified', 'Unverified'),
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Verification Rejected'),
    ], default='unverified')
    
    # Settings
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"
    
    @property
    def full_address(self):
        """Get full address"""
        parts = []
        if self.physical_address:
            parts.append(self.physical_address)
        if self.village:
            parts.append(self.village)
        if self.ward:
            parts.append(f"Ward: {self.ward}")
        if self.subcounty:
            parts.append(f"Subcounty: {self.subcounty}")
        if self.county:
            parts.append(f"County: {self.county}")
        if self.postal_code:
            parts.append(f"Postal Code: {self.postal_code}")
        
        return ", ".join(parts)


class Notification(models.Model):
    """System notifications"""
    NOTIFICATION_TYPES = [
        ('analysis_complete', 'Analysis Complete'),
        ('insurance_trigger', 'Insurance Trigger'),
        ('claim_update', 'Claim Update'),
        ('policy_expiry', 'Policy Expiry'),
        ('system_alert', 'System Alert'),
        ('weather_alert', 'Weather Alert'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    
    # Related objects
    related_farm = models.ForeignKey(Farm, on_delete=models.SET_NULL, null=True, blank=True)
    related_policy = models.ForeignKey(InsurancePolicy, on_delete=models.SET_NULL, null=True, blank=True)
    related_claim = models.ForeignKey(InsuranceClaim, on_delete=models.SET_NULL, null=True, blank=True)
    related_analysis = models.ForeignKey(SatelliteAnalysis, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} - {self.user.username}"
    
    def mark_as_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save()


class GEEExportTask(models.Model):
    """Track GEE export tasks"""
    TASK_STATUS = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    task_id = models.CharField(max_length=100, unique=True)
    task_type = models.CharField(max_length=50, choices=[
        ('farm_analysis', 'Farm Analysis'),
        ('batch_analysis', 'Batch Analysis'),
        ('rainfall_export', 'Rainfall Export'),
        ('indices_export', 'Vegetation Indices Export'),
    ])
    
    # Parameters
    parameters = models.TextField(blank=True, help_text="JSON parameters")
    year = models.IntegerField(null=True, blank=True)
    month = models.IntegerField(null=True, blank=True)
    
    # Results
    result_url = models.URLField(blank=True)
    result_size = models.CharField(max_length=50, blank=True)
    records_processed = models.IntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='pending')
    status_message = models.TextField(blank=True)
    progress_percentage = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    # Created by
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task_type} - {self.task_id}"
    
    @property
    def is_complete(self):
        return self.status in ['completed', 'failed', 'cancelled']
    
    def update_status(self, status, message="", progress=0):
        from django.utils import timezone
        self.status = status
        self.status_message = message
        self.progress_percentage = progress
        
        if status == 'running' and not self.started_at:
            self.started_at = timezone.now()
        elif status in ['completed', 'failed', 'cancelled'] and not self.completed_at:
            self.completed_at = timezone.now()
            if self.started_at:
                self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        
        self.save()