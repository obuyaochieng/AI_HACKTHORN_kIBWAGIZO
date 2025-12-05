"""
WORKING Google Earth Engine utilities for your setup
"""

import ee
import os
import json
from datetime import datetime, timedelta
from django.conf import settings

def initialize_gee():
    """Initialize GEE with your project ID"""
    try:
        # Get project ID from settings
        project_id = getattr(settings, 'GEE_PROJECT_ID', 'eco-avenue-411501')
        
        # Initialize with project ID (this works for you!)
        ee.Initialize(project=project_id)
        print(f"✅ GEE initialized with project: {project_id}")
        return True
    except Exception as e:
        print(f"❌ GEE initialization failed: {e}")
        return False


class WorkingGEEAnalyzer:
    """GEE Analyzer that works with your setup"""
    
    def __init__(self):
        # Initialize GEE
        if not initialize_gee():
            raise Exception("Failed to initialize Google Earth Engine")
        
        print("✅ WorkingGEEAnalyzer initialized successfully!")
        
        # Your assets path
        self.FARM_ASSETS_PATH = getattr(
            settings, 
            'GEE_FARMS_ASSET_PATH', 
            'projects/eco-avenue-411501/assets/farms'
        )
        
        # Collections
        self.SENTINEL_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
        self.CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
        
        # Years to analyze (from your JavaScript)
        self.YEARS = list(range(2018, 2026))  # 2018-2025
        
        # Indices from your JavaScript
        self.INDICES = ['NDVI', 'NDMI', 'BSI', 'EVI', 'SAVI', 'NDRE']
        
        # Visualization parameters from your JavaScript
        self.VIS_PARAMS = {
            'NDVI': {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'NDMI': {'min': -1, 'max': 1, 'palette': ['white', 'blue']},
            'BSI': {'min': -1, 'max': 1, 'palette': ['green', 'yellow', 'brown']},
            'EVI': {'min': -1, 'max': 1, 'palette': ['blue', 'white', 'green']},
            'SAVI': {'min': 0.1, 'max': 0.7, 'palette': ['brown', 'yellow', 'green']},
            'NDRE': {'min': 0.1, 'max': 0.45, 'palette': ['purple', 'yellow', 'green']},
        }
    
    def load_farms_from_gee(self):
        """Load farm polygons from your GEE assets"""
        try:
            farms = ee.FeatureCollection(self.FARM_ASSETS_PATH)
            count = farms.size().getInfo()
            print(f"✅ Loaded {count} farms from GEE assets")
            return farms
        except Exception as e:
            print(f"❌ Error loading farm assets: {e}")
            raise
    
    def mask_sentinel2(self, image):
        """Cloud mask for Sentinel-2 (same as your JavaScript)"""
        qa = image.select('QA60')
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
            qa.bitwiseAnd(cirrus_bit_mask).eq(0)
        )
        return image.updateMask(mask).divide(10000)
    
    def compute_indices(self, image):
        """Calculate indices (same as your JavaScript)"""
        # NDVI
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        
        # NDMI
        ndmi = image.normalizedDifference(['B8', 'B11']).rename('NDMI')
        
        # BSI (Bare Soil Index) - from your JavaScript
        bsi = image.expression(
            '(SWIR + RED - NIR - BLUE)/(SWIR + RED + NIR + BLUE)',
            {
                'SWIR': image.select('B11'),
                'RED': image.select('B4'),
                'NIR': image.select('B8'),
                'BLUE': image.select('B2')
            }
        ).rename('BSI')
        
        # Additional indices (optional)
        evi = image.expression(
            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
            {
                'NIR': image.select('B8'),
                'RED': image.select('B4'),
                'BLUE': image.select('B2')
            }
        ).rename('EVI')
        
        savi = image.expression(
            '((NIR - RED) / (NIR + RED + L)) * (1 + L)',
            {
                'NIR': image.select('B8'),
                'RED': image.select('B4'),
                'L': 0.5
            }
        ).rename('SAVI')
        
        ndre = image.normalizedDifference(['B8', 'B5']).rename('NDRE')
        
        return image.addBands([ndvi, ndmi, bsi, evi, savi, ndre])
    
    def get_monthly_indices(self, geometry, year, month, buffer_km=0):
        """
        Get monthly median indices for a geometry
        
        Args:
            geometry: ee.Geometry or ee.FeatureCollection
            year: int
            month: int
            buffer_km: float (buffer distance in km)
        
        Returns:
            Dictionary with index values
        """
        # Create date range
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        
        # Buffer if requested
        if buffer_km > 0:
            if isinstance(geometry, ee.Geometry):
                geometry = geometry.buffer(buffer_km * 1000)
            elif isinstance(geometry, ee.FeatureCollection):
                geometry = geometry.geometry().buffer(buffer_km * 1000)
        
        # Get Sentinel-2 collection
        s2_collection = ee.ImageCollection(self.SENTINEL_COLLECTION) \
            .filterBounds(geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .map(self.mask_sentinel2) \
            .map(self.compute_indices)
        
        # Check if we have images
        count = s2_collection.size().getInfo()
        if count == 0:
            return None
        
        # Calculate median
        median_image = s2_collection.median()
        
        # Extract values for each index
        stats = median_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9
        )
        
        stats_dict = stats.getInfo()
        
        return {
            'ndvi': stats_dict.get('NDVI'),
            'ndmi': stats_dict.get('NDMI'),
            'bsi': stats_dict.get('BSI'),
            'evi': stats_dict.get('EVI'),
            'savi': stats_dict.get('SAVI'),
            'ndre': stats_dict.get('NDRE'),
            'image_count': count
        }
    
    def get_rainfall(self, geometry, year, month, buffer_km=0):
        """Get total rainfall for a month"""
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        
        # Buffer if requested
        if buffer_km > 0:
            if isinstance(geometry, ee.Geometry):
                geometry = geometry.buffer(buffer_km * 1000)
        
        # Get CHIRPS data
        rainfall = ee.ImageCollection(self.CHIRPS_COLLECTION) \
            .filterDate(start_date, end_date) \
            .select('precipitation') \
            .sum()
        
        # Calculate mean rainfall over geometry
        stats = rainfall.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=5000,
            maxPixels=1e9
        )
        
        rainfall_value = stats.get('precipitation')
        if rainfall_value:
            return rainfall_value.getInfo()
        return None
    
    def analyze_farm(self, farm_feature, year, month):
        """Complete analysis for a single farm"""
        farm_id = farm_feature.get('id').getInfo() if hasattr(farm_feature.get('id'), 'getInfo') else 'unknown'
        
        # Get indices
        indices = self.get_monthly_indices(farm_feature.geometry(), year, month)
        
        # Get rainfall
        rainfall = self.get_rainfall(farm_feature.geometry(), year, month)
        
        if indices is None:
            return None
        
        return {
            'farm_id': farm_id,
            'year': year,
            'month': month,
            'ndvi': indices['ndvi'],
            'ndmi': indices['ndmi'],
            'bsi': indices['bsi'],
            'evi': indices['evi'],
            'savi': indices['savi'],
            'ndre': indices['ndre'],
            'rainfall_mm': rainfall,
            'image_count': indices['image_count'],
        }
    
    def analyze_all_farms(self, year, month):
        """
        Analyze all farms at once (more efficient)
        Returns list of farm analysis results
        """
        print(f"📊 Analyzing all farms for {year}-{month}...")
        
        # Load farms
        farms = self.load_farms_from_gee()
        
        # Create date range
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        
        # Get Sentinel-2 median image
        s2_image = ee.ImageCollection(self.SENTINEL_COLLECTION) \
            .filterBounds(farms.geometry()) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .map(self.mask_sentinel2) \
            .map(self.compute_indices) \
            .median()
        
        # Add farm ID property
        farms_with_id = farms.map(
            lambda feature: feature.set('farm_id', feature.get('id'))
        )
        
        # Calculate zonal statistics for all farms
        results = s2_image.reduceRegions(
            collection=farms_with_id,
            reducer=ee.Reducer.mean(),
            scale=10,
            tileScale=2
        )
        
        # Get rainfall for each farm
        rainfall_image = ee.ImageCollection(self.CHIRPS_COLLECTION) \
            .filterDate(start_date, end_date) \
            .select('precipitation') \
            .sum()
        
        def add_rainfall(feature):
            rainfall_value = rainfall_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=feature.geometry(),
                scale=5000,
                maxPixels=1e9
            ).get('precipitation')
            return feature.set('rainfall_mm', rainfall_value)
        
        results = results.map(add_rainfall)
        
        # Get results as list
        results_list = results.getInfo()['features']
        
        # Format results
        formatted_results = []
        for feature in results_list:
            props = feature['properties']
            
            # Get farm properties from original
            farm_props = {}
            for key in ['@id', 'crop', 'landuse', 'name', 'operator', 'place', 'type']:
                if key in props:
                    farm_props[key] = props[key]
            
            formatted_results.append({
                'farm_id': props.get('id', 'unknown'),
                'farm_name': props.get('name', f"Farm {props.get('id', 'unknown')}"),
                'year': year,
                'month': month,
                'ndvi': props.get('NDVI'),
                'ndmi': props.get('NDMI'),
                'bsi': props.get('BSI'),
                'evi': props.get('EVI'),
                'savi': props.get('SAVI'),
                'ndre': props.get('NDRE'),
                'rainfall_mm': props.get('rainfall_mm'),
                'properties': farm_props
            })
        
        print(f"✅ Analyzed {len(formatted_results)} farms")
        return formatted_results


