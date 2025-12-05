
RAINFALL ZONE CLASSIFICATION MODEL
====================================

Model Information:
------------------
• Training Date: 2025-12-05 08:26:39
• Number of Zones: 3
• Number of Farms: 190
• Model Type: KMeans Clustering
• Silhouette Score: 0.291

Files:
------
1. rainfall_zone_model.pkl - Main model file (pickle format)
2. zone_profiles.json - Zone descriptions and characteristics
3. farm_classifications.csv - All farm classifications
4. feature_summary.csv - Statistical summary of features
5. predictor.py - Ready-to-use prediction class

Zone Distribution:
-----------------
Zone_1    95
Zone_2    63
Zone_3    32

How to Use:
-----------
1. Load the model: predictor = RainfallZonePredictor('rainfall_zone_model.pkl')
2. Predict zone: result = predictor.predict([12 monthly values])
3. Results include zone, drought risk, and premium multiplier

For Insurance Companies:
-----------------------
• Use premium_multiplier for pricing
• Use drought_risk for risk assessment
• Use zone_type for product segmentation
