.3300,35.9350,Njoro,2016-05-22,11,0.33,15,202,0.14,30,maturity
NK001,-0.3300,35.9350,Njoro,2016-06-01,12,0.32,22,224,0.18,28,harvest
```

---

### **8.2 Farm-Level Summary Dataset**

```csv
farm_id,lat,lon,subcounty,year,ndvi_mean,ndvi_min,rainfall_total,rainfall_max_daily,soil_moisture_mean,temp_max_mean,crop_failure,yield_bags_per_acre,insurance_payout
NK001,-0.3300,35.9350,Njoro,2016,0.48,0.32,224,32,0.24,28.5,1,7,15000
NK002,-0.3100,35.9100,Njoro,2016,0.45,0.30,198,28,0.22,29.2,1,5,15000
NK003,-0.3500,35.9600,Njoro,2016,0.52,0.38,245,45,0.28,27.8,0,18,0
NK004,-0.2500,35.7300,Molo,2016,0.50,0.35,268,38,0.30,26.5,0,16,0
NK006,-0.7100,36.4300,Naivasha,2016,0.55,0.42,312,55,0.35,25.2,0,22,0
```

---

## **Part 9: Quick Start - Minimum Viable Dataset**

### **For Your Hackathon Demo, You MUST Have:**

✅ **1. Nakuru County Boundary** (1 file)
- Download from GADM or Kenya Open Data

✅ **2. 10-20 Sample Farm Locations** (1 CSV file)
- Create manually with lat/lon for Njoro, Molo, Naivasha

✅ **3. NDVI Time-Series** (1 CSV file)
- Export from Google Earth Engine using script above
- March-July 2016, weekly values

✅ **4. Rainfall Time-Series** (1 CSV file)
- Export CHIRPS data from GEE
- March-July 2016, weekly totals

✅ **5. Combined Dataset** (1 CSV file)
- Merge NDVI + Rainfall by farm_id and date
- Add crop_failure column (1 if NDVI<0.4 and rainfall<200mm, else 0)

---

## **Part 10: Download Script (Run This Today)**

### **Complete Python Script to Process Data:**

```python
# ============================================
# NAKURU DATA PROCESSING PIPELINE
# Run after exporting from Google Earth Engine
# ============================================

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

# ============================================
# STEP 1: Load Nakuru Boundary
# ============================================

# Option A: From GADM
nakuru = gpd.read_file('gadm41_KEN_1.shp')
nakuru = nakuru[nakuru['NAME_1'] == 'Nakuru']
nakuru.to_file('nakuru_boundary.geojson', driver='GeoJSON')

print("✅ Nakuru boundary saved")

# ============================================
# STEP 2: Create Sample Farms
# ============================================

farms = pd.DataFrame([
    {'id': 'NK001', 'name': 'Njoro Central', 'lat': -0.3300, 'lon': 35.9350, 'subcounty': 'Njoro'},
    {'id': 'NK002', 'name': 'Njoro West', 'lat': -0.3100, 'lon': 35.9100, 'subcounty': 'Njoro'},
    {'id': 'NK003', 'name': 'Njoro East', 'lat': -0.3500, 'lon': 35.9600, 'subcounty': 'Njoro'},
    {'id': 'NK004', 'name': 'Molo Town', 'lat': -0.2500, 'lon': 35.7300, 'subcounty': 'Molo'},
    {'id': 'NK005', 'name': 'Elburgon', 'lat': -0.4200, 'lon': 35.6800, 'subcounty': 'Molo'},
    {'id': 'NK006', 'name': 'Naivasha East', 'lat': -0.7100, 'lon': 36.4300, 'subcounty': 'Naivasha'},
    {'id': 'NK007', 'name': 'Kinangop', 'lat': -0.5900, 'lon': 36.6500, 'subcounty': 'Naivasha'},
    {'id': 'NK008', 'name': 'Gilgil North', 'lat': -0.5000, 'lon': 36.3200, 'subcounty': 'Gilgil'},
    {'id': 'NK009', 'name': 'Bahati', 'lat': -0.1800, 'lon': 36.0200, 'subcounty': 'Nakuru'},
    {'id': 'NK010', 'name': 'Subukia', 'lat': -0.3000, 'lon': 36.1500, 'subcounty': 'Subukia'},
])

farms.to_csv('sample_farms.csv', index=False)
print("✅ Sample farms created")

# ============================================
# STEP 3: Load GEE Exports
# ============================================

# Load NDVI time series (exported from GEE)
ndvi_df = pd.read_csv('nakuru_ndvi_weekly_2016.csv')
ndvi_df = ndvi_df[['id', 'date', 'week', 'mean']].rename(columns={'mean': 'ndvi'})

# Load rainfall time series
rainfall_df = pd.read_csv('nakuru_rainfall_weekly_2016.csv')
rainfall_df = rainfall_df[['id', 'date', 'week', 'mean']].rename(columns={'mean': 'rainfall_mm'})

# Load soil moisture (if available)
# soilmoisture_df = pd.read_csv('nakuru_soil_moisture_timeseries_2016.csv')

print("✅ GEE data loaded")

