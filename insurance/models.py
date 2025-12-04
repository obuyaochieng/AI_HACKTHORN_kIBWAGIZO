from django.db import models
from django.contrib.auth.models import User
from farms.models import Farm, Farmer

class InsurancePolicy(models.Model):
    """Insurance policy for a farm"""
    POLICY_TYPES = [
        ('drought', 'Drought Insurance'),
        ('comprehensive', 'Comprehensive Crop Insurance'),
        ('index', 'Index-Based Insurance'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('claimed', 'Claimed'),
    ]
    
    policy_number = models.CharField(max_length=50, unique=True)
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='policies')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='policies')
    
    # Policy details
    policy_type = models.CharField(max_length=20, choices=POLICY_TYPES, default='drought')
    sum_insured = models.DecimalField(max_digits=10, decimal_places=2)  # Total coverage amount
    premium_amount = models.DecimalField(max_digits=10, decimal_places=2)
    premium_paid = models.BooleanField(default=False)
    
    # Coverage period
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Terms
    deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coverage_percentage = models.IntegerField(default=80)  # 80% coverage
    
    # Triggers
    ndvi_trigger = models.FloatField(default=0.2)  # Trigger if NDVI < 0.2
    ndmi_trigger = models.FloatField(default=0.1)  # Trigger if NDMI < 0.1
    days_below_threshold = models.IntegerField(default=14)  # Must be below for X days
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_policies')
    agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_policies')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Insurance Policies'
    
    def __str__(self):
        return f"{self.policy_number} - {self.farmer.full_name}"
    
    @property
    def is_active(self):
        from datetime import date
        return self.status == 'active' and date.today() <= self.end_date
    
    @property
    def days_remaining(self):
        from datetime import date
        if self.end_date:
            return (self.end_date - date.today()).days
        return 0

class InsuranceClaim(models.Model):
    """Insurance claims"""
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    ]
    
    claim_number = models.CharField(max_length=50, unique=True)
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.CASCADE, related_name='claims')
    
    # Claim details
    claim_amount = models.DecimalField(max_digits=10, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Reason
    drought_alert = models.ForeignKey('farms.DroughtAlert', on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField()
    supporting_documents = models.FileField(upload_to='claims/documents/', null=True, blank=True)
    
    # Dates
    incident_date = models.DateField()
    claim_date = models.DateTimeField(auto_now_add=True)
    
    # Review process
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    # Payment
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['-claim_date']
    
    def __str__(self):
        return f"Claim {self.claim_number} - {self.status}"
    
    @property
    def days_since_submission(self):
        from datetime import datetime
        return (datetime.now().date() - self.claim_date.date()).days