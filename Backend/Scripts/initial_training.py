"""
initial_training.py
Script to train the anomaly detection model from scratch.
Reads from Toilet_Log_Features table, preprocesses, trains, and saves artifact.
"""

import os
import sys
import sqlite3
import numpy as np
import pandas as pd

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
from pathlib import Path
from sklearn.model_selection import StratifiedKFold

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_preprocessing import load_config, create_preprocessor
from ml_models import build_primary_model
from ml_artifacts import ModelArtifact, save_model_artifact


def compute_model_scores(model, X_processed):
    """
    Compute model scores using a consistent API.

    We prefer decision_function because many anomaly models define
    the outlier boundary around 0 in that space.
    """
    if hasattr(model, 'decision_function'):
        return model.decision_function(X_processed)
    if hasattr(model, 'score_samples'):
        return model.score_samples(X_processed)
    raise AttributeError("Model does not support decision_function or score_samples")


def calibrate_threshold_with_cv(X_train, y_train, config, model_name=None):
    """
    Calibrate threshold using StratifiedKFold and validation label ratio.
    """
    if model_name is None:
        model_name = config['models']['primary']
    
    from ml_models import get_model_builder
    builder = get_model_builder(model_name, config)
    n_splits = int(config.get('training', {}).get('cv_splits', 5))
    fallback_pct = float(config['threshold_search'].get('threshold_percentile', 5))

    X_train_cv = X_train.reset_index(drop=True)
    y_train_cv = y_train.reset_index(drop=True)

    # --- Cross-validation ---
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    fold_thresholds = []
    fold_metrics = []

    # Check if we actually have enough anomalies to split
    anomaly_counts = y_train_cv.sum()
    if anomaly_counts < n_splits:
        print(f"Warning: Only {anomaly_counts} anomalies found, fewer than {n_splits} splits. Reducing splits.")
        n_splits = max(2, int(anomaly_counts))
        if n_splits < 2:
             print("Too few anomalies for StratifiedKFold. Disabling shuffle splits.")
             # Fallback to no-split or simple fold if absolutely needed, though Stratified needs >=2
             # We just let it fail gracefully or adjust
             
    try:
        splits = list(skf.split(X_train_cv, y_train_cv))
    except ValueError:
        # If there are 0 anomalies or too few components, fallback
        print("Fallback to normal KFold due to insufficient class distribution")
        from sklearn.model_selection import KFold
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
        splits = list(kf.split(X_train_cv))

    for fold_idx, (tr_idx, val_idx) in enumerate(splits, 1):
        X_tr = X_train_cv.iloc[tr_idx]
        y_tr = y_train_cv.iloc[tr_idx]
        X_val = X_train_cv.iloc[val_idx]
        y_val = y_train_cv.iloc[val_idx]

        preprocessor, _, _ = create_preprocessor(X_tr, config)
        X_tr_p = preprocessor.fit_transform(X_tr)
        X_val_p = preprocessor.transform(X_val)

        model = builder()
        model.fit(X_tr_p, y_tr)

        val_scores = compute_model_scores(model, X_val_p)
        
        # Determine score interpretation
        # Scikit-learn standard models return lower scores for anomalies
        # But Autoencoder and XGBoost return higher scores for anomalies
        is_higher_anomalous = (
            model_name in ['simple_autoencoder', 'xgboost']
        )

        anomaly_ratio = float((y_val == 1).mean())
        if anomaly_ratio > 0:
            if is_higher_anomalous:
                # Anomalies are at the top 'anomaly_ratio' fraction of scores
                percentile = 100.0 * (1.0 - anomaly_ratio)
            else:
                # Anomalies are at the bottom 'anomaly_ratio' fraction of scores
                percentile = anomaly_ratio * 100.0
        else:
            if is_higher_anomalous:
                percentile = 100.0 - fallback_pct
            else:
                percentile = fallback_pct

        fold_threshold = float(np.percentile(val_scores, percentile))
        fold_thresholds.append(fold_threshold)
        fold_metrics.append({
            'fold': fold_idx,
            'train_size': int(len(X_tr)),
            'val_size': int(len(X_val)),
            'anomaly_ratio': anomaly_ratio,
            'percentile_used': percentile,
            'threshold': fold_threshold,
        })

    calibrated_threshold = float(np.median(fold_thresholds))
    return calibrated_threshold, fold_metrics


