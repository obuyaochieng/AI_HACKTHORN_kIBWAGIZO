import json
import geopandas as gpd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.serializers import serialize
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Farm, Farmer, SubCounty, SatelliteAnalysis, DroughtAlert
from .forms import FarmerRegistrationForm, FarmUploadForm
import ee

def map_viewer(request):
    """Interactive map viewer for Machakos County"""
    # Get Machakos center coordinates
    machakos_center = {
        'lat': -1.52,
        'lng': 37.26,
        'zoom': 10
    }
    
    # Get statistics for display
    total_farms = Farm.objects.count()
    total_farmers = Farmer.objects.count()
    active_alerts = DroughtAlert.objects.filter(is_active=True).count()
    
    context = {
        'machakos_center': machakos_center,
        'total_farms': total_farms,
        'total_farmers': total_farmers,
        'active_alerts': active_alerts,
    }
    
    return render(request, 'map_viewer.html', context)

def farm_geojson(request):
    """Return farms as GeoJSON"""
    farms = Farm.objects.all()
    
    # Convert to GeoJSON
    geojson_data = serialize('geojson', farms,
        geometry_field='geom',
        fields=('farm_id', 'name', 'farmer__first_name', 'farmer__last_name', 
                'crop_type', 'area_ha', 'ownership_type')
    )
    
    return JsonResponse(json.loads(geojson_data), safe=False)

def subcounty_geojson(request):
    """Return subcounties as GeoJSON"""
    subcounties = SubCounty.objects.all()
    
    geojson_data = serialize('geojson', subcounties,
        geometry_field='geom',
        fields=('name', 'subcounty_code', 'area_sqkm', 'population', 
                'main_crops', 'avg_rainfall', 'soil_type')
    )
    
    return JsonResponse(json.loads(geojson_data), safe=False)

def farmer_register(request):
    """Register a new farmer"""
    if request.method == 'POST':
        form = FarmerRegistrationForm(request.POST)
        if form.is_valid():
            farmer = form.save(commit=False)
            
            # Generate farmer ID
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            farmer.farmer_id = f"FARM{timestamp[-6:]}"
            
            # If user is registering themselves
            if request.user.is_authenticated:
                farmer.user = request.user
            
            farmer.save()
            messages.success(request, f'Farmer {farmer.full_name} registered successfully! Farmer ID: {farmer.farmer_id}')
            return redirect('farmer_detail', farmer_id=farmer.id)
    else:
        form = FarmerRegistrationForm()
    
    # Get subcounty choices
    subcounties = SubCounty.objects.all().values('id', 'name')
    
    context = {
        'form': form,
        'subcounties': list(subcounties),
    }
    
    return render(request, 'farmer_register.html', context)

def farm_upload(request):
    """Upload farm polygon (GeoJSON/Shapefile)"""
    if request.method == 'POST':
        form = FarmUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Process uploaded file
                uploaded_file = request.FILES['geojson_file']
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                if file_extension == 'geojson':
                    # Read GeoJSON
                    gdf = gpd.read_file(uploaded_file)
                elif file_extension == 'zip':
                    # Read Shapefile (zipped)
                    gdf = gpd.read_file(f"zip://{uploaded_file.file}")
                else:
                    messages.error(request, 'Unsupported file format. Please upload GeoJSON or zipped Shapefile.')
                    return redirect('farm_upload')
                
                # Validate CRS
                if gdf.crs != 'EPSG:4326':
                    gdf = gdf.to_crs('EPSG:4326')
                
                # Process each feature
                farmer_id = form.cleaned_data['farmer_id']
                farmer = get_object_or_404(Farmer, farmer_id=farmer_id)
                
                farms_created = []
                for idx, row in gdf.iterrows():
                    # Create farm
                    farm = Farm(
                        farm_id=f"{farmer.farmer_id}_F{idx+1:03d}",
                        farmer=farmer,
                        name=row.get('name', f'{farmer.full_name} Farm {idx+1}'),
                        geom=row.geometry.wkt,
                        area_ha=row.geometry.area * 10000,  # Convert from deg² to hectares (approx)
                        crop_type=row.get('crop', 'maize'),
                        crop_variety=row.get('variety', ''),
                        ownership_type='owned'
                    )
                    farm.save()
                    farms_created.append(farm)
                
                messages.success(request, f'Successfully uploaded {len(farms_created)} farms for {farmer.full_name}')
                return redirect('farmer_detail', farmer_id=farmer.id)
                
            except Exception as e:
                messages.error(request, f'Error processing file: {str(e)}')
    else:
        form = FarmUploadForm()
    
    return render(request, 'farm_upload.html', {'form': form})

def satellite_analysis(request):
    """Run satellite analysis for farms"""
    if not request.user.is_staff:
        messages.error(request, 'Only staff members can run satellite analysis.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        farm_ids = request.POST.getlist('farm_ids')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        
        if not farm_ids:
            messages.error(request, 'Please select at least one farm.')
            return redirect('satellite_analysis')
        
        # Initialize Earth Engine
        try:
            ee.Initialize()
        except:
            messages.error(request, 'Google Earth Engine not initialized. Please check credentials.')
            return redirect('satellite_analysis')
        
        # Process each farm
        analysis_count = 0
        for farm_id in farm_ids:
            farm = get_object_or_404(Farm, farm_id=farm_id)
            
            # Run analysis (simplified - implement actual GEE analysis)
            try:
                analysis = run_satellite_analysis(farm, start_date, end_date)
                if analysis:
                    analysis_count += 1
                    
                    # Check for drought alerts
                    check_drought_alert(farm, analysis)
                    
            except Exception as e:
                messages.warning(request, f'Error analyzing farm {farm_id}: {str(e)}')
        
        messages.success(request, f'Analysis complete for {analysis_count} farms.')
        return redirect('dashboard')
    
    # GET request - show form
    farms = Farm.objects.filter(is_active=True)
    
    # Default dates (last 30 days)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    context = {
        'farms': farms,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }
    
    return render(request, 'satellite_analysis.html', context)

