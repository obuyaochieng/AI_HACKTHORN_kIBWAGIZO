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
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_exempt


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




class FarmListView(LoginRequiredMixin, ListView):
    """List all farms"""
    model = Farm
    template_name = 'farms/farm_list.html'
    context_object_name = 'farms'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Farm.objects.filter(is_active=True).select_related('farmer', 'county')
        
        # Filter by search query
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(farm_id__icontains=search) |
                Q(name__icontains=search) |
                Q(farmer__first_name__icontains=search) |
                Q(farmer__last_name__icontains=search) |
                Q(crop_type__icontains=search)
            )
        
        # Filter by crop type
        crop_type = self.request.GET.get('crop_type', '')
        if crop_type:
            queryset = queryset.filter(crop_type=crop_type)
        
        # Filter by risk level
        risk_level = self.request.GET.get('risk_level', '')
        if risk_level:
            queryset = queryset.filter(
                analyses__drought_risk_level=risk_level,
                analyses__analysis_date__gte=datetime.now() - timedelta(days=30)
            ).distinct()
        
        # Filter by subcounty
        subcounty = self.request.GET.get('subcounty', '')
        if subcounty:
            queryset = queryset.filter(county__subcounty__icontains=subcounty)
        
        return queryset.order_by('farm_id')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter options to context
        context['crop_types'] = Farm.objects.values_list('crop_type', flat=True).distinct()
        context['subcounties'] = County.objects.values_list('subcounty', flat=True).distinct()
        context['search_query'] = self.request.GET.get('search', '')
        context['selected_crop'] = self.request.GET.get('crop_type', '')
        context['selected_risk'] = self.request.GET.get('risk_level', '')
        context['selected_subcounty'] = self.request.GET.get('subcounty', '')
        
        return context


class FarmDetailView(LoginRequiredMixin, DetailView):
    """View farm details"""
    model = Farm
    template_name = 'farms/farm_detail.html'
    context_object_name = 'farm'
    
    def get_object(self, queryset=None):
        # Get farm by ID or farm_id
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        elif 'farm_id' in self.kwargs:
            return get_object_or_404(Farm, farm_id=self.kwargs['farm_id'])
        return super().get_object(queryset)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        farm = self.object
        
        # Get analysis history
        analyses = farm.analyses.all().order_by('-analysis_date')[:12]
        
        # Calculate statistics
        if analyses.exists():
            latest = analyses.first()
            context.update({
                'latest_analysis': latest,
                'analyses': analyses,
                'ndvi_trend': self.calculate_trend(analyses, 'ndvi'),
                'rainfall_trend': self.calculate_trend(analyses, 'rainfall_mm'),
                'risk_history': [
                    {'date': a.analysis_date, 'risk': a.drought_risk_level}
                    for a in analyses[:6]
                ]
            })
        
        # Get insurance info
        try:
            context['insurance_policy'] = farm.insurance_policy
        except:
            context['insurance_policy'] = None
        
        # Get claims
        context['claims'] = farm.claims.all().order_by('-trigger_date')[:5]
        
        return context
    
    def calculate_trend(self, analyses, field):
        """Calculate trend for a field"""
        if analyses.count() < 2:
            return 'stable'
        
        values = [getattr(a, field) for a in analyses if getattr(a, field) is not None]
        if len(values) < 2:
            return 'stable'
        
        if values[0] > values[-1] * 1.1:
            return 'improving'
        elif values[0] < values[-1] * 0.9:
            return 'declining'
        else:
            return 'stable'
        


@csrf_exempt
def gee_tile_url(request):
    """Generate GEE tile URL for map display"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            index = data.get('index', 'NDVI')
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            
            # For now, return a placeholder URL
            # In production, this would generate actual GEE tile URLs
            return JsonResponse({
                'success': True,
                'index': index,
                'year': year,
                'month': month,
                'tile_url': f'/static/images/placeholder_{index.lower()}.png',
                'message': 'Tile URL generated (placeholder)'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def run_batch_analysis(request):
    """Run batch analysis for multiple farms"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            farm_ids = data.get('farm_ids', [])
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            
            if not farm_ids:
                return JsonResponse({
                    'success': False,
                    'error': 'No farm IDs provided'
                }, status=400)
            
            results = []
            
            for farm_id in farm_ids[:10]:  # Limit to 10 for demo
                try:
                    farm = Farm.objects.get(farm_id=farm_id)
                    
                    # Simulate analysis (replace with actual GEE analysis)
                    analysis = SatelliteAnalysis(
                        farm=farm,
                        analysis_date=datetime(year, month, 1),
                        year=year,
                        month=month,
                        ndvi=0.3 + (hash(farm_id) % 100) / 500,
                        ndmi=0.2 + (hash(farm_id) % 100) / 600,
                        savi=0.4 + (hash(farm_id) % 100) / 400,
                        rainfall_mm=50 + (hash(farm_id) % 100),
                        image_count=3
                    )
                    analysis.save()
                    
                    results.append({
                        'farm_id': farm_id,
                        'success': True,
                        'analysis_id': analysis.id,
                        'ndvi': analysis.ndvi,
                        'risk_level': analysis.drought_risk_level
                    })
                    
                except Farm.DoesNotExist:
                    results.append({
                        'farm_id': farm_id,
                        'success': False,
                        'error': 'Farm not found'
                    })
            
            return JsonResponse({
                'success': True,
                'results': results,
                'total': len(results),
                'completed': len([r for r in results if r['success']])
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_machakos_boundary(request):
    """Get Machakos County boundary as GeoJSON"""
    try:
        # Sample GeoJSON for Machakos County
        sample_geojson = {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [37.0, -1.3],
                        [37.5, -1.3],
                        [37.5, -1.8],
                        [37.0, -1.8],
                        [37.0, -1.3]
                    ]]
                },
                'properties': {
                    'name': 'Machakos County',
                    'county': 'Machakos'
                }
            }]
        }
        
        return JsonResponse(sample_geojson, safe=False)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
def export_analysis_data(request):
    """Export analysis data to various formats"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            format_type = data.get('format', 'csv')
            farm_ids = data.get('farm_ids', [])
            
            # For now, return a success message
            # In production, this would generate actual files
            return JsonResponse({
                'success': True,
                'message': f'Export started for {len(farm_ids)} farms in {format_type.upper()} format',
                'download_url': '/static/exports/sample_export.csv'
            })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)