def load_feature_data(config):
    """
    Load feature data from SQLite database.
    
    Args:
        config: Configuration dict
    
    Returns:
        pd.DataFrame: Feature data with all rows and columns
    """
    # Get database path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    db_path = os.path.join(backend_dir, 'hospital_iot.db')
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    table_name = config['data']['table']
    
    try:
        df = pd.read_sql_query(f'SELECT * FROM {table_name}', conn)
    finally:
        conn.close()
    
    print(f'Loaded {len(df)} rows from {table_name}')
    return df


def prepare_features(df, config, strategy='filtered'):
    """
    Prepare feature matrix X and label vector y from DataFrame.
    
    Args:
        df: DataFrame with feature data
        config: Configuration dict
        strategy: 'all', 'filtered', or 'top10'
    
    Returns:
        tuple: (X, y, feature_col_names)
    """
    label_col = config['data']['label_col']
    
    base_exclude = config['data'].get('base_exclude_cols', [])
    extra_exclude = config['data'].get('exclude_cols', [])
    top_k = config['data'].get('top_k_features', [])
    
    if strategy == 'all':
        # Every column except base excludes and label
        feature_cols = [c for c in df.columns if c not in base_exclude and c != label_col]
    elif strategy == 'top10':
        # Only the predefined top K features
        feature_cols = [c for c in df.columns if c in top_k]
    else: # 'filtered'
        # Exclude both base and extra (leakage-prone) columns
        combined_exclude = set(base_exclude + extra_exclude)
        feature_cols = [c for c in df.columns if c not in combined_exclude and c != label_col]

    X = df[feature_cols].copy()
    y = pd.to_numeric(df[label_col], errors='coerce').fillna(0).astype(int)
    
    print(f'Feature matrix: {X.shape}')
    print(f'Label distribution:\n{y.value_counts(normalize=True)}')
    
    return X, y, feature_cols


def train_test_split_stratified(X, y, train_ratio):
    """
    Split data ensuring equal distribution of anomalies in both train and test.
    This prevents all anomalies from being dumped into the test set if they 
    were generated at the end of the timeline.
    """
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=1.0 - train_ratio, stratify=y, random_state=42
    )

    print(f'Train/test split: {len(X_train)} / {len(X_test)} (ratio: {train_ratio})')
    print(f'Train anomalies:  {y_train.sum()}')
    print(f'Test anomalies:   {y_test.sum()}')
    
    return X_train, X_test, y_train, y_test


def compute_score_statistics(y_scores, data_name=''):
    """
    Compute statistics on anomaly scores.
    
    Args:
        y_scores: Array of anomaly scores
        data_name: Name for output (e.g., 'train', 'test')
    
    Returns:
        dict: Statistics dictionary
    """
    stats = {
        'mean': float(np.mean(y_scores)),
        'std': float(np.std(y_scores)),
        'min': float(np.min(y_scores)),
        'max': float(np.max(y_scores)),
        'p5': float(np.percentile(y_scores, 5)),
        'median': float(np.median(y_scores)),
        'p25': float(np.percentile(y_scores, 25)),
        'p75': float(np.percentile(y_scores, 75)),
        'p95': float(np.percentile(y_scores, 95)),
    }
    
    if data_name:
        print(f'\n{data_name} score statistics:')
        for key, val in stats.items():
            print(f'  {key:8s}: {val:8.4f}')
    
    return stats


