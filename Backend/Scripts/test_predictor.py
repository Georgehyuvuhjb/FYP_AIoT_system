"""
test_predictor.py
Quick test of the anomaly detector and patient threshold search.
"""

import os
import sys
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from ai_predictor import AnomalyPredictor
from ml_artifacts import load_model_artifact

def print_patient_summary(row, title="Patient Data"):
    """Helper to nicely print patient data."""
    print(f"\n--- {title} ---")
    print(f"Patient ID:       {row.get('patient_id', 'Unknown')}")
    print(f"Is Accident:      {row.get('is_accident', 'Unknown')}")
    print(f"Duration (sec):   {row.get('duration_seconds', 'Unknown')}")
    print(f"Age / Mobility:   {row.get('age', '?')} / {row.get('mobility_level', '?')}")
    print(f"Gastro / Uro:     {row.get('has_gastro_issue', '?')} / {row.get('has_uro_issue', '?')}")
    print(f"7d Mean Duration: {row.get('mean_duration_7d', '?'):.1f}s")
    print(f"Self Report Max:  {row.get('self_reported_max_seconds', '?')}s")
    print("-" * 20)

def test_compare_normal_vs_anomaly():
    """Test and compare basic normal vs anomaly scores."""
    print("\n=== Test 1: Normal vs Anomaly Scoring ===")
    
    try:
        predictor = AnomalyPredictor()
        
        # Load sample data from database
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(os.path.dirname(script_dir), 'hospital_iot.db')
        
        conn = sqlite3.connect(db_path)
        # Get one normal sample
        df_normal = pd.read_sql_query(
            "SELECT * FROM Toilet_Log_Features WHERE is_accident = 0 AND patient_id NOT LIKE 'Unknown_%' LIMIT 1", conn
        )
        # Get one anomaly sample
        df_anomaly = pd.read_sql_query(
            "SELECT * FROM Toilet_Log_Features WHERE is_accident = 1 AND patient_id NOT LIKE 'Unknown_%' LIMIT 1", conn
        )
        conn.close()
        
        if len(df_normal) > 0:
            norm_row = df_normal.iloc[0]
            print_patient_summary(norm_row, "Normal Sample (is_accident=0)")
            norm_score = predictor.predict_score(norm_row.to_frame().T)[0]
            print(f">>> Predictor Score: {norm_score:.4f} (Higher is more normal)")
            
        if len(df_anomaly) > 0:
            anom_row = df_anomaly.iloc[0]
            print_patient_summary(anom_row, "Anomaly Sample (is_accident=1)")
            anom_score = predictor.predict_score(anom_row.to_frame().T)[0]
            print(f">>> Predictor Score: {anom_score:.4f} (Lower = more anomalous)")
            
        if len(df_normal) > 0 and len(df_anomaly) > 0:
            if anom_score < norm_score:
                print("\n✓ SUCCESS: Anomaly score is correctly lower than normal score!")
            else:
                print("\n⚠ WARNING: Anomaly score is not lower. Might need more training data.")
                
    except Exception as e:
        print(f'✗ Error in scoring test: {e}\n')

def test_patient_threshold_search():
    """Test patient-specific threshold search with a wider duration sweep."""
    print("\n=== Test 2: Patient Threshold Search (Config-driven sweep) ===")
    
    try:
        predictor = AnomalyPredictor()
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(os.path.dirname(script_dir), 'hospital_iot.db')
        
        conn = sqlite3.connect(db_path)
        df_sample = pd.read_sql_query(
            "SELECT * FROM Toilet_Log_Features WHERE is_accident = 0 AND patient_id NOT LIKE 'Unknown_%' LIMIT 1", conn
        )
        conn.close()
        
        if len(df_sample) == 0:
            print("No valid patient data found")
            return
        
        features = df_sample.iloc[0]
        print(f"Testing patient: {features.get('patient_id', 'Unknown')}")
        print(f"Base 7-day mean duration: {features.get('mean_duration_7d', 0):.1f}s")
        ts = predictor.config.get('threshold_search', {})
        duration_min = ts.get('duration_min', 120)
        duration_max = ts.get('duration_max', 2400)
        duration_step = ts.get('duration_step', 30)
        debounce_steps = ts.get('debounce_steps', 3)
        print(f"Sweep settings: min={duration_min}s, max={duration_max}s, step={duration_step}s, debounce={debounce_steps}")
        
        # Compute threshold using config-driven sweep settings.
        result = predictor.compute_threshold_for_patient(
            features,
            duration_range=(duration_min, duration_max),
            debounce_steps=debounce_steps
        )
        
        print(f'\nThreshold search result:')
        print(f'  Status:             {result["reason"]}')
        print(f'  Threshold duration: {result.get("threshold_duration", "Not found")} seconds')
        print(f'  Score at threshold: {result.get("threshold_score", "N/A")}')
        
    except Exception as e:
        print(f'✗ Error in threshold search: {e}\n')


def test_model_artifact():
    """Test model artifact loading."""
    print("=== Test 0: Model Artifact Loading ===\n")
    
    try:
        preprocessor, model, metadata = load_model_artifact()
        
        print(f'✓ Model artifact loaded successfully')
        print(f'  Model type: {metadata["model_name"]}')
        print(f'  Features: {metadata["num_features"]}')
        
    except Exception as e:
        print(f'✗ Error loading artifact: {e}\n')

if __name__ == '__main__':
    print('\n' + '='*60)
    print('  ANOMALY DETECTOR - COMPREHENSIVE TEST')
    print('='*60 + '\n')
    
    test_model_artifact()
    test_compare_normal_vs_anomaly()
    test_patient_threshold_search()
    
    print('\n' + '='*60)
    print('  ALL TESTS COMPLETED')
    print('='*60 + '\n')
