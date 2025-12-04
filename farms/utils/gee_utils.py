"""
Google Earth Engine utilities for Machakos drought monitoring
"""
import ee
import os
import json
from datetime import datetime, timedelta
from django.conf import settings
import geopandas as gpd
from shapely.geometry import mapping
import time

# Initialize GEE
def initialize_gee():
    """Initialize Google Earth Engine with service account"""
    try:
        # Try different initialization methods
        if hasattr(settings, 'GEE_SERVICE_ACCOUNT') and settings.GEE_SERVICE_ACCOUNT:
            credentials = ee.ServiceAccountCredentials(
                settings.GEE_SERVICE_ACCOUNT,
                settings.GEE_PRIVATE_KEY_PATH
            )
            ee.Initialize(credentials, project=settings.GEE_PROJECT_ID)
        else:
            # Try without service account (for development)
            ee.Initialize(project=settings.GEE_PROJECT_ID)
        
        print("✅ Google Earth Engine initialized successfully")
        return True
    except Exception as e:
        print(f"❌ GEE initialization failed: {e}")
        
        # Try the high-volume endpoint
        try:
            ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
            print("✅ Connected via high-volume endpoint")
            return True
        except Exception as e2:
            print(f"❌ High-volume endpoint also failed: {e2}")
            return False