def run_satellite_analysis(farm, start_date, end_date):
    """
    Run satellite analysis using Google Earth Engine
    This is a simplified version - implement actual GEE analysis
    """
    try:
        # Convert geometry to EE
        geom_wkt = farm.geom.wkt
        # Parse WKT and convert to EE geometry (simplified)
        
        # Example analysis (implement actual GEE calls)
        # For now, create mock data
        from django.utils import timezone
        import random
        
        analysis = SatelliteAnalysis(
            farm=farm,
            analysis_date=timezone.now().date(),
            image_date=(timezone.now() - timedelta(days=2)).date(),
            
            # Mock vegetation indices
            ndvi_mean=random.uniform(0.1, 0.8),
            ndvi_min=random.uniform(0.05, 0.6),
            ndvi_max=random.uniform(0.3, 0.9),
            ndvi_std=random.uniform(0.05, 0.2),
            
            ndmi_mean=random.uniform(-0.1, 0.4),
            ndwi_mean=random.uniform(-0.2, 0.3),
            
            soil_moisture=random.uniform(10, 80),
            
            vegetation_health='good',
            moisture_status='adequate',
            
            cloud_cover_percentage=random.uniform(0, 30),
            satellite_source='Sentinel-2'
        )
        
        analysis.save()
        return analysis
        
    except Exception as e:
        print(f"Analysis error: {e}")
        return None

def check_drought_alert(farm, analysis):
    """Check if analysis triggers a drought alert"""
    # Thresholds
    NDVI_ALERT = 0.2
    NDMI_ALERT = 0.1
    
    trigger_reasons = []
    ndvi_breached = False
    ndmi_breached = False
    soil_moisture_breached = False
    
    if analysis.ndvi_mean < NDVI_ALERT:
        trigger_reasons.append(f"Low NDVI ({analysis.ndvi_mean:.3f} < {NDVI_ALERT})")
        ndvi_breached = True
    
    if analysis.ndmi_mean < NDMI_ALERT:
        trigger_reasons.append(f"Low moisture index ({analysis.ndmi_mean:.3f} < {NDMI_ALERT})")
        ndmi_breached = True
    
    if analysis.soil_moisture and analysis.soil_moisture < 20:
        trigger_reasons.append(f"Low soil moisture ({analysis.soil_moisture:.1f}% < 20%)")
        soil_moisture_breached = True
    
    if trigger_reasons:
        # Determine severity
        if analysis.ndvi_mean < 0.1:
            severity = 'severe'
        elif analysis.ndvi_mean < 0.15:
            severity = 'high'
        elif analysis.ndvi_mean < 0.2:
            severity = 'moderate'
        else:
            severity = 'low'
        
        # Create alert
        alert = DroughtAlert(
            farm=farm,
            analysis=analysis,
            severity=severity,
            trigger_reason='; '.join(trigger_reasons),
            ndvi_breached=ndvi_breached,
            ndmi_breached=ndmi_breached,
            soil_moisture_breached=soil_moisture_breached,
            start_date=analysis.image_date,
            is_active=True
        )
        alert.save()

@login_required
def dashboard(request):
    """Main dashboard"""
    # Statistics
    stats = {
        'total_farms': Farm.objects.count(),
        'total_farmers': Farmer.objects.count(),
        'active_alerts': DroughtAlert.objects.filter(is_active=True).count(),
        'policies_active': 0,  # Will implement with insurance app
        'total_area': Farm.objects.aggregate(total=Sum('area_ha'))['total'] or 0,
    }
    
    # Recent alerts
    recent_alerts = DroughtAlert.objects.filter(is_active=True).order_by('-detected_date')[:10]
    
    # Recent analyses
    recent_analyses = SatelliteAnalysis.objects.all().order_by('-analysis_date')[:10]
    
    # Subcounty distribution
    subcounty_stats = SubCounty.objects.annotate(
        farm_count=Count('farmer__farms')
    ).values('name', 'farm_count')[:5]
    
    context = {
        'stats': stats,
        'recent_alerts': recent_alerts,
        'recent_analyses': recent_analyses,
        'subcounty_stats': subcounty_stats,
        'user': request.user,
    }
    
    return render(request, 'dashboard.html', context)

def farmer_detail(request, farmer_id):
    """Farmer detail view"""
    farmer = get_object_or_404(Farmer, id=farmer_id)
    farms = farmer.farms.all()
    
    # Get farmer's alerts
    alerts = DroughtAlert.objects.filter(farm__farmer=farmer, is_active=True)
    
    context = {
        'farmer': farmer,
        'farms': farms,
        'alerts': alerts,
    }
    
    return render(request, 'farmer_detail.html', context)

def farm_detail(request, farm_id):
    """Farm detail view"""
    farm = get_object_or_404(Farm, farm_id=farm_id)
    analyses = SatelliteAnalysis.objects.filter(farm=farm).order_by('-analysis_date')
    alerts = DroughtAlert.objects.filter(farm=farm).order_by('-detected_date')
    
    # Get historical NDVI data for chart
    ndvi_history = analyses.values('analysis_date', 'ndvi_mean')[:30]
    
    context = {
        'farm': farm,
        'analyses': analyses,
        'alerts': alerts,
        'ndvi_history': list(ndvi_history),
    }
    
    return render(request, 'farm_detail.html', context)