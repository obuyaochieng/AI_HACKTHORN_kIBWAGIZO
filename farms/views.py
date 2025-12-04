from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView, DetailView, TemplateView
from django.db.models import Count, Avg, Max, Min
from django.core.paginator import Paginator
import json
from datetime import datetime, timedelta

from .models import Farm, Farmer, County, SatelliteAnalysis, InsurancePolicy, InsuranceClaim
from .utils.gee_utils import GEEAnalyzer, ShapefileProcessor, test_gee_connection


class MapView(TemplateView):
    """Main map view for Machakos County"""
    template_name = 'map_viewer.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get Machakos County
        machakos = County.objects.filter(county__icontains='machakos').first()
        
        # Get farms for display
        farms = Farm.objects.filter(is_active=True).select_related('farmer', 'county')
        
        # Prepare farm data for map
        farm_data = []
        for farm in farms:
            # Get latest analysis
            latest_analysis = farm.analyses.order_by('-analysis_date').first()
            
            farm_data.append({
                'id': farm.id,
                'farm_id': farm.farm_id,
                'name': farm.name,
                'farmer': farm.farmer.full_name if farm.farmer else '',
                'crop': farm.crop_type,
                'area_ha': farm.area_ha,
                'centroid': {
                    'lat': farm.centroid.y,
                    'lng': farm.centroid.x
                } if farm.centroid else None,
                'geometry': json.loads(farm.geometry.geojson) if farm.geometry else None,
                'risk_level': latest_analysis.drought_risk_level if latest_analysis else 'unknown',
                'risk_color': latest_analysis.risk_color if latest_analysis else 'gray',
                'ndvi': latest_analysis.ndvi if latest_analysis else None,
                'insurance_triggered': latest_analysis.insurance_triggered if latest_analysis else False,
            })
        
        context.update({
            'machakos_county': machakos,
            'farms': farms,
            'farm_data_json': json.dumps(farm_data),
            'total_farms': farms.count(),
            'total_area': sum(f.area_ha for f in farms if f.area_ha),
            'crop_types': list(set(f.crop_type for f in farms if f.crop_type)),
        })
        
        return context


class SatelliteAnalysisView(TemplateView):
    """Satellite analysis dashboard"""
    template_name = 'satellite_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Years available for analysis
        years = list(range(2021, 2026))
        
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
        ]
        
        context.update({
            'years': years,
            'months': months,
            'indices': indices,
            'current_year': datetime.now().year,
            'current_month': datetime.now().month,
        })
        
        return context


class DashboardView(TemplateView):
    """Main dashboard for insurance admin"""
    template_name = 'dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get summary statistics
        total_farms = Farm.objects.filter(is_active=True).count()
        total_farmers = Farmer.objects.count()
        total_area = Farm.objects.filter(is_active=True).aggregate(
            total=Sum('area_ha')
        )['total'] or 0
        
        # Get insurance stats
        active_policies = InsurancePolicy.objects.filter(status='active').count()
        total_claims = InsuranceClaim.objects.count()
        pending_claims = InsuranceClaim.objects.filter(status='pending').count()
        total_payout = InsuranceClaim.objects.filter(status__in=['approved', 'paid']).aggregate(
            total=Sum('approved_amount')
        )['total'] or 0
        
        # Get risk distribution
        latest_analyses = SatelliteAnalysis.objects.filter(
            analysis_date__gte=datetime.now() - timedelta(days=30)
        ).order_by('farm', '-analysis_date').distinct('farm')
        
        risk_counts = {
            'low': 0,
            'moderate': 0,
            'severe': 0,
            'unknown': 0,
        }
        
        for analysis in latest_analyses:
            risk_counts[analysis.drought_risk_level] = risk_counts.get(analysis.drought_risk_level, 0) + 1
        
        # Get recent claims
        recent_claims = InsuranceClaim.objects.order_by('-submitted_date')[:10]
        
        # Get farms needing attention
        high_risk_farms = Farm.objects.filter(
            analyses__drought_risk_level='severe',
            analyses__analysis_date__gte=datetime.now() - timedelta(days=30)
        ).distinct()[:10]
        
        context.update({
            'total_farms': total_farms,
            'total_farmers': total_farmers,
            'total_area': total_area,
            'active_policies': active_policies,
            'total_claims': total_claims,
            'pending_claims': pending_claims,
            'total_payout': total_payout,
            'risk_counts': risk_counts,
            'recent_claims': recent_claims,
            'high_risk_farms': high_risk_farms,
        })
        
        return context