class GEEAnalyzer:
    """Main class for GEE analysis operations"""
    
    def __init__(self):
        if not initialize_gee():
            raise Exception("Failed to initialize Google Earth Engine")
        
        # Constants from your friend's JavaScript code
        self.SENTINEL_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
        self.CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
        
        # Years to analyze
        self.YEARS = list(range(2021, 2026))  # 2021-2025
        
        # Indices to calculate
        self.INDICES = ['NDVI', 'EVI', 'NDMI', 'SAVI', 'NDRE']
        
        # Visualization parameters
        self.VIS_PARAMS = {
            'NDVI': {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'EVI': {'min': -1, 'max': 1, 'palette': ['blue', 'white', 'green']},
            'NDMI': {'min': -1, 'max': 1, 'palette': ['white', 'blue']},
            'SAVI': {'min': 0.1, 'max': 0.7, 'palette': ['brown', 'yellow', 'green']},
            'NDRE': {'min': 0.1, 'max': 0.45, 'palette': ['purple', 'yellow', 'green']},
        }
    
    def mask_sentinel2(self, image):
        """Cloud mask for Sentinel-2"""
        qa = image.select('QA60')
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
            qa.bitwiseAnd(cirrus_bit_mask).eq(0)
        )
        return image.updateMask(mask).divide(10000)
    
    def calculate_indices(self, image):
        """Calculate all vegetation indices from Sentinel-2"""
        # NDVI
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        
        # EVI
        evi = image.expression(
            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
            {
                'NIR': image.select('B8'),
                'RED': image.select('B4'),
                'BLUE': image.select('B2')
            }
        ).rename('EVI')
        
        # NDMI
        ndmi = image.normalizedDifference(['B8', 'B11']).rename('NDMI')
        
        # SAVI
        savi = image.expression(
            '((NIR - RED) / (NIR + RED + L)) * (1 + L)',
            {
                'NIR': image.select('B8'),
                'RED': image.select('B4'),
                'L': 0.5
            }
        ).rename('SAVI')
        
        # NDRE
        ndre = image.normalizedDifference(['B8', 'B5']).rename('NDRE')
        
        return image.addBands([ndvi, evi, ndmi, savi, ndre])
    
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
            .map(self.calculate_indices)
        
        # Check if we have images
        count = s2_collection.size().getInfo()
        if count == 0:
            return None, 0
        
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
            'evi': stats_dict.get('EVI'),
            'ndmi': stats_dict.get('NDMI'),
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
    
    def analyze_farm(self, farm_geometry, farm_id, year, month):
        """Complete analysis for a single farm"""
        # Get indices
        indices = self.get_monthly_indices(farm_geometry, year, month)
        
        # Get rainfall
        rainfall = self.get_rainfall(farm_geometry, year, month)
        
        if indices is None:
            return None
        
        return {
            'farm_id': farm_id,
            'year': year,
            'month': month,
            'ndvi': indices['ndvi'],
            'evi': indices['evi'],
            'ndmi': indices['ndmi'],
            'savi': indices['savi'],
            'ndre': indices['ndre'],
            'rainfall_mm': rainfall,
            'image_count': indices['image_count'],
        }
    
    def analyze_multiple_farms(self, farm_features, year, month):
        """
        Analyze multiple farms at once (more efficient)
        
        Args:
            farm_features: ee.FeatureCollection with farm geometries
            year: int
            month: int
        """
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        
        # Get Sentinel-2 collection
        s2_collection = ee.ImageCollection(self.SENTINEL_COLLECTION) \
            .filterBounds(farm_features.geometry()) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .map(self.mask_sentinel2) \
            .map(self.calculate_indices) \
            .median()
        
        # Add farm ID property
        farm_features = farm_features.map(
            lambda feature: feature.set('farm_id', feature.get('id'))
        )
        
        # Calculate zonal statistics for all farms
        results = s2_collection.reduceRegions(
            collection=farm_features,
            reducer=ee.Reducer.mean(),
            scale=10,
            tileScale=2
        )
        
        # Get rainfall for each farm
        rainfall_image = ee.ImageCollection(self.CHIRPS_COLLECTION) \
            .filterDate(start_date, end_date) \
            .select('precipitation') \
            .sum()
        
        # Add rainfall to results
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
            formatted_results.append({
                'farm_id': props.get('farm_id'),
                'year': year,
                'month': month,
                'ndvi': props.get('NDVI'),
                'evi': props.get('EVI'),
                'ndmi': props.get('NDMI'),
                'savi': props.get('SAVI'),
                'ndre': props.get('NDRE'),
                'rainfall_mm': props.get('rainfall_mm'),
            })
        
        return formatted_results
    
    def get_timelapse_url(self, geometry, start_year, start_month, end_year, end_month, index='NDVI'):
        """
        Generate timelapse URL for a geometry
        
        Returns:
            URL for timelapse GIF
        """
        start_date = ee.Date.fromYMD(start_year, start_month, 1)
        end_date = ee.Date.fromYMD(end_year, end_month, 1)
        
        # Create image collection
        collection = ee.ImageCollection(self.SENTINEL_COLLECTION) \
            .filterBounds(geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .map(self.mask_sentinel2) \
            .map(self.calculate_indices)
        
        # Create timelapse
        timelapse = collection.select(index)
        
        # Generate URL
        vis_params = self.VIS_PARAMS.get(index, {'min': 0, 'max': 1})
        
        # This would typically use ee.Image.getThumbURL() but needs proper setup
        # For now, return the image collection info
        count = timelapse.size().getInfo()
        
        return {
            'index': index,
            'image_count': count,
            'start_date': start_date.format().getInfo(),
            'end_date': end_date.format().getInfo(),
            'vis_params': vis_params,
        }
    
    def export_to_drive(self, farm_features, year, months=None):
        """
        Export farm analysis results to Google Drive (like JavaScript version)
        """
        if months is None:
            months = list(range(1, 13))
        
        # Create monthly collections
        monthly_collections = []
        
        for month in months:
            start_date = ee.Date.fromYMD(year, month, 1)
            end_date = start_date.advance(1, 'month')
            
            # Get median image
            median_image = ee.ImageCollection(self.SENTINEL_COLLECTION) \
                .filterBounds(farm_features.geometry()) \
                .filterDate(start_date, end_date) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
                .map(self.mask_sentinel2) \
                .map(self.calculate_indices) \
                .median()
            
            # Add farm ID
            farm_features = farm_features.map(
                lambda f: f.set('farm_id', f.get('id'))
            )
            
            # Calculate zonal stats
            monthly_results = median_image.reduceRegions(
                collection=farm_features,
                reducer=ee.Reducer.mean(),
                scale=10,
                tileScale=2
            ).map(lambda f: f.set({
                'year': year,
                'month': month
            }))
            
            monthly_collections.append(monthly_results)
        
        # Combine all months
        all_results = ee.FeatureCollection(monthly_collections).flatten()
        
        # Export to Drive
        task = ee.batch.Export.table.toDrive(
            collection=all_results,
            description=f'Machakos_Farm_Analysis_{year}',
            folder='GEE_Exports',
            fileFormat='CSV'
        )
        
        task.start()
        
        return {
            'task_id': task.id,
            'status': 'RUNNING',
            'description': f'Exporting {len(months)} months for {farm_features.size().getInfo()} farms'
        }


class ShapefileProcessor:
    """Process shapefiles for GEE integration"""
    
    def __init__(self):
        self.gee_analyzer = GEEAnalyzer()
    
    def load_machakos_county(self, shapefile_path=None):
        """Load Machakos County boundary"""
        if shapefile_path is None:
            shapefile_path = getattr(settings, 'SHAPEFILE_PATH', 'assets/shapefiles/Machakos_County.shp')
        
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")
        
        # Load with geopandas
        gdf = gpd.read_file(shapefile_path)
        
        # Filter for Machakos if needed
        if 'county' in gdf.columns:
            gdf = gdf[gdf['county'].str.contains('Machakos', case=False, na=False)]
        
        # Convert to GeoJSON
        geojson = json.loads(gdf.to_json())
        
        # Convert to ee.FeatureCollection
        ee_features = []
        for feature in geojson['features']:
            ee_geom = ee.Geometry(feature['geometry'])
            ee_feature = ee.Feature(ee_geom, feature['properties'])
            ee_features.append(ee_feature)
        
        return ee.FeatureCollection(ee_features)
    
    def load_farms_from_geojson(self, geojson_path=None):
        """Load farm polygons from GeoJSON"""
        if geojson_path is None:
            geojson_path = getattr(settings, 'FARMS_GEOJSON_PATH', 'assets/farms.geojson')
        
        if not os.path.exists(geojson_path):
            raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")
        
        with open(geojson_path, 'r') as f:
            geojson = json.load(f)
        
        # Convert to ee.FeatureCollection
        ee_features = []
        for feature in geojson['features']:
            # Ensure farm_id exists
            properties = feature['properties']
            if 'farm_id' not in properties:
                if 'id' in properties:
                    properties['farm_id'] = str(properties['id'])
                else:
                    properties['farm_id'] = f"farm_{len(ee_features)}"
            
            ee_geom = ee.Geometry(feature['geometry'])
            ee_feature = ee.Feature(ee_geom, properties)
            ee_features.append(ee_feature)
        
        return ee.FeatureCollection(ee_features)
    
    def upload_to_gee_assets(self, feature_collection, asset_name, overwrite=False):
        """
        Upload feature collection to GEE Assets
        
        Note: This requires proper GEE permissions and may need to be run
        separately with ee.batch.Export
        """
        try:
            # Create asset ID
            asset_id = f"projects/{settings.GEE_PROJECT_ID}/assets/{asset_name}"
            
            # Check if asset exists
            try:
                existing = ee.FeatureCollection(asset_id)
                if overwrite:
                    print(f"Overwriting existing asset: {asset_id}")
                else:
                    print(f"Asset already exists: {asset_id}")
                    return asset_id
            except:
                pass
            
            # Start export task
            task = ee.batch.Export.table.toAsset(
                collection=feature_collection,
                description=f'Upload {asset_name}',
                assetId=asset_id
            )
            
            task.start()
            
            print(f"Upload started. Task ID: {task.id}")
            print(f"Check status with: earthengine task list")
            
            return asset_id
            
        except Exception as e:
            print(f"Error uploading to GEE Assets: {e}")
            return None


def test_gee_connection():
    """Test GEE connection and basic functionality"""
    print("Testing GEE connection...")
    
    try:
        analyzer = GEEAnalyzer()
        print("✅ GEE Analyzer initialized successfully")
        
        # Create a test point (Machakos center)
        test_point = ee.Geometry.Point([37.2667, -1.5167])
        
        # Test indices calculation
        test_result = analyzer.get_monthly_indices(test_point, 2023, 6, buffer_km=5)
        
        if test_result:
            print(f"✅ Test analysis successful")
            print(f"   NDVI: {test_result['ndvi']:.3f}")
            print(f"   Image count: {test_result['image_count']}")
        else:
            print("⚠️ No images found for test location/date")
        
        # Test rainfall
        rainfall = analyzer.get_rainfall(test_point, 2023, 6, buffer_km=5)
        if rainfall:
            print(f"✅ Rainfall: {rainfall:.1f} mm")
        
        return True
        
    except Exception as e:
        print(f"❌ GEE test failed: {e}")
        return False