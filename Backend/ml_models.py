"""
ml_models.py
Model builder functions that read parameters from config.yaml.
Supports Isolation Forest, One-Class SVM, and optional Autoencoder.
"""

from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from ml_preprocessing import load_config


def build_isolation_forest(config=None):
    """
    Build Isolation Forest anomaly detector from config parameters.
    
    Args:
        config: Configuration dict (loaded from YAML if None)
    
    Returns:
        sklearn.ensemble.IsolationForest: Initialized model
    """
    if config is None:
        config = load_config()
    
    params = config['models']['isolation_forest']
    
    model = IsolationForest(
        contamination=params['contamination'],
        max_samples=params['max_samples'],
        random_state=params['random_state'],
        n_estimators=params.get('n_estimators', 100),
        n_jobs=1  # Prevent multiprocessing crash on Windows
    )
    
    return model


def build_one_class_svm(config=None):
    """
    Build One-Class SVM anomaly detector from config parameters.
    
    Args:
        config: Configuration dict (loaded from YAML if None)
    
    Returns:
        sklearn.svm.OneClassSVM: Initialized model
    """
    if config is None:
        config = load_config()
    
    params = config['models']['one_class_svm']
    
    model = OneClassSVM(
        nu=params['nu'],
        kernel=params['kernel'],
        gamma=params['gamma'],
    )
    
    return model


from sklearn.base import BaseEstimator

class AutoencoderWrapper(BaseEstimator):
    """Scikit-learn compatible wrapper for Keras Autoencoder."""
    def __init__(self, config=None):
        if config is None:
            config = load_config()
        self.config = config
        self.params = config['models']['simple_autoencoder']
        self.model = None

    def fit(self, X, y=None):
        import tensorflow as tf
        from tensorflow.keras import Sequential, layers
        
        input_dim = X.shape[1]
        encoding_dim = self.params.get('encoding_dim', 16)
        
        self.model = Sequential([
            layers.Input(shape=(input_dim,)),
            layers.Dense(32),
            layers.BatchNormalization(),
            layers.LeakyReLU(alpha=0.1),
            layers.Dropout(0.2),
            layers.Dense(16),
            layers.BatchNormalization(),
            layers.LeakyReLU(alpha=0.1),
            layers.Dense(8, activation='relu', name='encoding'),
            layers.Dense(16),
            layers.BatchNormalization(),
            layers.LeakyReLU(alpha=0.1),
            layers.Dropout(0.2),
            layers.Dense(32),
            layers.BatchNormalization(),
            layers.LeakyReLU(alpha=0.1),
            layers.Dense(input_dim, activation='linear')
        ])
        self.model.compile(optimizer='adam', loss='mse')
        
        epochs = self.params.get('epochs', 50)
        batch_size = self.params.get('batch_size', 16)
        
        # Fit the model
        self.model.fit(
            X, X,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.1,
            verbose=0
        )
        return self

    def decision_function(self, X):
        import numpy as np
        # Predictions are the reconstructed inputs
        reconstructions = self.model.predict(X, verbose=0)
        # Anomaly score is the Mean Squared Error (MSE)
        mse = np.mean(np.square(X - reconstructions), axis=1)
        return mse

    def predict(self, X):
        return self.decision_function(X)

def build_autoencoder(config=None):
    """
    Build simple Autoencoder for anomaly detection.
    OPTIONAL: Requires tensorflow/keras to be installed.
    """
    try:
        import tensorflow as tf
    except ImportError:
        raise ImportError(
            "Autoencoder requires tensorflow. Install with: pip install tensorflow"
        )
    return AutoencoderWrapper(config)


class XGBoostWrapper(BaseEstimator):
    """Scikit-learn compatible wrapper for XGBoost Classifier used for anomaly detection."""
    def __init__(self, config=None):
        if config is None:
            config = load_config()
        self.config = config
        self.params = config['models'].get('xgboost', {})
        self.model = None

    def fit(self, X, y=None):
        import xgboost as xgb
        if y is None:
            raise ValueError("y cannot be None for XGBoost classification")
        
        self.model = xgb.XGBClassifier(
            n_estimators=self.params.get('n_estimators', 150),
            max_depth=self.params.get('max_depth', 4),
            learning_rate=self.params.get('learning_rate', 0.1),
            scale_pos_weight=self.params.get('scale_pos_weight', 40),
            random_state=self.params.get('random_state', 42),
            eval_metric='logloss'
        )
        self.model.fit(X, y)
        return self

    def decision_function(self, X):
        # We output the predicted probability for the positive class (1 = accident)
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X):
        return self.decision_function(X)

def build_xgboost(config=None):
    """Build XGBoost classification model."""
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError(
            "XGBoost requires xgboost. Install with: pip install xgboost"
        )
    return XGBoostWrapper(config)


def get_model_builder(model_name, config=None):
    """
    Get the builder function for a named model.
    
    Args:
        model_name: Name of model ('isolation_forest', 'one_class_svm', 'simple_autoencoder')
        config: Configuration dict (loaded from YAML if None)
    
    Returns:
        callable: Model builder function
    """
    builders = {
        'isolation_forest': build_isolation_forest,
        'one_class_svm': build_one_class_svm,
        'simple_autoencoder': build_autoencoder,
        'xgboost': build_xgboost,
    }
    
    if model_name not in builders:
        raise ValueError(
            f"Unknown model: {model_name}. Choose from: {list(builders.keys())}"
        )
    
    builder = builders[model_name]
    return lambda: builder(config)


def build_primary_model(config=None):
    """
    Build the primary model specified in config['models']['primary'].
    
    Args:
        config: Configuration dict (loaded from YAML if None)
    
    Returns:
        Model instance (subclass of sklearn base estimator)
    """
    if config is None:
        config = load_config()
    
    primary_model = config['models']['primary']
    builder = get_model_builder(primary_model, config)
    return builder()
