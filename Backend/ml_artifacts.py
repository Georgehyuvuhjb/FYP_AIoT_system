"""
ml_artifacts.py
Model and preprocessor persistence layer.
Saves/loads trained models, preprocessors, and metadata.
"""

import os
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np

from ml_preprocessing import load_config, get_feature_names_after_preprocessing


class ModelArtifact:
    """
    Container for trained model, preprocessor, and metadata.
    Handles serialization and loading.
    """
    
    def __init__(
        self,
        preprocessor,
        model,
        model_name,
        feature_names,
        numerical_cols,
        categorical_cols,
        config=None,
        train_metrics=None,
        threshold=None,
    ):
        """
        Initialize model artifact.
        
        Args:
            preprocessor: Fitted ColumnTransformer
            model: Trained model (e.g., IsolationForest)
            model_name: Name of the model architecture ('isolation_forest', etc.)
            feature_names: Feature names after preprocessing
            numerical_cols: List of numerical column names
            categorical_cols: List of categorical column names
            config: Configuration dict
            train_metrics: Dict of training metrics (optional)
        """
        self.preprocessor = preprocessor
        self.model = model
        self.model_name = model_name
        self.feature_names = feature_names
        self.numerical_cols = numerical_cols
        self.categorical_cols = categorical_cols
        self.config = config or load_config()
        self.train_metrics = train_metrics or {}
        self.threshold = threshold
        
        # Metadata
        self.created_at = datetime.now().isoformat()
        self.num_features = len(feature_names)
    
    def to_dict(self):
        """
        Convert artifact metadata to dict (for JSON serialization).
        
        Returns:
            dict: Metadata (does not include model/preprocessor objects)
        """
        return {
            'model_name': self.model_name,
            'feature_names': list(self.feature_names),
            'numerical_cols': self.numerical_cols,
            'categorical_cols': self.categorical_cols,
            'num_features': self.num_features,
            'created_at': self.created_at,
            'train_metrics': self.train_metrics,
            'threshold': self.threshold,
        }
    
    @classmethod
    def from_dict(cls, data, preprocessor, model, config=None):
        """
        Reconstruct artifact from dict metadata and loaded objects.
        
        Args:
            data: Dict from JSON metadata file
            preprocessor: Loaded ColumnTransformer
            model: Loaded model
            config: Configuration dict (optional)
        
        Returns:
            ModelArtifact instance
        """
        artifact = cls(
            preprocessor=preprocessor,
            model=model,
            model_name=data['model_name'],
            feature_names=np.array(data['feature_names']),
            numerical_cols=data['numerical_cols'],
            categorical_cols=data['categorical_cols'],
            config=config,
            train_metrics=data.get('train_metrics', {}),
            threshold=data.get('threshold'),
        )
        artifact.created_at = data['created_at']
        return artifact


def save_model_artifact(artifact, config=None, artifact_name=None):
    """
    Save model artifact (preprocessor, model, metadata) to disk.
    
    Args:
        artifact: ModelArtifact instance
        config: Configuration dict (loaded from YAML if None)
        artifact_name: Custom name for artifact (uses config default if None)
    
    Returns:
        str: Path to saved artifact directory
    """
    if config is None:
        config = load_config()
    
    if artifact_name is None:
        artifact_name = config['artifacts'].get('model_name', f"anomaly_model_{config['models']['primary']}")
    
    model_dir = config['artifacts']['model_dir']
    
    # Ensure model_dir is an absolute path relative to this script
    if not os.path.isabs(model_dir):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(base_dir, model_dir)
    
    # Ensure model directory exists
    os.makedirs(model_dir, exist_ok=True)
    
    artifact_dir = os.path.join(model_dir, artifact_name)
    os.makedirs(artifact_dir, exist_ok=True)
    
    # Save preprocessor
    preprocessor_path = os.path.join(artifact_dir, 'preprocessor.joblib')
    joblib.dump(artifact.preprocessor, preprocessor_path)
    
    # Save model
    model_path = os.path.join(artifact_dir, 'model.joblib')
    joblib.dump(artifact.model, model_path)
    
    # Save metadata
    metadata_path = os.path.join(artifact_dir, 'metadata.json')
    metadata = artifact.to_dict()
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Save full config for reproducibility
    config_path = os.path.join(artifact_dir, 'config_used.yaml')
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(artifact.config, f)
    
    print(f'??Model artifact saved to: {artifact_dir}')
    print(f'  - Preprocessor: {preprocessor_path}')
    print(f'  - Model: {model_path}')
    print(f'  - Metadata: {metadata_path}')
    print(f'  - Config: {config_path}')
    
    return artifact_dir


def load_model_artifact(config=None, artifact_name=None):
    """
    Load model artifact (preprocessor, model, metadata) from disk.
    
    Args:
        config: Configuration dict (loaded from YAML if None)
        artifact_name: Custom name for artifact (uses config default if None)
    
    Returns:
        tuple: (preprocessor, model, metadata_dict)
    """
    if config is None:
        config = load_config()
    
    if artifact_name is None:
        artifact_name = config['artifacts'].get('model_name', f"anomaly_model_{config['models']['primary']}")
    
    model_dir = config['artifacts']['model_dir']
    
    # Ensure model_dir is an absolute path relative to this script
    if not os.path.isabs(model_dir):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(base_dir, model_dir)
        
    artifact_dir = os.path.join(model_dir, artifact_name)
    
    if not os.path.exists(artifact_dir):
        raise FileNotFoundError(f"Artifact directory not found: {artifact_dir}")
    
    # Load preprocessor
    preprocessor_path = os.path.join(artifact_dir, 'preprocessor.joblib')
    preprocessor = joblib.load(preprocessor_path)
    
    # Load model
    model_path = os.path.join(artifact_dir, 'model.joblib')
    model = joblib.load(model_path)
    
    # Load metadata
    metadata_path = os.path.join(artifact_dir, 'metadata.json')
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    
    print(f'??Model artifact loaded from: {artifact_dir}')
    print(f'  - Created at: {metadata["created_at"]}')
    print(f'  - Model type: {metadata["model_name"]}')
    print(f'  - Features: {metadata["num_features"]}')
    
    return preprocessor, model, metadata


def get_artifact_path(config=None, artifact_name=None):
    """
    Get the full path to an artifact directory.
    
    Args:
        config: Configuration dict (loaded from YAML if None)
        artifact_name: Custom name for artifact (uses config default if None)
    
    Returns:
        str: Full path to artifact directory
    """
    if config is None:
        config = load_config()
    
    if artifact_name is None:
        artifact_name = config['artifacts'].get('model_name', f"anomaly_model_{config['models']['primary']}")
    
    model_dir = config['artifacts']['model_dir']
    return os.path.join(model_dir, artifact_name)
