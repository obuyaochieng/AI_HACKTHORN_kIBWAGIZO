from django import forms
from django.contrib.auth.models import User
from .models import Farmer, Farm, SubCounty

class FarmerRegistrationForm(forms.ModelForm):
    """Form for registering a new farmer"""
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=False)
    
    class Meta:
        model = Farmer
        fields = ['first_name', 'last_name', 'phone', 'email', 'id_number', 
                 'subcounty', 'ward', 'village']
        widgets = {
            'phone': forms.TextInput(attrs={'placeholder': '0712345678'}),
            'id_number': forms.TextInput(attrs={'placeholder': '12345678'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make subcounty dropdown nicer
        self.fields['subcounty'].queryset = SubCounty.objects.all().order_by('name')
        
        # Add Bootstrap classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

class FarmUploadForm(forms.Form):
    """Form for uploading farm polygons"""
    farmer_id = forms.CharField(
        max_length=20,
        required=True,
        help_text="Enter the farmer's ID (e.g., FARM123456)"
    )
    
    geojson_file = forms.FileField(
        required=True,
        help_text="Upload GeoJSON or zipped Shapefile (.zip) containing farm polygons"
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