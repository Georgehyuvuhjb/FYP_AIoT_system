"""
ai_predictor.py
Anomaly detection predictor with patient-specific threshold search.
Loads trained model and preprocessor, provides scoring and duration-based threshold discovery.
"""

import os
import sys
import numpy as np
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_preprocessing import load_config
from ml_artifacts import load_model_artifact


class AnomalyPredictor:
    """
    Wrapper around trained anomaly detection model.
    Handles preprocessing, scoring, and patient-specific threshold search.
    """
    
    def __init__(self, config=None, artifact_name=None):
        """
        Initialize predictor by loading trained artifact.
        
        Args:
            config: Configuration dict (loaded from YAML if None)
            artifact_name: Name of artifact to load (uses config default if None)
        """
        self.config = config or load_config()
        
        # Load artifact
        self.preprocessor, self.model, self.metadata = load_model_artifact(
            config=self.config,
            artifact_name=artifact_name,
        )
        
        self.model_name = self.metadata['model_name']
        self.feature_names = np.array(self.metadata['feature_names'])
        self.numerical_cols = self.metadata['numerical_cols']
        self.categorical_cols = self.metadata['categorical_cols']
        
        print(f'✓ AnomalyPredictor initialized')
        print(f'  Model: {self.model_name}')
        print(f'  Features: {len(self.feature_names)}')
    
    def predict_score(self, X):
        """
        Compute anomaly scores for input features.
        NOTE: Scores depend on the model type:
        - IsolationForest: negative scores (more negative = more anomalous)
        - OneClassSVM: negative scores for outliers, positive for inliers
        
        Args:
            X: DataFrame with feature columns (will be preprocessed)
        
        Returns:
            np.ndarray: Array of anomaly scores
        """
        # Preprocess
        X_processed = self.preprocessor.transform(X)
        
        # Use decision_function when available: many anomaly models define
        # 0 as the inlier/outlier boundary in this space.
        if hasattr(self.model, 'decision_function'):
            scores = self.model.decision_function(X_processed)
        elif hasattr(self.model, 'score_samples'):
            scores = self.model.score_samples(X_processed)
        else:
            raise AttributeError('Model does not support decision_function or score_samples')
        
        return scores
    
    def predict_scores_batch(self, X_list):
        """
        Compute anomaly scores for a batch of feature rows.
        
        Args:
            X_list: List of DataFrames or single concatenated DataFrame
        
        Returns:
            np.ndarray: Array of anomaly scores (one per row)
        """
        if isinstance(X_list, list) and len(X_list) > 0:
            X = pd.concat(X_list, ignore_index=True)
        else:
            X = X_list
        
        return self.predict_score(X)
    
    def get_default_threshold(self):
        """
        Get default threshold based on training data percentile.
        
        Returns:
            float: Threshold value (default from config percentile)
        """
        percentile = float(self.config['threshold_search']['threshold_percentile'])
        
        if 'threshold' in self.metadata:
            return self.metadata['threshold']
        
        # Model-specific safe defaults.
        # For both One-Class SVM and Isolation Forest, the decision boundary
        # from decision_function is typically at 0 (negative = outlier).
        if self.model_name in ('one_class_svm', 'isolation_forest'):
            return 0.0
        
        # Would be computed from training scores during initial_training.py
        # For now, return a placeholder
        print(f'Warning: No default threshold in metadata. Using config percentile: {percentile}')
        return None
    
    def compute_threshold_for_patient(
        self,
        base_features_row,
        duration_range=None,
        debounce_steps=None,
    ):
        """
        Find personalized duration threshold for a patient via duration sweep.
        
        Strategy:
        1. Start with patient's base features (7-day rolling stats, etc.)
        2. Iterate duration from 0 to max(simulated durations)
        3. For each duration:
           a. Recalculate duration-dependent fields
           b. Preprocess and score
           c. Check if score exceeds threshold
        4. Return the first duration where score consistently exceeds threshold (debounced)
        
        Args:
            base_features_row: pd.Series with patient's current features
            duration_range: Tuple (min, max) or None to use config defaults
            debounce_steps: Number of consecutive steps to exceed threshold. 
                           None = use config default
        
        Returns:
            dict: {
                'threshold_duration': float (None if not found),
                'threshold_score': float,
                'scores_by_duration': dict {duration: score},
                'reason': str (why search ended),
            }
        """
        if duration_range is None:
            duration_range = (
                self.config['threshold_search']['duration_min'],
                self.config['threshold_search']['duration_max'],
            )
        
        if debounce_steps is None:
            debounce_steps = self.config['threshold_search']['debounce_steps']
        arming_normal_steps = int(self.config['threshold_search'].get('arming_normal_steps', 3))
        
        duration_step = self.config['threshold_search']['duration_step']
        min_dur, max_dur = duration_range
        
        # Get default threshold from model
        default_threshold = self.get_default_threshold()
        is_autoencoder = self.model_name == 'simple_autoencoder'
        is_xgboost_or_rf = self.model_name in ('xgboost', 'random_forest')
        
        if default_threshold is None:
            percentile = float(self.config['threshold_search']['threshold_percentile'])
            # Fallback: Autoencoder uses upper tail (e.g., 100 - 5 = 95), others use lower tail (5)
            if is_autoencoder:
                percentile = 100 - percentile
            
            train_scores = self.metadata.get('train_metrics', {}).get('train_scores', {})
            pct_key = f'p{int(percentile)}'
            default_threshold = train_scores.get(pct_key)
            if default_threshold is None:
                default_threshold = train_scores.get('p75', 0.1) if is_autoencoder else train_scores.get('p25', -0.5)
            print(f'Using fallback threshold ({pct_key}): {default_threshold:.4f}')
        
        print(f'\nSearching for patient threshold...')
        print(f'  Duration range: {min_dur}-{max_dur}s (step: {duration_step}s)')
        print(f'  Threshold limit: {default_threshold:.4f} (scores lower than this are anomalies)')
        print(f'  Arming normals: {arming_normal_steps} consecutive normal points')
        print(f'  Debounce: {debounce_steps} steps')
        
        scores_by_duration = {}
        consecutive_exceeds = 0
        consecutive_normals = 0
        armed = False
        armed_at_duration = None
        threshold_duration = None
        threshold_score = None
        reason = 'max_duration_reached'
        
        # Iterate through durations
        for duration in np.arange(min_dur, max_dur + duration_step, duration_step):
            # Make a copy of base features
            features = base_features_row.copy()
            
            # Recalculate duration-dependent fields
            features = self._recalculate_duration_features(features, duration)
            
            # Score (reshape to 2D for sklearn/keras)
            score = self.predict_score(features.to_frame().T)[0]
            scores_by_duration[float(duration)] = float(score)
            
            if is_autoencoder or is_xgboost_or_rf:
                is_anomaly = score > default_threshold
            else:
                is_anomaly = score < default_threshold

            # Phase 1: Arm only after stable normal window.
            if not armed:
                if not is_anomaly:
                    consecutive_normals += 1
                else:
                    consecutive_normals = 0

                if consecutive_normals >= arming_normal_steps:
                    armed = True
                    armed_at_duration = float(duration)
                # Ignore anomalies before armed.
                continue
            
            # Phase 2: Detect true anomalies only after arming.
            if is_anomaly:
                consecutive_exceeds += 1
                
                if consecutive_exceeds >= debounce_steps:
                    threshold_duration = float(duration - (debounce_steps - 1) * duration_step)
                    threshold_score = float(score)
                    reason = 'threshold_found_after_arming'
                    break
            else:
                consecutive_exceeds = 0

        if threshold_duration is None and not armed:
            reason = 'no_stable_normal_window_found'
        elif threshold_duration is None and armed:
            reason = 'max_duration_reached_after_arming'
        
        result = {
            'threshold_duration': threshold_duration,
            'threshold_score': threshold_score,
            'scores_by_duration': scores_by_duration,
            'reason': reason,
            'total_durations_tested': len(scores_by_duration),
            'armed': armed,
            'armed_at_duration': armed_at_duration,
        }
        
        if threshold_duration is not None:
            print(f'✓ Threshold found: {threshold_duration:.1f}s (score fell to {threshold_score:.4f})')
        else:
            print(f'✗ No threshold found (anomaly score never dropped below {default_threshold:.4f})')
        
        return result
    
    def _recalculate_duration_features(self, features, duration):
        """
        Recalculate features that directly depend on duration_seconds.
        
        Duration-dependent fields (direct):
        - duration_seconds: The duration itself
        - gastro_x_duration: has_gastro_issue * duration_seconds
        - report_minus_duration: self_reported_max_seconds - duration_seconds
        - duration_to_report_ratio: duration_seconds / self_reported_max_seconds
        
        Note: 7-day rolling features (mean_/max_/min_/std_duration_7d) should NOT
        be recalculated within a single request (they depend on historical data).
        
        Args:
            features: pd.Series with patient features
            duration: Duration in seconds to use
        
        Returns:
            pd.Series: Updated features
        """
        features = features.copy()
        
        # Update duration_seconds
        if 'duration_seconds' in features.index:
            features['duration_seconds'] = float(duration)
        
        # Update gastro_x_duration
        if 'gastro_x_duration' in features.index and 'has_gastro_issue' in features.index:
            features['gastro_x_duration'] = int(features['has_gastro_issue']) * float(duration)
        
        # Update report_minus_duration
        if 'report_minus_duration' in features.index and 'self_reported_max_seconds' in features.index:
            if pd.notna(features['self_reported_max_seconds']):
                features['report_minus_duration'] = float(features['self_reported_max_seconds']) - float(duration)
            else:
                features['report_minus_duration'] = np.nan
        
        # Update duration_to_report_ratio
        if 'duration_to_report_ratio' in features.index and 'self_reported_max_seconds' in features.index:
            if pd.notna(features['self_reported_max_seconds']) and float(features['self_reported_max_seconds']) > 0:
                features['duration_to_report_ratio'] = float(duration) / float(features['self_reported_max_seconds'])
            else:
                features['duration_to_report_ratio'] = np.nan
        
        return features


# Global predictor instance (lazy initialization)
_predictor_instance = None


def get_predictor(config=None, artifact_name=None):
    """
    Get or create the global predictor instance.
    
    Args:
        config: Configuration dict (loaded from YAML if None)
        artifact_name: Name of artifact to load (uses config default if None)
    
    Returns:
        AnomalyPredictor: Predictor instance
    """
    global _predictor_instance
    
    if _predictor_instance is None:
        _predictor_instance = AnomalyPredictor(config, artifact_name)
    
    return _predictor_instance


# Convenience functions
def predict_score(features_row, config=None):
    """
    Quick score prediction for a single feature row.
    
    Args:
        features_row: pd.Series with features
        config: Configuration dict (optional)
    
    Returns:
        float: Anomaly score
    """
    predictor = get_predictor(config)
    return predictor.predict_score(features_row.to_frame().T)[0]


def compute_patient_threshold(features_row, config=None):
    """
    Quick threshold search for a patient.
    
    Args:
        features_row: pd.Series with patient's base features
        config: Configuration dict (optional)
    
    Returns:
        dict: Threshold search results
    """
    predictor = get_predictor(config)
    return predictor.compute_threshold_for_patient(features_row)