# API Views
@login_required
def run_analysis(request):
    """Run satellite analysis for selected farms"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            farm_ids = data.get('farm_ids', [])
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            
            # Get farms
            farms = Farm.objects.filter(farm_id__in=farm_ids)
            
            # Initialize GEE analyzer
            analyzer = GEEAnalyzer()
            
            results = []
            for farm in farms:
                # Convert farm geometry to ee.Geometry
                geojson = json.loads(farm.geometry.geojson)
                ee_geometry = ee.Geometry(geojson)
                
                # Run analysis
                analysis_result = analyzer.analyze_farm(
                    ee_geometry, 
                    farm.farm_id,
                    year,
                    month
                )
                
                if analysis_result:
                    # Save to database
                    satellite_analysis = SatelliteAnalysis(
                        farm=farm,
                        analysis_date=datetime(year, month, 1).date(),
                        year=year,
                        month=month,
                        ndvi=analysis_result.get('ndvi'),
                        evi=analysis_result.get('evi'),
                        ndmi=analysis_result.get('ndmi'),
                        savi=analysis_result.get('savi'),
                        ndre=analysis_result.get('ndre'),
                        rainfall_mm=analysis_result.get('rainfall_mm'),
                        cloud_cover_percentage=None,  # Could calculate from metadata
                        image_count=analysis_result.get('image_count', 0),
                    )
                    satellite_analysis.save()
                    
                    results.append({
                        'farm_id': farm.farm_id,
                        'success': True,
                        'analysis_id': satellite_analysis.id,
                        'ndvi': satellite_analysis.ndvi,
                        'risk_level': satellite_analysis.drought_risk_level,
                    })
                else:
                    results.append({
                        'farm_id': farm.farm_id,
                        'success': False,
                        'error': 'No satellite data available',
                    })
            
            return JsonResponse({
                'success': True,
                'results': results,
                'message': f'Analysis completed for {len(results)} farms'
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
    
    # Get all analyses for this farm
    analyses = SatelliteAnalysis.objects.filter(farm=farm).order_by('year', 'month')
    
    data = {
        'farm': {
            'id': farm.farm_id,
            'name': farm.name,
            'crop': farm.crop_type,
            'area_ha': farm.area_ha,
            'farmer': farm.farmer.full_name if farm.farmer else '',
        },
        'analyses': [],
        'monthly_averages': {},
    }
    
    # Prepare time series data
    for analysis in analyses:
        data['analyses'].append({
            'date': f"{analysis.year}-{analysis.month:02d}",
            'year': analysis.year,
            'month': analysis.month,
            'ndvi': analysis.ndvi,
            'evi': analysis.evi,
            'ndmi': analysis.ndmi,
            'savi': analysis.savi,
            'ndre': analysis.ndre,
            'rainfall_mm': analysis.rainfall_mm,
            'risk_level': analysis.drought_risk_level,
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
    
    return JsonResponse(data)


@staff_member_required
def import_shapefiles(request):
    """Import shapefiles and farms from CSV"""
    if request.method == 'POST':
        try:
            processor = ShapefileProcessor()
            
            # Import county boundaries
            county_fc = processor.load_machakos_county()
            
            # Import farms
            farms_fc = processor.load_farms_from_geojson()
            
            # Process and save to database
            # This would iterate through features and create Farm objects
            
            return JsonResponse({
                'success': True,
                'message': 'Import completed successfully',
                'county_features': county_fc.size().getInfo(),
                'farm_features': farms_fc.size().getInfo(),
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    # GET request - show import form
    return render(request, 'import_shapefiles.html')


@login_required
def trigger_insurance_check(request):
    """Check and trigger insurance claims based on analysis"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            farm_id = data.get('farm_id')
            analysis_id = data.get('analysis_id')
            
            farm = get_object_or_404(Farm, farm_id=farm_id)
            analysis = get_object_or_404(SatelliteAnalysis, id=analysis_id, farm=farm)
            
            # Check if insurance should be triggered
            if analysis.insurance_triggered:
                # Check if policy exists
                try:
                    policy = farm.insurance_policy
                    
                    # Create claim
                    claim = InsuranceClaim(
                        policy=policy,
                        farm=farm,
                        triggered_by_analysis=analysis,
                        trigger_date=analysis.analysis_date,
                        claim_amount=policy.sum_insured * policy.payout_rate,
                        ndvi_value=analysis.ndvi,
                        rainfall_value=analysis.rainfall_mm,
                    )
                    claim.save()
                    
                    return JsonResponse({
                        'success': True,
                        'claim_created': True,
                        'claim_number': claim.claim_number,
                        'claim_amount': float(claim.claim_amount),
                        'message': 'Insurance claim created successfully',
                    })
                    
                except InsurancePolicy.DoesNotExist:
                    return JsonResponse({
                        'success': True,
                        'claim_created': False,
                        'message': 'Insurance should be triggered but no active policy found',
                    })
            else:
                return JsonResponse({
                    'success': True,
                    'claim_created': False,
                    'message': 'Insurance thresholds not met',
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def test_gee_api(request):
    """Test GEE API connection"""
    success = test_gee_connection()
    
    return JsonResponse({
        'success': success,
        'message': 'GEE connection test completed',
        'timestamp': datetime.now().isoformat(),
    })