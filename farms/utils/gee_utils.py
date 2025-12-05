"""
WORKING Google Earth Engine utilities for Machakos drought monitoring
"""

import ee
import os
import json
from datetime import datetime, timedelta
from django.conf import settings
import time

def initialize_gee():
    """Initialize GEE with your project ID"""
    try:
        # Get project ID from settings
        project_id = getattr(settings, 'GEE_PROJECT_ID', 'eco-avenue-411501')
        
        # Initialize with project ID
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
        self.LANDSAT_COLLECTION = "LANDSAT/LC08/C02/T1_L2"  # For Land Surface Temperature
        
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
    
    def mask_landsat8(self, image):
        """Cloud mask for Landsat 8"""
        # Bit 3 is cloud shadow, bit 5 is cloud
        cloudShadowBitMask = 1 << 3
        cloudsBitMask = 1 << 5
        qa = image.select('QA_PIXEL')
        mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(
            qa.bitwiseAnd(cloudsBitMask).eq(0)
        )
        return image.updateMask(mask)
    
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
        
        # Additional indices
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
    
    def calculate_lst(self, landsat_image):
        """Calculate Land Surface Temperature from Landsat 8"""
        # Convert to TOA reflectance
        opticalBands = landsat_image.select('SR_B.').multiply(0.0000275).add(-0.2)
        thermalBand = landsat_image.select('ST_B10').multiply(0.00341802).add(149.0)
        
        # Calculate NDVI
        ndvi = opticalBands.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
        
        # Calculate vegetation proportion
        pv = ndvi.expression(
            '((ndvi - ndvi_min) / (ndvi_max - ndvi_min)) ** 2',
            {
                'ndvi': ndvi,
                'ndvi_min': 0.2,
                'ndvi_max': 0.5
            }
        ).rename('PV')
        
        # Calculate emissivity
        emissivity = pv.expression(
            '0.004 * pv + 0.986',
            {'pv': pv}
        ).rename('EMISSIVITY')
        
        # Calculate LST in Kelvin
        lst_k = thermalBand.expression(
            '(BT / (1 + (0.00115 * BT / 1.4388) * log(emissivity)))',
            {
                'BT': thermalBand,
                'emissivity': emissivity
            }
        ).rename('LST_K')
        
        # Convert to Celsius
        lst_c = lst_k.expression(
            'lst_k - 273.15',
            {'lst_k': lst_k}
        ).rename('LST')
        
        return lst_c
    
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
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
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
        
        # Try to get Land Surface Temperature
        lst = None
        try:
            landsat_collection = ee.ImageCollection(self.LANDSAT_COLLECTION) \
                .filterBounds(geometry) \
                .filterDate(start_date, end_date) \
                .map(self.mask_landsat8)
            
            if landsat_collection.size().getInfo() > 0:
                landsat_median = landsat_collection.median()
                lst_image = self.calculate_lst(landsat_median)
                lst_stats = lst_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=30,
                    maxPixels=1e9
                )
                lst = lst_stats.get('LST').getInfo()
        except:
            lst = None
        
        return {
            'ndvi': stats_dict.get('NDVI'),
            'ndmi': stats_dict.get('NDMI'),
            'bsi': stats_dict.get('BSI'),
            'evi': stats_dict.get('EVI'),
            'savi': stats_dict.get('SAVI'),
            'ndre': stats_dict.get('NDRE'),
            'lst': lst,
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
    
    def analyze_farm(self, farm, year, month):
        """Complete analysis for a farm model instance"""
        try:
            # Convert farm geometry to ee.Geometry
            if farm.geometry_geojson:
                geojson = json.loads(farm.geometry_geojson)
                geometry = ee.Geometry(geojson)
            else:
                # Use centroid if no geometry
                geometry = ee.Geometry.Point([farm.longitude, farm.latitude]).buffer(100)  # 100m buffer
            
            # Get indices
            indices = self.get_monthly_indices(geometry, year, month, buffer_km=0.5)
            
            # Get rainfall
            rainfall = self.get_rainfall(geometry, year, month, buffer_km=0.5)
            
            if indices is None:
                return None
            
            return {
                'farm_id': farm.farm_id,
                'year': year,
                'month': month,
                'ndvi': indices['ndvi'],
                'ndmi': indices['ndmi'],
                'bsi': indices['bsi'],
                'evi': indices['evi'],
                'savi': indices['savi'],
                'ndre': indices['ndre'],
                'lst': indices.get('lst'),
                'rainfall_mm': rainfall,
                'image_count': indices['image_count'],
            }
            
        except Exception as e:
            print(f"Error analyzing farm {farm.farm_id}: {e}")
            return None
    
    def analyze_all_farms(self, year, month):
        """
        Analyze all farms at once (more efficient)
        Returns list of farm analysis results
        """
        print(f"📊 Analyzing all farms for {year}-{month}...")
        
        try:
            # Load farms from GEE assets
            farms = self.load_farms_from_gee()
            
            # Create date range
            start_date = ee.Date.fromYMD(year, month, 1)
            end_date = start_date.advance(1, 'month')
            
            # Get Sentinel-2 median image
            s2_image = ee.ImageCollection(self.SENTINEL_COLLECTION) \
                .filterBounds(farms.geometry()) \
                .filterDate(start_date, end_date) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
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
                
                # Get farm properties
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
                    'image_count': props.get('image_count', 1),
                    'properties': farm_props
                })
            
            print(f"✅ Analyzed {len(formatted_results)} farms")
            return formatted_results
            
        except Exception as e:
            print(f"❌ Error in batch analysis: {e}")
            return []
    
    def get_timelapse_data(self, geometry, start_year, start_month, end_year, end_month, index='NDVI'):
        """
        Get timelapse data for a geometry
        """
        start_date = ee.Date.fromYMD(start_year, start_month, 1)
        end_date = ee.Date.fromYMD(end_year, end_month, 1)
        
        # Create image collection
        collection = ee.ImageCollection(self.SENTINEL_COLLECTION) \
            .filterBounds(geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .map(self.mask_sentinel2) \
            .map(self.compute_indices)
        
        # Get monthly composites
        monthly_data = []
        current_date = start_date
        
        while current_date.millis().lt(end_date.millis()):
            month_start = current_date
            month_end = month_start.advance(1, 'month')
            
            monthly_collection = collection.filterDate(month_start, month_end)
            
            if monthly_collection.size().getInfo() > 0:
                monthly_median = monthly_collection.median()
                
                stats = monthly_median.select(index).reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=10,
                    maxPixels=1e9
                )
                
                value = stats.get(index).getInfo()
                
                monthly_data.append({
                    'date': month_start.format('YYYY-MM').getInfo(),
                    'year': month_start.get('year').getInfo(),
                    'month': month_start.get('month').getInfo(),
                    index: value,
                })
            
            current_date = month_end
        
        return {
            'index': index,
            'data': monthly_data,
            'start_date': start_date.format().getInfo(),
            'end_date': end_date.format().getInfo(),
            'count': len(monthly_data),
        }
    
    def export_to_drive(self, farms, year, months=None, description=None):
        """
        Export analysis results to Google Drive
        """
        if months is None:
            months = list(range(1, 13))
        
        if description is None:
            description = f'Machakos_Farm_Analysis_{year}'
        
        try:
            # Load farms from GEE
            gee_farms = self.load_farms_from_gee()
            
            # Filter farms if specific IDs provided
            if farms and isinstance(farms, list):
                # This would require matching farm IDs between Django and GEE
                pass
            
            monthly_collections = []
            
            for month in months:
                start_date = ee.Date.fromYMD(year, month, 1)
                end_date = start_date.advance(1, 'month')
                
                # Get median image
                median_image = ee.ImageCollection(self.SENTINEL_COLLECTION) \
                    .filterBounds(gee_farms.geometry()) \
                    .filterDate(start_date, end_date) \
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
                    .map(self.mask_sentinel2) \
                    .map(self.compute_indices) \
                    .median()
                
                # Add farm ID
                gee_farms = gee_farms.map(
                    lambda f: f.set('farm_id', f.get('id'))
                )
                
                # Calculate zonal stats
                monthly_results = median_image.reduceRegions(
                    collection=gee_farms,
                    reducer=ee.Reducer.mean(),
                    scale=10,
                    tileScale=2
                ).map(lambda f: f.set({
                    'year': year,
                    'month': month,
                    'analysis_date': start_date.format('YYYY-MM-dd')
                }))
                
                monthly_collections.append(monthly_results)
            
            # Combine all months
            all_results = ee.FeatureCollection(monthly_collections).flatten()
            
            # Export to Drive
            task = ee.batch.Export.table.toDrive(
                collection=all_results,
                description=description,
                folder='GEE_Exports',
                fileFormat='CSV',
                selectors=['farm_id', 'year', 'month', 'analysis_date', 
                          'NDVI', 'NDMI', 'BSI', 'EVI', 'SAVI', 'NDRE']
            )
            
            task.start()
            
            print(f"✅ Export task started: {task.id}")
            
            return {
                'task_id': task.id,
                'status': 'RUNNING',
                'description': description,
                'farms': gee_farms.size().getInfo(),
                'months': len(months),
            }
            
        except Exception as e:
            print(f"❌ Export error: {e}")
            return None


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
        print("\n2. Analyzing sample farm...")
        
        # Create a test point (Machakos center)
        test_point = ee.Geometry.Point([37.2667, -1.5167])
        
        # Get current month for testing
        current_date = datetime.now()
        last_month = current_date.month - 1 if current_date.month > 1 else 12
        last_year = current_date.year if current_date.month > 1 else current_date.year - 1
        
        result = analyzer.get_monthly_indices(
            test_point,
            last_year,
            last_month,
            buffer_km=1
        )
        
        if result:
            print(f"   ✅ Test analysis successful!")
            print(f"   NDVI: {result.get('ndvi', 'N/A')}")
            print(f"   NDMI: {result.get('ndmi', 'N/A')}")
            print(f"   BSI: {result.get('bsi', 'N/A')}")
            print(f"   Images: {result.get('image_count', 0)}")
        
        # Test 3: Get rainfall
        print("\n3. Getting rainfall data...")
        rainfall = analyzer.get_rainfall(test_point, last_year, last_month, buffer_km=1)
        
        if rainfall:
            print(f"   ✅ Rainfall data: {rainfall:.1f} mm")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False


