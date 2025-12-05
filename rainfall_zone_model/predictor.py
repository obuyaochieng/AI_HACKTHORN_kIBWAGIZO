
import pickle
import numpy as np
import json

class RainfallZonePredictor:
    """Production-ready rainfall zone predictor"""
    
    def __init__(self, model_path='rainfall_zone_model.pkl'):
        """Load trained model"""
        with open(model_path, 'rb') as f:
            self.model_data = pickle.load(f)
        
        self.zone_model = self.model_data['zone_model']
        self.scaler = self.model_data['scaler']
        self.feature_names = self.model_data['feature_names']
        self.zone_profiles = self.model_data['zone_profiles']
        
    def predict(self, monthly_rainfall, farm_id="new_farm"):
        """Predict zone for new farm"""
        # Calculate features
        features = self._calculate_features(monthly_rainfall)
        
        # Prepare and scale features
        feature_vector = self._prepare_features(features)
        feature_vector_scaled = self.scaler.transform([feature_vector])
        
        # Predict
        zone_id = int(self.zone_model.predict(feature_vector_scaled)[0])
        
        # Get results
        return self._format_result(zone_id, features, farm_id)
    
    def _calculate_features(self, rainfall):
        """Calculate features from monthly rainfall"""
        features = {}
        rainfall = np.array(rainfall)
        
        # Basic stats
        features['total_rainfall'] = float(np.sum(rainfall))
        features['mean_rainfall'] = float(np.mean(rainfall))
        features['std_rainfall'] = float(np.std(rainfall))
        
        if features['mean_rainfall'] > 0:
            features['cv_rainfall'] = float(features['std_rainfall'] / features['mean_rainfall'])
        else:
            features['cv_rainfall'] = 0.0
        
        # Rainy days
        rainy_days = rainfall[rainfall > 0]
        features['rainy_days_percent'] = float((len(rainy_days) / 12) * 100)
        
        # Dry spells
        dry_spells = []
        current = 0
        for rain in rainfall:
            if rain == 0:
                current += 1
            else:
                if current > 0:
                    dry_spells.append(current)
                current = 0
        if current > 0:
            dry_spells.append(current)
        
        features['max_dry_spell'] = int(max(dry_spells)) if dry_spells else 0
        
        # Monthly means
        for i, rain in enumerate(rainfall, 1):
            features[f'month_{i}_mean'] = float(rain)
        
        return features
    
    def _prepare_features(self, features):
        """Prepare feature vector in correct order"""
        vector = []
        for name in self.feature_names:
            vector.append(features.get(name, 0.0))
        return vector
    
    def _format_result(self, zone_id, features, farm_id):
        """Format prediction result"""
        profile = self.zone_profiles.get(zone_id, {})
        
        return {
            'farm_id': farm_id,
            'zone_id': zone_id,
            'zone_name': profile.get('zone_name', f'Zone_{zone_id+1}'),
            'zone_type': profile.get('zone_type', 'Unknown'),
            'drought_risk': profile.get('drought_risk', 'Unknown'),
            'total_rainfall': features['total_rainfall'],
            'rainy_days_percent': features['rainy_days_percent'],
            'premium_multiplier': profile.get('premium_multiplier', 1.3),
            'risk_score': profile.get('risk_score', 5)
        }

# Example usage:
# predictor = RainfallZonePredictor('rainfall_zone_model.pkl')
# result = predictor.predict([50, 40, 60, 80, 100, 20, 10, 5, 15, 40, 120, 90])
