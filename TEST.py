"""
Test views to verify GEE integration works in Django
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime

try:
    from .utils.gee_working import WorkingGEEAnalyzer, test_working_gee
    GEE_AVAILABLE = True
except Exception as e:
    print(f"⚠️ GEE not available: {e}")
    GEE_AVAILABLE = False


@csrf_exempt
def test_gee_api(request):
    """Test GEE API endpoint"""
    if request.method == 'GET':
        try:
            if not GEE_AVAILABLE:
                return JsonResponse({
                    'success': False,
                    'error': 'GEE not available'
                })
            
            # Run test
            test_result = test_working_gee()
            
            return JsonResponse({
                'success': test_result,
                'message': 'GEE test completed',
                'gee_available': GEE_AVAILABLE,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def get_farm_list(request):
    """Get list of farms from GEE assets"""
    if request.method == 'GET':
        try:
            if not GEE_AVAILABLE:
                return JsonResponse({
                    'success': False,
                    'error': 'GEE not available'
                })
            
            analyzer = WorkingGEEAnalyzer()
            farms = analyzer.load_farms_from_gee()
            
            # Get farm count
            count = farms.size().getInfo()
            
            # Get first few farms for preview
            farm_list = []
            for i in range(min(10, count)):
                farm = ee.Feature(farms.toList(count).get(i))
                props = farm.getInfo()['properties']
                
                farm_list.append({
                    'id': props.get('id', f'farm_{i}'),
                    'name': props.get('name', f'Farm {i}'),
                    'crop': props.get('crop', 'unknown'),
                    'landuse': props.get('landuse', 'unknown'),
                    'operator': props.get('operator', ''),
                    'type': props.get('type', ''),
                })
            
            return JsonResponse({
                'success': True,
                'farm_count': count,
                'farms': farm_list,
                'asset_path': analyzer.FARM_ASSETS_PATH
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def analyze_single_farm(request, farm_id):
    """Analyze a single farm"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            year = data.get('year', datetime.now().year)
            month = data.get('month', datetime.now().month)
            
            if not GEE_AVAILABLE:
                return JsonResponse({
                    'success': False,
                    'error': 'GEE not available'
                })
            
            analyzer = WorkingGEEAnalyzer()
            farms = analyzer.load_farms_from_gee()
            
            # Find farm by ID
            farm = None
            farm_list = farms.toList(farms.size().getInfo())
            
            for i in range(farm_list.length().getInfo()):
                f = ee.Feature(farm_list.get(i))
                if str(f.get('id').getInfo()) == str(farm_id):
                    farm = f
                    break
            
            if not farm:
                return JsonResponse({
                    'success': False,
                    'error': f'Farm {farm_id} not found'
                })
            
            # Analyze farm
            result = analyzer.analyze_farm(farm, year, month)
            
            if result:
                return JsonResponse({
                    'success': True,
                    'farm_id': farm_id,
                    'year': year,
                    'month': month,
                    'data': result
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No data available for this period'
                })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)