def train_model(X_train, y_train, X_test, config, model_name=None):
    """
    Preprocess data and train anomaly detection model.

    Args:
        X_train: Training feature matrix
        X_test: Test feature matrix
        config: Configuration dict
        model_name: Optional custom model name (defaults to primary)

    Returns:
        tuple: (preprocessor, model, feature_names, numerical_cols, categorical_cols, train_metrics)
    """
    if model_name is None:
        model_name = config['models']['primary']

    print(f'\n=== Preprocessing for {model_name} ===')
    
    # Create preprocessor (fit on train data only)
    preprocessor, numerical_cols, categorical_cols = create_preprocessor(X_train, config)
    
    # Fit preprocessor on train data
    X_train_processed = preprocessor.fit_transform(X_train)
    X_test_processed = preprocessor.transform(X_test)
    
    print(f'Preprocessor fitted on {len(X_train)} train samples')
    print(f'Processed shape: {X_train_processed.shape}')
    print(f'Numerical cols: {len(numerical_cols)}, Categorical cols: {len(categorical_cols)}')
    
    # Get feature names after preprocessing
    feature_names = preprocessor.get_feature_names_out()
    
    print('\n=== Model Training ===')

    # Build and train model
    from ml_models import get_model_builder
    try:
        builder = get_model_builder(model_name, config)
        model = builder()
    except (ValueError, ImportError) as e:
        print(f"Skipping model {model_name}: {e}")
        return None, None, None, None, None, None, None

    model.fit(X_train_processed, y_train)

    print(f'Model trained: {model_name}')
    print('\n=== Score Analysis ===')
    
    y_train_scores = compute_model_scores(model, X_train_processed)
    y_test_scores = compute_model_scores(model, X_test_processed)

    try:
        # Threshold calibration with Stratified CV on training data only
        calibrated_threshold, cv_folds = calibrate_threshold_with_cv(X_train, y_train, config, model_name)
    except Exception as e:
        import traceback
        print("Crash in CV:", traceback.format_exc())
        calibrated_threshold, cv_folds = 0.0, []
        
    print(f'Calibrated threshold (median over folds): {calibrated_threshold:.6f}')
    
    train_stats = compute_score_statistics(y_train_scores, 'Train')
    test_stats = compute_score_statistics(y_test_scores, 'Test')
    
    # Compile metrics
    train_metrics = {
        'train_scores': train_stats,
        'test_scores': test_stats,
        'num_train_samples': len(X_train),
        'num_test_samples': len(X_test),
        'cv_calibration': cv_folds,
        'calibrated_threshold': calibrated_threshold,
    }
    
    return preprocessor, model, feature_names, numerical_cols, categorical_cols, train_metrics, calibrated_threshold


def main():
    """
    Main training pipeline.
    """
    print('=== Initial Model Training ===\n')
    
    # Load configuration
    config = load_config()
    print(f'Configuration loaded')
    print(f'  Primary model: {config["models"]["primary"]}')
    print(f'  Train ratio: {config["data"]["train_ratio"]}')
    
    # Load data
    print('\n=== Data Loading ===')
    df = load_feature_data(config)
    
    # Ensure time ordering by log_id
    df = df.sort_values('log_id').reset_index(drop=True)
    
    models_to_train = config['models'].get('train_list', [config['models']['primary']])
    strategies = ['all', 'filtered', 'top10']
    
    for strategy in strategies:
        print(f"\n{'#'*60}")
        print(f"### RUNNING EXPERIMENT STRATEGY: {strategy.upper()} ###")
        print(f"{'#'*60}")
        
        # Prepare features for the current strategy
        X, y, feature_cols = prepare_features(df, config, strategy=strategy)
        
        # Stratified train/test split
        print(f'\n=== Train/Test Split ({strategy}) ===')
        train_ratio = config['data']['train_ratio']
        X_train, X_test, y_train, y_test = train_test_split_stratified(X, y, train_ratio)
        
        for model_base_name in models_to_train:
            # We add suffix to model name to identify the strategy
            model_name_with_strategy = f"{model_base_name}_{strategy}"
            
            print(f"\n{'='*50}\nStarting pipeline for model: {model_name_with_strategy}\n{'='*50}")
            # Train model. We pass the base model name to the builder but save it as the strategy model.
            try:
                # We need to pass model_base_name so get_model_builder creates the correct type
                result = train_model(
                    X_train, y_train, X_test, config, model_name=model_base_name
                )
            except Exception as e:
                print(f"Error training {model_name_with_strategy}: {e}")
                continue
                
            if result is None or result[1] is None:
                continue
                
            preprocessor, model, feature_names, numerical_cols, categorical_cols, train_metrics, calibrated_threshold = result

            # Create artifact
            print('\n=== Creating Artifact ===')
            artifact = ModelArtifact(
                preprocessor=preprocessor,
                model=model,
                model_name=model_name_with_strategy,
                feature_names=feature_names,
                numerical_cols=numerical_cols,
                categorical_cols=categorical_cols,
                config=config,
                train_metrics=train_metrics,
                threshold=calibrated_threshold,
            )
            
            # Save artifact
            print('\n=== Saving Artifact ===')
            artifact_dir = save_model_artifact(artifact, config, artifact_name=f"anomaly_model_{model_name_with_strategy}")
            
            print(f'\n[OK] Training complete for {model_name_with_strategy}!')
            print(f'   Artifact saved to: {artifact_dir}')

if __name__ == '__main__':
    main()