# Helper functions
def get_gee_tile_url(geometry, index='NDVI', year=None, month=None):
    """Generate tile URL for map display (simplified)"""
    try:
        analyzer = WorkingGEEAnalyzer()
        
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        
        # Get image
        image = ee.ImageCollection(analyzer.SENTINEL_COLLECTION) \
            .filterBounds(geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .map(analyzer.mask_sentinel2) \
            .map(analyzer.compute_indices) \
            .median() \
            .select(index)
        
        # Get visualization parameters
        vis_params = analyzer.VIS_PARAMS.get(index, {'min': 0, 'max': 1})
        
        # Generate tile URL
        map_id = image.getMapId(vis_params)
        
        return {
            'tile_url': map_id['tile_fetcher'].url_format,
            'index': index,
            'year': year,
            'month': month,
            'vis_params': vis_params,
        }
        
    except Exception as e:
        print(f"Error generating tile URL: {e}")
        return None


def calculate_risk_from_gee(ndvi, rainfall, ndmi=None, bsi=None):
    """Calculate risk score from GEE indices"""
    score = 0
    
    # NDVI contributes 40%
    if ndvi is not None:
        if ndvi < 0.2:
            score += 40
        elif ndvi < 0.3:
            score += 30
        elif ndvi < 0.4:
            score += 20
        elif ndvi < 0.6:
            score += 10
    
    # Rainfall contributes 30%
    if rainfall is not None:
        if rainfall < 25:
            score += 30
        elif rainfall < 50:
            score += 20
        elif rainfall < 75:
            score += 10
    
    # NDMI contributes 20%
    if ndmi is not None:
        if ndmi < 0:
            score += 20
        elif ndmi < 0.2:
            score += 10
    
    # BSI contributes 10%
    if bsi is not None:
        if bsi > 0.3:
            score += 10
    
    # Determine risk level
    if score >= 70:
        return 'high', score
    elif score >= 40:
        return 'moderate', score
    else:
        return 'low', score