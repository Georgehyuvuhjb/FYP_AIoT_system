"""
ml_preprocessing.py
Preprocessing pipeline builder that reads configuration from config.yaml.
Handles feature column selection, datatype inference, and ColumnTransformer creation.
"""

import yaml
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def load_config(config_path=None):
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config.yaml. If None, searches in Backend/ directory.
    
    Returns:
        dict: Configuration dictionary
    """
    if config_path is None:
        # Try to find config.yaml in Backend directory
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def infer_numerical_columns(df, categorical_cols):
    """
    Infer numerical columns as all columns NOT in categorical list.
    
    Args:
        df: DataFrame with all candidate features
        categorical_cols: List of column names to treat as categorical
    
    Returns:
        list: Column names to treat as numerical
    """
    return [c for c in df.columns if c not in categorical_cols]


def create_preprocessor(df, config=None, categorical_cols=None):
    """
    Create a ColumnTransformer-based preprocessing pipeline from config.
    
    Args:
        df: Input DataFrame with features
        config: Configuration dict (loaded from YAML if None)
        categorical_cols: Override categorical columns from config (for flexibility)
    
    Returns:
        sklearn.compose.ColumnTransformer: Fitted preprocessor
    """
    if config is None:
        config = load_config()
    
    # Determine categorical columns
    if categorical_cols is None:
        categorical_cols = config['features'].get('categorical', [])
    
    # Keep only those that exist in df (guards against schema changes)
    categorical_cols = [c for c in categorical_cols if c in df.columns]
    
    # Infer numerical columns
    numerical_cols = infer_numerical_columns(df, categorical_cols)
    
    # Get preprocessing parameters from config
    num_impute = config['preprocessing']['numerical_impute_strategy']
    cat_impute = config['preprocessing']['categorical_impute_strategy']
    onehot_unknown = config['preprocessing']['onehot_handle_unknown']
    onehot_sparse = config['preprocessing']['onehot_sparse']
    
    # Build preprocessing pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            (
                'num',
                Pipeline([
                    ('imputer', SimpleImputer(strategy=num_impute)),
                    ('scaler', StandardScaler()),
                ]),
                numerical_cols,
            ),
            (
                'cat',
                Pipeline([
                    ('imputer', SimpleImputer(strategy=cat_impute)),
                    ('onehot', OneHotEncoder(
                        handle_unknown=onehot_unknown,
                        sparse_output=onehot_sparse,
                    )),
                ]),
                categorical_cols,
            ),
        ],
        remainder='drop',
    )
    
    return preprocessor, numerical_cols, categorical_cols


def get_feature_names_after_preprocessing(preprocessor):
    """
    Get feature names after preprocessing (one-hot encoding, scaling, etc.).
    
    Args:
        preprocessor: Fitted ColumnTransformer
    
    Returns:
        np.ndarray: Array of feature names after preprocessing
    """
    return preprocessor.get_feature_names_out()


def preview_preprocessor(df, preprocessor, num_samples=3, num_features=12):
    """
    Preview preprocessor output on sample data (for debugging).
    
    Args:
        df: Input DataFrame
        preprocessor: Fitted ColumnTransformer
        num_samples: Number of rows to show
        num_features: Number of columns to show
    """
    X_processed = preprocessor.transform(df.head(num_samples))
    feature_names = get_feature_names_after_preprocessing(preprocessor)
    
    preview_df = pd.DataFrame(
        X_processed,
        columns=feature_names,
    )
    
    print(f'Preprocessor preview ({num_samples} rows, {num_features} cols):')
    print(preview_df.iloc[:, :num_features])
    print(f'\nTotal features after preprocessing: {len(feature_names)}')
