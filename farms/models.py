from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import os
from django.conf import settings

class County(models.Model):
    """Machakos County boundary and sub-counties"""
    country = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    county = models.CharField(max_length=100)
    county_code = models.CharField(max_length=50, unique=True)
    subcounty = models.CharField(max_length=100)
    subcounty_code = models.CharField(max_length=50, unique=True)
    geometry = models.MultiPolygonField(srid=4326)
    centroid = models.PointField(srid=4326, null=True, blank=True)
    
    # Analysis parameters
    avg_rainfall = models.FloatField(null=True, blank=True, help_text="Average annual rainfall in mm")
    soil_type = models.CharField(max_length=100, blank=True)
    elevation = models.FloatField(null=True, blank=True, help_text="Average elevation in meters")
    
    class Meta:
        verbose_name_plural = "Counties"
        ordering = ['county', 'subcounty']
    
    def __str__(self):
        return f"{self.county} - {self.subcounty}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate centroid if not provided
        if self.geometry and not self.centroid:
            self.centroid = self.geometry.centroid
        super().save(*args, **kwargs)


class Farmer(models.Model):
    """Farm owner information"""
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    national_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    
    # Location
    subcounty = models.ForeignKey(County, on_delete=models.SET_NULL, null=True, related_name='farmers')
    village = models.CharField(max_length=100)
    
    # Banking for insurance payouts
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    mpesa_number = models.CharField(max_length=20, blank=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.national_id})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Farm(models.Model):
    """Farm polygon with crop information"""
    # Farm identification
    farm_id = models.CharField(max_length=100, unique=True, db_index=True)
    osm_id = models.CharField(max_length=100, blank=True, help_text="Original OSM ID if from OpenStreetMap")
    name = models.CharField(max_length=200, blank=True)
    
    # Ownership
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='farms')
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='farms')
    
    # Geometry
    geometry = models.MultiPolygonField(srid=4326)
    centroid = models.PointField(srid=4326)
    area_ha = models.FloatField(validators=[MinValueValidator(0.1)], help_text="Area in hectares")
    
    # Crop information
    crop_type = models.CharField(max_length=100, default=settings.PRIMARY_CROP)
    crop_variety = models.CharField(max_length=100, blank=True)
    planting_date = models.DateField(null=True, blank=True)
    expected_harvest_date = models.DateField(null=True, blank=True)
    
    # Land characteristics
    landuse = models.CharField(max_length=100, blank=True)
    soil_quality = models.CharField(max_length=50, blank=True, choices=[
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ])
    irrigation = models.BooleanField(default=False)
    irrigation_type = models.CharField(max_length=50, blank=True, choices=[
        ('drip', 'Drip'),
        ('sprinkler', 'Sprinkler'),
        ('flood', 'Flood'),
        ('none', 'None'),
    ])
    
    # Management
    operator = models.CharField(max_length=200, blank=True)
    cooperative = models.CharField(max_length=200, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    # GEE Integration
    gee_asset_path = models.CharField(max_length=500, blank=True, 
                                      help_text="Path in GEE Assets where farm polygon is stored")
    
    class Meta:
        ordering = ['farm_id']
    
    def __str__(self):
        return f"{self.farm_id} - {self.name or 'Unnamed Farm'}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate area if not provided
        if self.geometry and not self.area_ha:
            # Convert from square degrees to hectares (approximate)
            # For accurate area, use proper projection transformation
            self.area_ha = self.geometry.area * 10000  # Rough approximation
        
        # Auto-set centroid if not provided
        if self.geometry and not self.centroid:
            self.centroid = self.geometry.centroid
        
        super().save(*args, **kwargs)
    
    @property
    def crop_days(self):
        """Days since planting"""
        if self.planting_date:
            from datetime import date
            return (date.today() - self.planting_date).days
        return None


class SatelliteAnalysis(models.Model):
    """Satellite-based indices analysis for farms"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='analyses')
    
    # Time period
    analysis_date = models.DateField()
    year = models.IntegerField()
    month = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    
    # Sentinel-2 Indices
    ndvi = models.FloatField(null=True, blank=True, help_text="Normalized Difference Vegetation Index")
    evi = models.FloatField(null=True, blank=True, help_text="Enhanced Vegetation Index")
    ndmi = models.FloatField(null=True, blank=True, help_text="Normalized Difference Moisture Index")
    savi = models.FloatField(null=True, blank=True, help_text="Soil Adjusted Vegetation Index")
    ndre = models.FloatField(null=True, blank=True, help_text="Normalized Difference Red Edge")
    
    # Rainfall data
    rainfall_mm = models.FloatField(null=True, blank=True, help_text="Total rainfall in mm for period")
    
    # Derived metrics
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
    
    # Analysis metadata
    cloud_cover_percentage = models.FloatField(null=True, blank=True)
    image_count = models.IntegerField(default=0)
    analysis_timestamp = models.DateTimeField(auto_now_add=True)
    
    # Insurance trigger
    drought_risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low Risk'),
        ('moderate', 'Moderate Risk'),
        ('severe', 'Severe Risk'),
    ], blank=True)
    insurance_triggered = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Satellite Analyses"
        ordering = ['-analysis_date', 'farm']
        unique_together = ['farm', 'year', 'month']
    
    def __str__(self):
        return f"{self.farm.farm_id} - {self.year}-{self.month:02d}"
    
    def calculate_risk_level(self):
        """Calculate drought risk based on thresholds"""
        from django.conf import settings
        
        if self.ndvi is None:
            return 'low'
        
        try:
            ndvi_severe = float(os.getenv('NDVI_THRESHOLD_SEVERE', 0.3))
            ndvi_moderate = float(os.getenv('NDVI_THRESHOLD_MODERATE', 0.4))
        except:
            ndvi_severe = 0.3
            ndvi_moderate = 0.4
        
        if self.ndvi < ndvi_severe:
            return 'severe'
        elif self.ndvi < ndvi_moderate:
            return 'moderate'
        else:
            return 'low'
    
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
        
        # Auto-calculate moisture stress from NDMI
        if self.ndmi is not None:
            if self.ndmi > 0.2:
                self.moisture_stress = 'none'
            elif self.ndmi > 0.1:
                self.moisture_stress = 'mild'
            elif self.ndmi > 0:
                self.moisture_stress = 'moderate'
            else:
                self.moisture_stress = 'severe'
        
        # Auto-calculate drought risk
        self.drought_risk_level = self.calculate_risk_level()
        
        # Check if insurance should be triggered
        try:
            rainfall_threshold = float(os.getenv('RAINFALL_THRESHOLD_MM', 50))
        except:
            rainfall_threshold = 50
        
        if (self.drought_risk_level in ['moderate', 'severe'] or 
            (self.rainfall_mm is not None and self.rainfall_mm < rainfall_threshold)):
            self.insurance_triggered = True
        else:
            self.insurance_triggered = False
        
        super().save(*args, **kwargs)
    
    @property
    def risk_color(self):
        """Get color for risk level"""
        colors = {
            'low': 'green',
            'moderate': 'orange',
            'severe': 'red',
        }
        return colors.get(self.drought_risk_level, 'gray')


class InsurancePolicy(models.Model):
    """Insurance policy for farms"""
    POLICY_STATUS = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('claimed', 'Claim Made'),
    ]
    
    policy_number = models.CharField(max_length=50, unique=True)
    farm = models.OneToOneField(Farm, on_delete=models.CASCADE, related_name='insurance_policy')
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='policies')
    
    # Coverage
    coverage_start = models.DateField()
    coverage_end = models.DateField()
    sum_insured = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total insured amount in KES")
    premium_paid = models.DecimalField(max_digits=12, decimal_places=2)
    premium_rate = models.FloatField(help_text="Premium as percentage of sum insured")
    
    # Terms
    trigger_threshold_ndvi = models.FloatField(default=0.3)
    trigger_threshold_rainfall = models.FloatField(default=50, help_text="mm per month")
    payout_rate = models.FloatField(default=1.0, help_text="Payout as fraction of sum insured")
    
    # Status
    status = models.CharField(max_length=20, choices=POLICY_STATUS, default='active')
    created_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Insurance Policies"
        ordering = ['-coverage_start']
    
    def __str__(self):
        return f"Policy {self.policy_number} - {self.farm.farm_id}"
    
    @property
    def is_active(self):
        from datetime import date
        return self.status == 'active' and self.coverage_start <= date.today() <= self.coverage_end
    
    @property
    def days_remaining(self):
        """Days until coverage ends"""
        from datetime import date
        if self.coverage_end:
            return (self.coverage_end - date.today()).days
        return None


class InsuranceClaim(models.Model):
    """Insurance claims triggered by drought detection"""
    CLAIM_STATUS = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ]
    
    claim_number = models.CharField(max_length=50, unique=True)
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.CASCADE, related_name='claims')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='claims')
    
    # Trigger details
    triggered_by_analysis = models.ForeignKey(SatelliteAnalysis, on_delete=models.SET_NULL, 
                                             null=True, related_name='claims')
    trigger_date = models.DateField()
    
    # Claim details
    claim_amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=CLAIM_STATUS, default='pending')
    
    # Evidence
    ndvi_value = models.FloatField(null=True, blank=True)
    rainfall_value = models.FloatField(null=True, blank=True)
    satellite_image_url = models.URLField(blank=True)
    field_assessment_report = models.FileField(upload_to='claim_reports/', blank=True)
    
    # Processing
    submitted_date = models.DateTimeField(auto_now_add=True)
    reviewed_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-trigger_date']
    
    def __str__(self):
        return f"Claim {self.claim_number} - {self.status}"
    
    @property
    def is_approved(self):
        return self.status in ['approved', 'paid']
    
    def save(self, *args, **kwargs):
        # Auto-generate claim number if not provided
        if not self.claim_number:
            from django.utils import timezone
            date_str = timezone.now().strftime('%Y%m%d')
            last_claim = InsuranceClaim.objects.filter(
                claim_number__startswith=f'CLM{date_str}'
            ).order_by('claim_number').last()
            
            if last_claim:
                last_num = int(last_claim.claim_number[-4:])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.claim_number = f'CLM{date_str}{new_num:04d}'
        
        super().save(*args, **kwargs)