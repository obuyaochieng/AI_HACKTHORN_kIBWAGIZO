# farms/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
import json

from .models import CustomUser, UserProfile, Farm, County, InsurancePolicy, InsuranceClaim

# Use the custom user model
User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """Form for creating new users"""
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=True)
    national_id = forms.CharField(max_length=20, required=False)
    
    class Meta:
        model = User  # Use the custom user model
        fields = ('username', 'email', 'phone', 'national_id', 
                 'first_name', 'last_name', 'user_type')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make user_type dropdown nicer
        self.fields['user_type'].choices = User.USER_TYPES
        
        # Add Bootstrap classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('Email already exists')
        return email
    
    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if national_id and User.objects.filter(national_id=national_id).exists():
            raise ValidationError('National ID already registered')
        return national_id


class CustomUserChangeForm(UserChangeForm):
    """Form for updating users"""
    class Meta:
        model = User  # Use the custom user model
        fields = ('username', 'email', 'phone', 'national_id',
                 'first_name', 'last_name', 'user_type', 'is_active')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})


class UserProfileForm(forms.ModelForm):
    """Form for user profile"""
    class Meta:
        model = UserProfile
        fields = ['date_of_birth', 'gender', 'physical_address', 
                 'postal_address', 'postal_code', 'bank_name', 
                 'bank_branch', 'account_name', 'account_number',
                 'mpesa_number', 'mpesa_name', 'emergency_contact_name',
                 'emergency_contact_phone', 'emergency_contact_relationship',
                 'id_document', 'id_number', 'email_notifications',
                 'sms_notifications', 'push_notifications']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'physical_address': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Make file fields specific
        self.fields['id_document'].widget.attrs.update({'class': 'form-control-file'})