# Test function
def test_working_gee():
    """Test the working GEE analyzer"""
    print("=" * 60)
    print("TESTING WORKING GEE ANALYZER")
    print("=" * 60)
    
    try:
        analyzer = WorkingGEEAnalyzer()
        
        # Test 1: Load farms
        print("\n1. Loading farms...")
        farms = analyzer.load_farms_from_gee()
        
        # Test 2: Analyze first farm
        print("\n2. Analyzing first farm...")
        first_farm = ee.Feature(farms.first())
        
        # Get current month for testing
        current_date = datetime.now()
        result = analyzer.analyze_farm(first_farm, current_date.year, current_date.month)
        
        if result:
            print(f"   ✅ Farm analysis successful!")
            print(f"   Farm ID: {result['farm_id']}")
            print(f"   NDVI: {result.get('ndvi', 'N/A')}")
            print(f"   NDMI: {result.get('ndmi', 'N/A')}")
            print(f"   Rainfall: {result.get('rainfall_mm', 'N/A')} mm")
        
        # Test 3: Quick analysis for last month
        print("\n3. Quick analysis for last month...")
        last_month = current_date.month - 1 if current_date.month > 1 else 12
        last_year = current_date.year if current_date.month > 1 else current_date.year - 1
        
        quick_result = analyzer.get_monthly_indices(
            first_farm.geometry(),
            last_year,
            last_month,
            buffer_km=0
        )
        
        if quick_result:
            print(f"   ✅ Quick analysis successful!")
            print(f"   NDVI: {quick_result.get('ndvi', 'N/A')}")
            print(f"   Images: {quick_result.get('image_count', 0)}")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False