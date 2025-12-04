#!/usr/bin/env python
"""
Simplified setup script for Machakos Drought System
"""
import os
import sys
import django
import json

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'machakos_aidsttup.settings')

# Setup Django
django.setup()

from farms.models import SubCounty
from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Polygon

def main():
    print("🚀 Setting up Machakos Drought System...")
    
    # 1. Make migrations
    print("📦 Creating migrations...")
    os.system('python manage.py makemigrations')
    
    # 2. Apply migrations
    print("🔄 Applying migrations...")
    os.system('python manage.py migrate')
    
    # 3. Create superuser if doesn't exist
    print("👑 Creating admin user...")
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser(
            username='admin',
            email='admin@machakos.co.ke',
            password='admin123'
        )
        print("   ✅ Created superuser: admin/admin123")
    else:
        print("   ℹ️ Superuser already exists")
    
    # 4. Create Machakos sub-counties
    print("🗺️ Creating Machakos sub-counties...")
    subcounties_data = [
        {
            'name': 'Machakos Town',
            'subcounty_code': 'MAC_001',
            'area_sqkm': 155.4,
            'population': 150000,
            'main_crops': 'Maize, Beans, Vegetables',
            'avg_rainfall': 750,
            'soil_type': 'Volcanic loam',
            'center_lat': -1.5167,
            'center_lon': 37.2667
        },
        {
            'name': 'Mwala',
            'subcounty_code': 'MAC_002',
            'area_sqkm': 895.6,
            'population': 185000,
            'main_crops': 'Maize, Beans, Pigeon peas',
            'avg_rainfall': 600,
            'soil_type': 'Sandy loam',
            'center_lat': -1.35,
            'center_lon': 37.45
        },
        {
            'name': 'Yatta',
            'subcounty_code': 'MAC_003',
            'area_sqkm': 1203.8,
            'population': 210000,
            'main_crops': 'Maize, Sorghum, Cowpeas',
            'avg_rainfall': 550,
            'soil_type': 'Clay loam',
            'center_lat': -1.30,
            'center_lon': 37.60
        },
        {
            'name': 'Kangundo',
            'subcounty_code': 'MAC_004',
            'area_sqkm': 426.5,
            'population': 165000,
            'main_crops': 'Maize, Beans, Coffee',
            'avg_rainfall': 800,
            'soil_type': 'Red volcanic',
            'center_lat': -1.35,
            'center_lon': 37.35
        },
        {
            'name': 'Matungulu',
            'subcounty_code': 'MAC_005',
            'area_sqkm': 395.7,
            'population': 145000,
            'main_crops': 'Maize, Fruits, Vegetables',
            'avg_rainfall': 850,
            'soil_type': 'Clay',
            'center_lat': -1.45,
            'center_lon': 37.35
        },
        {
            'name': 'Kathiani',
            'subcounty_code': 'MAC_006',
            'area_sqkm': 321.9,
            'population': 125000,
            'main_crops': 'Maize, Beans, Macadamia',
            'avg_rainfall': 900,
            'soil_type': 'Volcanic ash',
            'center_lat': -1.38,
            'center_lon': 37.38
        },
        {
            'name': 'Masinga',
            'subcounty_code': 'MAC_007',
            'area_sqkm': 1120.4,
            'population': 195000,
            'main_crops': 'Maize, Sorghum, Millet',
            'avg_rainfall': 500,
            'soil_type': 'Sandy',
            'center_lat': -1.10,
            'center_lon': 37.48
        },
    ]
    
    for data in subcounties_data:
        # Create a simple polygon around the center point
        lat = data['center_lat']
        lon = data['center_lon']
        
        # Create a small bounding box around the center
        coords = [
            (lon - 0.05, lat - 0.05),
            (lon + 0.05, lat - 0.05),
            (lon + 0.05, lat + 0.05),
            (lon - 0.05, lat + 0.05),
            (lon - 0.05, lat - 0.05)
        ]
        
        polygon = Polygon(coords)
        multipolygon = MultiPolygon(polygon)
        
        subcounty, created = SubCounty.objects.update_or_create(
            subcounty_code=data['subcounty_code'],
            defaults={
                'name': data['name'],
                'area_sqkm': data['area_sqkm'],
                'population': data['population'],
                'main_crops': data['main_crops'],
                'avg_rainfall': data['avg_rainfall'],
                'soil_type': data['soil_type'],
                'geom': multipolygon
            }
        )
        
        if created:
            print(f"   ✅ Created: {subcounty.name}")
        else:
            print(f"   ℹ️ Updated: {subcounty.name}")
    
    # 5. Create a test farmer
    print("👨‍🌾 Creating test farmer...")
    from farms.models import Farmer
    
    test_farmer, created = Farmer.objects.update_or_create(
        farmer_id='FARM000001',
        defaults={
            'first_name': 'John',
            'last_name': 'Kamau',
            'phone': '0712345678',
            'email': 'john@example.com',
            'id_number': '12345678',
            'subcounty': SubCounty.objects.first(),
            'ward': 'Machakos Central',
            'village': 'Township'
        }
    )
    
    if created:
        print(f"   ✅ Created test farmer: {test_farmer.full_name}")
    else:
        print(f"   ℹ️ Test farmer already exists")
    
    print("\n" + "="*50)
    print("🎉 SETUP COMPLETE!")
    print("="*50)
    print("\nNext steps:")
    print("1. Run the development server:")
    print("   python manage.py runserver")
    print("\n2. Access the system at:")
    print("   🌐 http://localhost:8000/")
    print("\n3. Login with:")
    print("   👤 Username: admin")
    print("   🔑 Password: admin123")
    print("\n4. Test the map viewer:")
    print("   🗺️ http://localhost:8000/map/")
    print("\n5. Register a farmer:")
    print("   👨‍🌾 http://localhost:8000/farmer/register/")

if __name__ == '__main__':
    main()