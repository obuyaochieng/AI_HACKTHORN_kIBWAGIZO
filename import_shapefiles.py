import geopandas as gpd
import os
from django.contrib.gis.geos import GEOSGeometry
from farms.models import SubCounty, Farm, Farmer
import json

def import_machakos_shapefile(shapefile_path):
    """Import Machakos County shapefile"""
    gdf = gpd.read_file(shapefile_path)
    
    # Ensure correct CRS
    if gdf.crs != 'EPSG:4326':
        gdf = gdf.to_crs('EPSG:4326')
    
    for idx, row in gdf.iterrows():
        # Convert geometry
        geom = GEOSGeometry(row.geometry.wkt)
        
        # Create or update subcounty
        subcounty, created = SubCounty.objects.update_or_create(
            name=row.get('SUBCOUNTY', f'SubCounty_{idx}'),
            defaults={
                'subcounty_code': row.get('SUBCODE', f'CODE_{idx}'),
                'area_sqkm': row.geometry.area * 10000,  # Approximate
                'geom': geom
            }
        )
        
        print(f"{'Created' if created else 'Updated'}: {subcounty.name}")

def import_farms_geojson(geojson_path, farmer_id):
    """Import farms from GeoJSON"""
    with open(geojson_path) as f:
        data = json.load(f)
    
    farmer = Farmer.objects.get(farmer_id=farmer_id)
    
    for idx, feature in enumerate(data['features']):
        # Convert geometry
        geom = GEOSGeometry(json.dumps(feature['geometry']))
        
        # Create farm
        farm = Farm.objects.create(
            farm_id=f"{farmer.farmer_id}_F{idx+1:03d}",
            farmer=farmer,
            name=feature['properties'].get('name', f'{farmer.full_name} Farm {idx+1}'),
            geom=geom,
            area_ha=geom.area * 10000,  # Approximate
            crop_type=feature['properties'].get('crop', 'maize'),
            crop_variety=feature['properties'].get('variety', ''),
            ownership_type='owned'
        )
        
        print(f"Created farm: {farm.farm_id}")

if __name__ == '__main__':
    # Example usage
    # import_machakos_shapefile('path/to/Machakos_County.shp')
    # import_farms_geojson('path/to/farms.geojson', 'FARM123456')
    print("Run this script with actual file paths")