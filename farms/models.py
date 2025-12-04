from django.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.auth.models import User

class SubCounty(models.Model):
    """Machakos Sub-Counties from shapefile"""
    name = models.CharField(max_length=100)
    subcounty_code = models.CharField(max_length=20, unique=True)
    area_sqkm = models.FloatField()
    population = models.IntegerField(null=True, blank=True)
    geom = gis_models.MultiPolygonField(srid=4326)
    
    # Agricultural data
    main_crops = models.TextField(blank=True)
    avg_rainfall = models.FloatField(null=True, blank=True)  # mm/year
    soil_type = models.CharField(max_length=100, blank=True)
    
    class Meta:
        verbose_name_plural = "Sub Counties"
    
    def __str__(self):
        return f"{self.name} Sub-County"

class Farmer(models.Model):
    """Farmer information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    farmer_id = models.CharField(max_length=20, unique=True)  # Farm number from registration
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    id_number = models.CharField(max_length=20, unique=True)
    subcounty = models.ForeignKey(SubCounty, on_delete=models.SET_NULL, null=True)
    ward = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    
    registration_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"{self.farmer_id} - {self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class Farm(models.Model):
    """Farm polygon with location data"""
    CROP_CHOICES = [
        ('maize', 'Maize'),
        ('beans', 'Beans'),
        ('peas', 'Peas'),
        ('coffee', 'Coffee'),
        ('avocado', 'Avocado'),
        ('mango', 'Mango'),
        ('macadamia', 'Macadamia'),
        ('vegetables', 'Vegetables'),
        ('other', 'Other'),
    ]
    
    farm_id = models.CharField(max_length=50, unique=True)  # Matches farm.geojson ID
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='farms')
    name = models.CharField(max_length=200, blank=True)
    
    # Location
    geom = gis_models.MultiPolygonField(srid=4326)
    area_ha = models.FloatField()
    centroid = gis_models.PointField(srid=4326, null=True, blank=True)
    
    # Crop information
    crop_type = models.CharField(max_length=50, choices=CROP_CHOICES, default='maize')
    crop_variety = models.CharField(max_length=100, blank=True)
    planting_date = models.DateField(null=True, blank=True)
    harvest_date = models.DateField(null=True, blank=True)
    
    # Ownership/Lease
    ownership_type = models.CharField(max_length=20, choices=[
        ('owned', 'Owned'),
        ('leased', 'Leased'),
        ('family', 'Family Land'),
        ('communal', 'Communal'),
    ], default='owned')
    
    # Status
    is_active = models.BooleanField(default=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['farm_id']
    
    def __str__(self):
        return f"{self.farm_id} - {self.name or 'Unnamed Farm'}"
    
    def save(self, *args, **kwargs):
        # Calculate centroid if not set
        if self.geom and not self.centroid:
            self.centroid = self.geom.centroid
        super().save(*args, **kwargs)

class SatelliteAnalysis(models.Model):
    """Satellite data analysis results for farms"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='analyses')
    
    # Dates
    analysis_date = models.DateField()
    image_date = models.DateField()  # Date of satellite image
    
    # Vegetation indices
    ndvi_mean = models.FloatField()  # -1 to 1
    ndvi_min = models.FloatField()
    ndvi_max = models.FloatField()
    ndvi_std = models.FloatField()
    
    # Water indices
    ndmi_mean = models.FloatField()  # -1 to 1 (moisture)
    ndwi_mean = models.FloatField()  # -1 to 1 (water content)
    
    # Soil moisture (estimated)
    soil_moisture = models.FloatField(null=True, blank=True)  # 0-100%
    
    # Derived metrics
    vegetation_health = models.CharField(max_length=20, choices=[
        ('excellent', 'Excellent (>0.6)'),
        ('good', 'Good (0.4-0.6)'),
        ('moderate', 'Moderate (0.2-0.4)'),
        ('stressed', 'Stressed (0.1-0.2)'),
        ('severe', 'Severe (<0.1)'),
    ])
    
    moisture_status = models.CharField(max_length=20, choices=[
        ('wet', 'Wet (>0.3)'),
        ('adequate', 'Adequate (0.1-0.3)'),
        ('dry', 'Dry (<0.1)'),
        ('very_dry', 'Very Dry (<0)'),
    ])
    
    # Cloud cover
    cloud_cover_percentage = models.FloatField(default=0)
    
    # Analysis metadata
    satellite_source = models.CharField(max_length=50, default='Sentinel-2')
    processed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-analysis_date']
        verbose_name_plural = 'Satellite Analyses'
    
    def __str__(self):
        return f"{self.farm.farm_id} - {self.analysis_date}"

class DroughtAlert(models.Model):
    """Drought alerts for farms"""
    SEVERITY_CHOICES = [
        ('low', 'Low - Watch'),
        ('moderate', 'Moderate - Alert'),
        ('high', 'High - Warning'),
        ('severe', 'Severe - Emergency'),
    ]
    
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='alerts')
    analysis = models.ForeignKey(SatelliteAnalysis, on_delete=models.CASCADE, null=True, blank=True)
    
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    trigger_reason = models.TextField()
    
    # Thresholds breached
    ndvi_breached = models.BooleanField(default=False)
    ndmi_breached = models.BooleanField(default=False)
    soil_moisture_breached = models.BooleanField(default=False)
    
    # Dates
    detected_date = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField()  # When drought started
    end_date = models.DateField(null=True, blank=True)  # When resolved
    
    # Status
    is_active = models.BooleanField(default=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-detected_date']
    
    def __str__(self):
        return f"{self.farm.farm_id} - {self.severity} Alert"