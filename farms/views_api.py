"""
API views for GEE integration
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime, timedelta
from .utils.gee_utils import GEEAnalyzer, ShapefileProcessor
from .models import Farm, SatelliteAnalysis

@csrf_exempt
def gee_tile_url(request):
    """Generate GEE tile URL for map display"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            index = data.get('index', 'NDVI')
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            
            # Initialize GEE analyzer
            analyzer = GEEAnalyzer()
            
            # Load Machakos boundary
            processor = ShapefileProcessor()
            machakos = processor.load_machakos_county()
            
            # Create date
            date = datetime(year, month, 1)
            
            # Get tile URL (simplified - real implementation would use GEE export)
            # Note: Actual tile URL generation requires GEE export service
            
            return JsonResponse({
                'success': True,
                'index': index,
                'year': year,
                'month': month,
                'tile_url': f'/gee/tiles/{index}/{year}/{month}/{{z}}/{{x}}/{{y}}',
                'message': 'Tile URL generated'
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
            
            analyzer = GEEAnalyzer()
            results = []
            
            for farm_id in farm_ids[:10]:  # Limit to 10 for demo
                try:
                    farm = Farm.objects.get(farm_id=farm_id)
                    
                    # Convert geometry to ee.Geometry
                    geojson = json.loads(farm.geometry.geojson)
                    
                    # Note: Actual GEE integration would happen here
                    # For now, simulate analysis
                    
                    # Create analysis record
                    analysis = SatelliteAnalysis(
                        farm=farm,
                        analysis_date=datetime(year, month, 1),
                        year=year,
                        month=month,
                        ndvi=0.3 + (hash(farm_id) % 100) / 500,  # Simulated
                        ndmi=0.2 + (hash(farm_id) % 100) / 600,  # Simulated
                        savi=0.4 + (hash(farm_id) % 100) / 400,  # Simulated
                        rainfall_mm=50 + (hash(farm_id) % 100),  # Simulated
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
        processor = ShapefileProcessor()
        county_fc = processor.load_machakos_county()
        
        # Convert to GeoJSON
        geojson = {
            'type': 'FeatureCollection',
            'features': []
        }
        
        # Note: Actual implementation would convert ee.FeatureCollection to GeoJSON
        # For demo, return sample data
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
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            # Get analysis data
            analyses = SatelliteAnalysis.objects.all()
            
            if farm_ids:
                analyses = analyses.filter(farm__farm_id__in=farm_ids)
            
            if start_date:
                analyses = analyses.filter(analysis_date__gte=start_date)
            
            if end_date:
                analyses = analyses.filter(analysis_date__lte=end_date)
            
            # Convert to requested format
            if format_type == 'csv':
                import csv
                from django.http import HttpResponse
                
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="analysis_export.csv"'
                
                writer = csv.writer(response)
                writer.writerow([
                    'Farm ID', 'Farm Name', 'Year', 'Month',
                    'NDVI', 'EVI', 'NDMI', 'SAVI', 'NDRE',
                    'Rainfall (mm)', 'Risk Level', 'Insurance Triggered'
                ])
                
                for analysis in analyses:
                    writer.writerow([
                        analysis.farm.farm_id,
                        analysis.farm.name or '',
                        analysis.year,
                        analysis.month,
                        analysis.ndvi or '',
                        analysis.evi or '',
                        analysis.ndmi or '',
                        analysis.savi or '',
                        analysis.ndre or '',
                        analysis.rainfall_mm or '',
                        analysis.drought_risk_level,
                        'Yes' if analysis.insurance_triggered else 'No'
                    ])
                
                return response
                
            elif format_type == 'json':
                data = []
                for analysis in analyses:
                    data.append({
                        'farm_id': analysis.farm.farm_id,
                        'farm_name': analysis.farm.name,
                        'year': analysis.year,
                        'month': analysis.month,
                        'ndvi': analysis.ndvi,
                        'evi': analysis.evi,
                        'ndmi': analysis.ndmi,
                        'savi': analysis.savi,
                        'ndre': analysis.ndre,
                        'rainfall_mm': analysis.rainfall_mm,
                        'risk_level': analysis.drought_risk_level,
                        'insurance_triggered': analysis.insurance_triggered
                    })
                
                return JsonResponse({'data': data}, safe=False)
            
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Unsupported format: {format_type}'
                }, status=400)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)