class FarmerRegistrationForm(CustomUserCreationForm):
    """Special form for farmer registration"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set user_type to farmer
        self.fields['user_type'].initial = 'farmer'
        self.fields['user_type'].widget = forms.HiddenInput()
        
        # Add farmer-specific fields
        self.fields['county'] = forms.ModelChoiceField(
            queryset=County.objects.all(),
            required=True
        )
        self.fields['subcounty'] = forms.CharField(max_length=100, required=True)
        self.fields['ward'] = forms.CharField(max_length=100, required=True)
        self.fields['village'] = forms.CharField(max_length=100, required=True)
    
    class Meta(CustomUserCreationForm.Meta):
        fields = CustomUserCreationForm.Meta.fields + ('county', 'subcounty', 'ward', 'village')
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'farmer'
        
        if commit:
            user.save()
            # Update location fields
            user.county = self.cleaned_data['county'].county_name
            user.subcounty = self.cleaned_data['subcounty']
            user.ward = self.cleaned_data['ward']
            user.village = self.cleaned_data['village']
            user.save()
        
        return user


class FarmUploadForm(forms.Form):
    """Form for uploading farm polygons"""
    farmer = forms.ModelChoiceField(
        queryset=User.objects.filter(user_type='farmer'),
        required=True,
        help_text="Select the farmer"
    )
    
    geojson_file = forms.FileField(
        required=True,
        help_text="Upload GeoJSON file containing farm polygons"
    )
    
    crop_type = forms.ChoiceField(
        choices=Farm.CROP_CHOICES,
        initial='maize',
        help_text="Select the main crop for these farms"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
    
    def clean_geojson_file(self):
        file = self.cleaned_data['geojson_file']
        if not file.name.endswith('.geojson') and not file.name.endswith('.json'):
            raise ValidationError('File must be GeoJSON format')
        return file


class FarmEditForm(forms.ModelForm):
    """Form for creating/editing farms"""
    class Meta:
        model = Farm
        fields = ['name', 'county', 'latitude', 'longitude', 'area_ha',
                 'crop_type', 'crop_variety', 'planting_date', 
                 'expected_harvest_date', 'expected_yield', 'soil_type',
                 'soil_ph', 'irrigation', 'irrigation_type', 'cooperative',
                 'farm_manager', 'contact_phone', 'geometry_geojson',
                 'boundary_coordinates']
        widgets = {
            'planting_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_harvest_date': forms.DateInput(attrs={'type': 'date'}),
            'geometry_geojson': forms.Textarea(attrs={'rows': 3}),
            'boundary_coordinates': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set farmer if creating new
        if self.instance.pk is None and self.user and self.user.is_farmer:
            self.instance.farmer = self.user
        
        # Make county dropdown nicer
        self.fields['county'].queryset = County.objects.all().order_by('subcounty')
        
        # Add Bootstrap classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Make text areas specific
        self.fields['geometry_geojson'].widget.attrs.update({'class': 'form-control', 'rows': 5})
        self.fields['boundary_coordinates'].widget.attrs.update({'class': 'form-control', 'rows': 5})
    
    def clean(self):
        cleaned_data = super().clean()
        planting_date = cleaned_data.get('planting_date')
        harvest_date = cleaned_data.get('expected_harvest_date')
        
        if planting_date and harvest_date and harvest_date <= planting_date:
            raise ValidationError('Harvest date must be after planting date')
        
        return cleaned_data
    
    def clean_soil_ph(self):
        ph = self.cleaned_data.get('soil_ph')
        if ph is not None and (ph < 0 or ph > 14):
            raise ValidationError('Soil pH must be between 0 and 14')
        return ph


class InsurancePolicyForm(forms.ModelForm):
    """Form for insurance policies"""
    class Meta:
        model = InsurancePolicy
        fields = ['farmer', 'farm', 'policy_type', 'coverage_start', 
                 'coverage_end', 'sum_insured', 'premium_rate', 
                 'ndvi_trigger', 'rainfall_trigger', 'risk_level_trigger',
                 'payout_rate', 'max_payout', 'deductible', 'is_auto_renew',
                 'payment_method', 'policy_document', 'terms_document']
        widgets = {
            'coverage_start': forms.DateInput(attrs={'type': 'date'}),
            'coverage_end': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter farmers and farms
        if self.user and not self.user.is_admin:
            # Non-admins can only create policies for themselves
            self.fields['farmer'].queryset = User.objects.filter(pk=self.user.pk)
            self.fields['farm'].queryset = Farm.objects.filter(farmer=self.user, is_active=True)
        else:
            # Admins can create for any farmer
            self.fields['farmer'].queryset = User.objects.filter(user_type='farmer')
            self.fields['farm'].queryset = Farm.objects.filter(is_active=True)
        
        # Set created_by if new
        if self.instance.pk is None:
            self.instance.created_by = self.user
        
        # Add Bootstrap classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Make file fields specific
        self.fields['policy_document'].widget.attrs.update({'class': 'form-control-file'})
        self.fields['terms_document'].widget.attrs.update({'class': 'form-control-file'})
    
    def clean(self):
        cleaned_data = super().clean()
        coverage_start = cleaned_data.get('coverage_start')
        coverage_end = cleaned_data.get('coverage_end')
        sum_insured = cleaned_data.get('sum_insured')
        premium_rate = cleaned_data.get('premium_rate')
        
        if coverage_start and coverage_end:
            if coverage_end <= coverage_start:
                raise ValidationError('Coverage end date must be after start date')
            
            # Check coverage duration (max 1 year)
            duration = (coverage_end - coverage_start).days
            if duration > 365:
                raise ValidationError('Coverage duration cannot exceed 1 year')
        
        if sum_insured and premium_rate:
            # Calculate and validate premium
            premium_amount = sum_insured * (premium_rate / 100)
            if premium_amount > sum_insured * 0.3:  # Premium can't exceed 30% of sum insured
                raise ValidationError('Premium amount is too high')
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Auto-calculate premium amount
        if instance.sum_insured and instance.premium_rate:
            instance.premium_amount = instance.sum_insured * (instance.premium_rate / 100)
        
        if commit:
            instance.save()
        
        return instance


class InsuranceClaimForm(forms.ModelForm):
    """Form for insurance claims"""
    class Meta:
        model = InsuranceClaim
        fields = ['policy', 'farm', 'triggered_by', 'trigger_date',
                 'claimed_amount', 'satellite_image_url', 'gee_analysis_link',
                 'field_photos', 'claim_form', 'supporting_docs', 'status']
        widgets = {
            'trigger_date': forms.DateInput(attrs={'type': 'date'}),
            'field_photos': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter policies and farms based on user
        if self.user and not self.user.is_admin:
            # Farmers can only claim on their policies
            self.fields['policy'].queryset = InsurancePolicy.objects.filter(
                farmer=self.user, 
                status='active'
            )
            self.fields['farm'].queryset = Farm.objects.filter(farmer=self.user)
        else:
            # Admins can claim on any active policy
            self.fields['policy'].queryset = InsurancePolicy.objects.filter(status='active')
            self.fields['farm'].queryset = Farm.objects.filter(is_active=True)
        
        # Filter analyses based on selected farm
        farm = self.initial.get('farm') or (self.instance.farm if self.instance.pk else None)
        if farm:
            self.fields['triggered_by'].queryset = SatelliteAnalysis.objects.filter(farm=farm)
        else:
            self.fields['triggered_by'].queryset = SatelliteAnalysis.objects.none()
        
        # Add Bootstrap classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Make text areas specific
        self.fields['field_photos'].widget.attrs.update({'class': 'form-control', 'rows': 5})
        
        # Make file fields specific
        self.fields['claim_form'].widget.attrs.update({'class': 'form-control-file'})
        self.fields['supporting_docs'].widget.attrs.update({'class': 'form-control-file'})
    
    def clean_field_photos(self):
        field_photos = self.cleaned_data.get('field_photos')
        if field_photos:
            try:
                # Validate JSON format
                json.loads(field_photos)
            except json.JSONDecodeError:
                raise ValidationError('Field photos must be a valid JSON array')
        return field_photos
    
    def clean(self):
        cleaned_data = super().clean()
        policy = cleaned_data.get('policy')
        farm = cleaned_data.get('farm')
        
        if policy and farm and policy.farm != farm:
            raise ValidationError('Selected farm does not match the policy farm')
        
        return cleaned_data


class AnalysisSearchForm(forms.Form):
    """Form for searching analysis data"""
    year = forms.ChoiceField(
        choices=[(str(y), str(y)) for y in range(2018, 2026)],
        required=False,
        initial='2023'
    )
    
    month = forms.ChoiceField(
        choices=[(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        required=False
    )
    
    index = forms.ChoiceField(
        choices=[
            ('NDVI', 'NDVI'),
            ('EVI', 'EVI'),
            ('NDMI', 'NDMI'),
            ('SAVI', 'SAVI'),
            ('NDRE', 'NDRE'),
            ('BSI', 'BSI'),
        ],
        required=False,
        initial='NDVI'
    )
    
    farm = forms.ModelChoiceField(
        queryset=Farm.objects.filter(is_active=True),
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and user.is_farmer:
            self.fields['farm'].queryset = Farm.objects.filter(farmer=user, is_active=True)
        
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})


class ExportForm(forms.Form):
    """Form for data export"""
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('excel', 'Excel'),
    ]
    
    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        initial='csv'
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )
    
    include_farm_details = forms.BooleanField(
        required=False,
        initial=True
    )
    
    include_analysis = forms.BooleanField(
        required=False,
        initial=True
    )
    
    include_insurance = forms.BooleanField(
        required=False,
        initial=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Style checkboxes differently
        for field in ['include_farm_details', 'include_analysis', 'include_insurance']:
            self.fields[field].widget.attrs.update({'class': 'form-check-input'})
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise ValidationError('End date must be after start date')
        
        return cleaned_data


class NotificationSettingsForm(forms.ModelForm):
    """Form for notification settings"""
    class Meta:
        model = UserProfile
        fields = ['email_notifications', 'sms_notifications', 'push_notifications']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-check-input'})