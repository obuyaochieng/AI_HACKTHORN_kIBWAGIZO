# ============================================================================
# CLASSIFICATION_MODEL_TRAINER.py
# ============================================================================

import pandas as pd
import numpy as np
import pickle
import json
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class RainfallClassificationModel:
    """Train and save rainfall classification model"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.cluster_profiles = {}
        
    def prepare_features(self, df):
        """Prepare features from rainfall data"""
        print("Preparing features...")
        
        # Calculate location-level features
        location_features = df.groupby('id_number').apply(self._calculate_location_features)
        
        # Calculate temporal features
        monthly_features = self._calculate_monthly_features(df)
        quarterly_features = self._calculate_quarterly_features(df)
        seasonal_features = self._calculate_seasonal_features(df)
        
        # Combine all features
        all_features = location_features.join(monthly_features, how='left')
        all_features = all_features.join(quarterly_features, how='left')
        all_features = all_features.join(seasonal_features, how='left')
        all_features = all_features.fillna(0)
        
        return all_features
    
    def _calculate_location_features(self, group):
        """Calculate features for a single location"""
        metrics = {}
        
        # Basic statistics
        metrics['total_rainfall'] = group['rainfall_mm'].sum()
        metrics['mean_rainfall'] = group['rainfall_mm'].mean()
        metrics['median_rainfall'] = group['rainfall_mm'].median()
        metrics['std_rainfall'] = group['rainfall_mm'].std()
        metrics['cv_rainfall'] = metrics['std_rainfall'] / metrics['mean_rainfall'] if metrics['mean_rainfall'] > 0 else 0
        
        # Rainy days metrics
        rainy_days = group[group['rainfall_mm'] > 0]
        metrics['rainy_days_count'] = len(rainy_days)
        metrics['rainy_days_percent'] = (len(rainy_days) / len(group)) * 100 if len(group) > 0 else 0
        metrics['mean_rainy_day_intensity'] = rainy_days['rainfall_mm'].mean() if len(rainy_days) > 0 else 0
        
        # Dry spell metrics
        dry_spells = []
        current_spell = 0
        for val in group['rainfall_mm'].values:
            if val == 0:
                current_spell += 1
            else:
                if current_spell > 0:
                    dry_spells.append(current_spell)
                current_spell = 0
        if current_spell > 0:
            dry_spells.append(current_spell)
        
        metrics['max_dry_spell'] = max(dry_spells) if dry_spells else 0
        metrics['avg_dry_spell'] = np.mean(dry_spells) if dry_spells else 0
        metrics['dry_spell_frequency'] = len(dry_spells) / len(group) if len(group) > 0 else 0
        
        return pd.Series(metrics)
    
    def _calculate_monthly_features(self, df):
        """Calculate monthly features for all locations"""
        monthly_features_list = []
        
        for location_id in df['id_number'].unique():
            location_data = df[df['id_number'] == location_id]
            
            monthly_dict = {'id_number': location_id}
            
            for month in range(1, 13):
                month_data = location_data[location_data['month'] == month]['rainfall_mm']
                monthly_dict[f'month_{month}_mean'] = month_data.mean() if len(month_data) > 0 else 0
                monthly_dict[f'month_{month}_std'] = month_data.std() if len(month_data) > 0 else 0
            
            monthly_features_list.append(monthly_dict)
        
        return pd.DataFrame(monthly_features_list).set_index('id_number')
    
    def _calculate_quarterly_features(self, df):
        """Calculate quarterly features"""
        if 'quarter' not in df.columns:
            df['quarter'] = df['month'].apply(lambda x: f"Q{(x-1)//3 + 1}")
        
        quarterly_features_list = []
        
        for location_id in df['id_number'].unique():
            location_data = df[df['id_number'] == location_id]
            
            quarterly_dict = {'id_number': location_id}
            
            for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
                quarter_data = location_data[location_data['quarter'] == quarter]['rainfall_mm']
                quarterly_dict[f'quarter_{quarter}_mean'] = quarter_data.mean() if len(quarter_data) > 0 else 0
                quarterly_dict[f'quarter_{quarter}_sum'] = quarter_data.sum() if len(quarter_data) > 0 else 0
            
            quarterly_features_list.append(quarterly_dict)
        
        return pd.DataFrame(quarterly_features_list).set_index('id_number')
    
    def _calculate_seasonal_features(self, df):
        """Calculate seasonal features"""
        if 'season' not in df.columns:
            def get_season(month):
                if month in [12, 1, 2]:
                    return 'DJF'
                elif month in [3, 4, 5]:
                    return 'MAM'
                elif month in [6, 7, 8]:
                    return 'JJA'
                else:
                    return 'SON'
            df['season'] = df['month'].apply(get_season)
        
        seasonal_features_list = []
        
        for location_id in df['id_number'].unique():
            location_data = df[df['id_number'] == location_id]
            
            seasonal_dict = {'id_number': location_id}
            
            for season in ['DJF', 'MAM', 'JJA', 'SON']:
                season_data = location_data[location_data['season'] == season]['rainfall_mm']
                seasonal_dict[f'season_{season}_mean'] = season_data.mean() if len(season_data) > 0 else 0
                seasonal_dict[f'season_{season}_sum'] = season_data.sum() if len(season_data) > 0 else 0
            
            seasonal_features_list.append(seasonal_dict)
        
        return pd.DataFrame(seasonal_features_list).set_index('id_number')
    
    def select_features(self, features_df):
        """Select key features for clustering"""
        selected = [
            'total_rainfall', 'mean_rainfall', 'cv_rainfall',
            'rainy_days_percent', 'mean_rainy_day_intensity',
            'max_dry_spell', 'avg_dry_spell', 'dry_spell_frequency'
        ]
        
        # Add critical months (based on your analysis)
        for month in [11, 12, 6]:  # Nov, Dec, Jun
            selected.append(f'month_{month}_mean')
        
        # Filter to available features
        self.feature_columns = [f for f in selected if f in features_df.columns]
        
        return features_df[self.feature_columns]
    
    def train(self, df, n_clusters=4):
        """Train the classification model"""
        print("Training model...")
        
        # Prepare features
        features_df = self.prepare_features(df)
        
        # Select features
        X = self.select_features(features_df)
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train KMeans
        self.model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        cluster_labels = self.model.fit_predict(X_scaled)
        
        # Create cluster profiles
        features_df['cluster'] = cluster_labels
        self._create_cluster_profiles(features_df)
        
        print(f"Model trained with {n_clusters} clusters")
        print(f"Trained on {len(features_df)} locations")
        
        return features_df
    
    def _create_cluster_profiles(self, features_df):
        """Create profiles for each cluster"""
        for cluster_id in sorted(features_df['cluster'].unique()):
            cluster_data = features_df[features_df['cluster'] == cluster_id]
            
            profile = {
                'size': len(cluster_data),
                'avg_total_rainfall': cluster_data['total_rainfall'].mean(),
                'avg_rainy_days': cluster_data['rainy_days_percent'].mean(),
                'avg_max_dry_spell': cluster_data['max_dry_spell'].mean(),
                'typical_months': self._get_typical_months(cluster_data)
            }
            
            # Determine cluster type
            profile['cluster_type'] = self._classify_cluster_type(profile)
            
            self.cluster_profiles[cluster_id] = profile
    
    def _get_typical_months(self, cluster_data):
        """Get typical wet/dry months for cluster"""
        typical = {}
        for month in range(1, 13):
            col = f'month_{month}_mean'
            if col in cluster_data.columns:
                month_avg = cluster_data[col].mean()
                if month_avg > cluster_data[col].mean() * 1.2:
                    typical[month] = 'Wet'
                elif month_avg < cluster_data[col].mean() * 0.8:
                    typical[month] = 'Dry'
                else:
                    typical[month] = 'Normal'
        return typical
    
    def _classify_cluster_type(self, profile):
        """Classify cluster type based on characteristics"""
        if profile['avg_total_rainfall'] > 10000:
            return "High Rainfall Zone"
        elif profile['avg_total_rainfall'] > 5000:
            if profile['avg_rainy_days'] > 50:
                return "Moderate Rainfall, Frequent Rain"
            else:
                return "Moderate Rainfall, Seasonal"
        elif profile['avg_total_rainfall'] > 1000:
            if profile['avg_max_dry_spell'] > 200:
                return "Low Rainfall, Drought Prone"
            else:
                return "Low Rainfall, Stable"
        else:
            return "Arid Zone"
    
    def predict_drought_risk(self, features):
        """Predict drought risk for a single location"""
        risk_score = 0
        
        # Factor 1: Low rainfall
        if features['total_rainfall'] < 1000:
            risk_score += 2
        elif features['total_rainfall'] < 5000:
            risk_score += 1
        
        # Factor 2: High variability
        if features['cv_rainfall'] > 1.5:
            risk_score += 2
        elif features['cv_rainfall'] > 1.0:
            risk_score += 1
        
        # Factor 3: Long dry spells
        if features['max_dry_spell'] > 250:
            risk_score += 2
        elif features['max_dry_spell'] > 150:
            risk_score += 1
        
        # Factor 4: Low rainy days
        if features['rainy_days_percent'] < 10:
            risk_score += 2
        elif features['rainy_days_percent'] < 20:
            risk_score += 1
        
        # Classify risk
        if risk_score >= 7:
            return "Very High"
        elif risk_score >= 5:
            return "High"
        elif risk_score >= 3:
            return "Moderate"
        else:
            return "Low"
    
    def save_model(self, model_path='rainfall_classification_model.pkl'):
        """Save the trained model"""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns,
            'cluster_profiles': self.cluster_profiles
        }
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"Model saved to {model_path}")
        
        # Also save cluster profiles as JSON for easy access
        profiles_path = 'cluster_profiles.json'
        with open(profiles_path, 'w') as f:
            json.dump(self.cluster_profiles, f, indent=2)
        
        print(f"Cluster profiles saved to {profiles_path}")

# ============================================================================
# TRAINING SCRIPT
# ============================================================================
if __name__ == "__main__":
    # Load your data
    df = pd.read_csv('outpu.csv')
    
    # Initialize and train model
    classifier = RainfallClassificationModel()
    results = classifier.train(df, n_clusters=4)
    
    # Save model
    classifier.save_model()
    
    # Save results
    results.to_csv('classification_results.csv')
    print("Training complete!")