# ============================================
# STEP 4: Merge Datasets
# ============================================

# Merge NDVI and rainfall
combined = ndvi_df.merge(rainfall_df, on=['id', 'date', 'week'], how='outer')

# Add farm metadata
combined = combined.merge(farms[['id', 'name', 'lat', 'lon', 'subcounty']], on='id')

# Calculate cumulative rainfall
combined = combined.sort_values(['id', 'week'])
combined['rainfall_cumulative'] = combined.groupby('id')['rainfall_mm'].cumsum()

# Add crop stages (approximate)
def get_crop_stage(week):
    if week <= 2: return 'planting'
    elif week <= 4: return 'germination'
    elif week <= 8: return 'vegetative'
    elif week <= 10: return 'flowering'
    elif week <= 14: return 'grain_filling'
    else: return 'maturity'

combined['crop_stage'] = combined['week'].apply(get_crop_stage)

# Identify crop failure
combined['stress_indicator'] = (
    (combined['ndvi'] < 0.42) &  # Low vegetation health
    (combined['rainfall_cumulative'] < 200)  # Low total rainfall
).astype(int)

print("✅ Datasets merged")

# ============================================
# STEP 5: Calculate Summary Statistics
# ============================================

summary = combined.groupby('id').agg({
    'ndvi': ['mean', 'min', 'max'],
    'rainfall_mm': 'sum',
    'stress_indicator': 'max'  # 1 if any week showed stress
}).reset_index()

summary.columns = ['farm_id', 'ndvi_mean', 'ndvi_min', 'ndvi_max', 
                   'rainfall_total', 'crop_failure']

# Add farm info
summary = summary.merge(farms[['id', 'name', 'lat', 'lon', 'subcounty']], 
                        left_on='farm_id', right_on='id')

# Simulate yield data (for demo - replace with real data if available)
summary['yield_bags_per_acre'] = np.where(
    summary['crop_failure'] == 1,
    np.random.randint(5, 10, len(summary)),  # Failed crops: 5-10 bags
    np.random.randint(18, 25, len(summary))  # Successful crops: 18-25 bags
)

# Insurance payout (KES 15,000 if crop failed)
summary['insurance_payout'] = np.where(summary['crop_failure'] == 1, 15000, 0)

print("✅ Summary statistics calculated")

# ============================================
# STEP 6: Save Final Datasets
# ============================================

combined.to_csv('nakuru_timeseries_complete.csv', index=False)
summary.to_csv('nakuru_farm_summary.csv', index=False)

print("✅ Final datasets saved:")
print("   - nakuru_timeseries_complete.csv")
print("   - nakuru_farm_summary.csv")

# ============================================
# STEP 7: Quick Visualization
# ============================================

# Plot NDVI time series for all farms
plt.figure(figsize=(12, 6))
for farm_id in combined['id'].unique():
    farm_data = combined[combined['id'] == farm_id]
    plt.plot(farm_data['week'], farm_data['ndvi'], marker='o', label=farm_id)

plt.axhline(y=0.4, color='r', linestyle='--', label='Critical Threshold')
plt.xlabel('Week (March - July 2016)')
plt.ylabel('NDVI')
plt.title('Crop Health Over Time - Nakuru County 2016')
plt.legend()
plt.grid(True)
plt.savefig('ndvi_timeseries.png', dpi=300, bbox_inches='tight')
print("✅ Visualization saved: ndvi_timeseries.png")

# Show summary
print("\n" + "="*60)
print("NAKURU 2016 DROUGHT SUMMARY")
print("="*60)
print(f"Total farms monitored: {len(summary)}")
print(f"Farms with crop failure: {summary['crop_failure'].sum()} ({summary['crop_failure'].mean()*100:.1f}%)")
print(f"Average NDVI: {summary['ndvi_mean'].mean():.2f}")
print(f"Average rainfall: {summary['rainfall_total'].mean():.0f} mm")
print(f"Total insurance payouts: KES {summary['insurance_payout'].sum():,}")
print("="*60)
```

---

## **Summary: Your Data Checklist**

### **TODAY (Must Have):**
- [ ] Nakuru boundary (GeoJSON)
- [ ] 10 sample farm locations (CSV)
- [ ] NDVI time-series March-July 2016 (CSV from GEE)
- [ ] Rainfall time-series March-July 2016 (CSV from GEE)
- [ ] Combined dataset (run Python script above)

### **NICE TO HAVE (If Time):**
- [ ] Soil moisture data
- [ ] Temperature data
- [ ] Elevation/slope
- [ ] Historical baseline (2010-2015)
- [ ] Land cover classification

### **FOR PRODUCTION (Post-Hackathon):**
- [ ] Real farmer GPS coordinates (from cooperatives)
- [ ] Historical yield data (Ministry of Agriculture)
- [ ] Insurance claims data (from partners)
- [ ] Current season data (2024-2025)

---

**Next Steps:**
1. Run the Google Earth Engine scripts (all at once - takes 10-20 minutes)
2. Download the CSV exports from your Google Drive
3. Run the Python processing script
4. Load into your React app
5. Demo ready! 🚀

**Want me to help you set up the GEE scripts or process the data once you have it?**