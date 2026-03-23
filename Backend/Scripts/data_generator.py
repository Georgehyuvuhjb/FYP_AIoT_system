import sqlite3
import random
from datetime import datetime, timedelta
from faker import Faker
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, '..'))
DB_FILE = os.path.join(backend_dir, 'hospital_iot.db')

sys.path.append(backend_dir)
import db_manager

fake = Faker()

# ==========================================
# Configuration
# ==========================================
NUM_PATIENTS = 100
DAYS_OF_HISTORY = 30
YOUR_REAL_RFID_UID = "4347A329"
ANOMALIES_PER_PATIENT = 5

# ==========================================
# 1. Clear Old Data
# ==========================================
def clear_database(cursor):
    print("🧹 Dropping old tables to apply new schema...")
    cursor.execute("DROP TABLE IF EXISTS Toilet_Logs")
    cursor.execute("DROP TABLE IF EXISTS Card_Assignments")
    cursor.execute("DROP TABLE IF EXISTS Patients")
    cursor.execute("DROP TABLE IF EXISTS TimeOfDay")
    db_manager.init_db()

# ==========================================
# 2. Generate Patients & Cards
# ==========================================
def generate_patients_and_cards(cursor):
    print(f"👥 Generating {NUM_PATIENTS} patients and assigning RFID cards...")
    
    patients = []
    
    for i in range(NUM_PATIENTS):
        patient_id = f"P-{1000 + i}"
        age = random.randint(20, 90)
        gender = random.choice(['M', 'F'])
        
        # Weighted probabilities for medical conditions
        mobility_level = random.choices([0, 1, 2], weights=[60, 30, 10])[0] 
        has_gastro = random.choices([0, 1], weights=[85, 15])[0]
        has_uro = random.choices([0, 1], weights=[70, 30])[0]

        # Build patient-specific self-reported threshold with clinical factors + personal preference.
        base_seconds = 15 * 60
        age_offset = 5 * 60 if age >= 60 else 0
        age_offset += 5 * 60 if age >= 75 else 0
        mobility_offset = 5 * 60 if mobility_level == 1 else 15 * 60 if mobility_level >= 2 else 0
        medical_offset = (5 * 60 if has_gastro else 0) + (5 * 60 if has_uro else 0)
        personal_style = random.randint(0, 20) * 60
        self_reported_max_seconds = base_seconds + age_offset + mobility_offset + medical_offset + personal_style

        cursor.execute('''
        INSERT INTO Patients (
            patient_id, age, gender, mobility_level,
            has_gastro_issue, has_uro_issue, self_reported_max_seconds
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, age, gender, mobility_level, has_gastro, has_uro, self_reported_max_seconds))
        
        if i == 0:
            card_uid = YOUR_REAL_RFID_UID
        else:
            card_uid = fake.hexify(text='^^^^^^^^', upper=True)
            
        cursor.execute('''
        INSERT INTO Card_Assignments (card_uid, patient_id, is_active)
        VALUES (?, ?, 1)
        ''', (card_uid, patient_id))

        patients.append({
            'patient_id': patient_id,
            'age': age,
            'mobility': mobility_level,
            'has_gastro': has_gastro,
            'has_uro': has_uro,
            'self_reported_max_seconds': self_reported_max_seconds,
        })
        
    return patients

# ==========================================
# 3. Generate Historical Toilet Logs
# ==========================================
def generate_toilet_logs(cursor, patients):
    print(f"Generating {DAYS_OF_HISTORY} days of historical toilet logs (Normal Data)...")
    
    start_date = datetime.now() - timedelta(days=DAYS_OF_HISTORY)
    
    time_of_day_mapping = {
        'Deep Night': 300,
        'Early Morning': 200,
        'Late Morning': 150,
        'Afternoon': 150,
        'Evening': 180
    }

    total_logs = 0
    
    for day in range(DAYS_OF_HISTORY):
        current_date = start_date + timedelta(days=day)
        
        for p in patients:
            visits_today = random.randint(4, 8)
            
            for _ in range(visits_today):

                hour = random.choices(
                    [random.randint(0, 5), random.randint(6, 8), random.randint(9, 11), random.randint(12, 17), random.randint(18, 23)],
                    weights=[15, 30, 20, 20, 15]
                )[0]
                minute = random.randint(0, 59)
                
                entry_dt = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                entry_iso = entry_dt.isoformat() + "+08:00"

                if 0 <= hour < 6: tod = 'Deep Night'
                elif 6 <= hour < 9: tod = 'Early Morning'
                elif 9 <= hour < 12: tod = 'Late Morning'
                elif 12 <= hour < 18: tod = 'Afternoon'
                else: tod = 'Evening'

                # --- Calculate Risk-based Upper Bound ---
                age_mod = 0.3 * ((max(20, min(90, p['age'])) - 20) / 70.0)
                mob_mod = 0.1 if p['mobility'] == 1 else (0.2 if p['mobility'] >= 2 else 0)
                morb_mod = 0.15 if (p['has_gastro'] or p['has_uro']) else 0
                
                risk_score = age_mod + mob_mod + morb_mod
                upper_bound = min(1.5, 0.75 + risk_score)

                base_time = time_of_day_mapping[tod]
                multiplier = random.uniform(0.15, upper_bound)
                preferred_duration = p['self_reported_max_seconds'] * multiplier

                blended_mean = 0.6 * preferred_duration + 0.4 * base_time
                duration = int(random.gauss(blended_mean, 40))
                if duration < 0:
                    duration = 0
                
                tod_mapping_id = {
                    'Deep Night': 1, 'Early Morning': 2,
                    'Late Morning': 3, 'Afternoon': 4, 'Evening': 5
                }
                tod_id = tod_mapping_id[tod]

                exit_dt = entry_dt + timedelta(seconds=duration)
                exit_iso = exit_dt.isoformat() + "+08:00"

                cursor.execute('''
                INSERT INTO Toilet_Logs (patient_id, entry_time, exit_time, duration_seconds, time_of_day_id, is_accident)
                VALUES (?, ?, ?, ?, ?, 0)
                ''', (p['patient_id'], entry_iso, exit_iso, duration, tod_id))
                
                total_logs += 1

    print(f"Created {total_logs} historical logs successfully.")


def _generate_single_anomaly(cursor, patient, now):
    """Generate a single anomaly log."""
    day_offset = random.randint(1, DAYS_OF_HISTORY)
    
    # --- Anomaly is more likely in Deep Night (40%) and Early Morning (30%) ---
    hour = random.choices(
        [
            random.randint(0, 5),   # Deep Night
            random.randint(6, 8),   # Early Morning
            random.randint(9, 11),  # Late Morning
            random.randint(12, 17), # Afternoon
            random.randint(18, 23)  # Evening
        ],
        weights=[40, 30, 10, 10, 10]
    )[0]
    minute = random.randint(0, 59)

    entry_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(days=day_offset)
    
    # --- 10% chance of Non-timeout accident (e.g. falling shortly after entering) ---
    # --- 90% chance of Timeout accident ---
    if random.random() < 0.10:
        multiplier = random.uniform(0.1, 0.9)
    else:
        multiplier = random.uniform(1.1, 1.8)
        
    duration = int(max(1, patient['self_reported_max_seconds'] * multiplier + random.gauss(0, 30)))
    exit_dt = entry_dt + timedelta(seconds=duration)

    entry_iso = entry_dt.isoformat() + "+08:00"
    exit_iso = exit_dt.isoformat() + "+08:00"

    if 0 <= hour < 6:
        tod_id = 1
    elif 6 <= hour < 9:
        tod_id = 2
    elif 9 <= hour < 12:
        tod_id = 3
    elif 12 <= hour < 18:
        tod_id = 4
    else:
        tod_id = 5

    cursor.execute(
        '''
        INSERT INTO Toilet_Logs (patient_id, entry_time, exit_time, duration_seconds, time_of_day_id, is_accident)
        VALUES (?, ?, ?, ?, ?, 1)
        ''',
        (patient['patient_id'], entry_iso, exit_iso, duration, tod_id),
    )


def generate_anomaly_logs(cursor, patients):
    """
    Generate anomaly logs mixed with different severities and occurrences.
    Most anomalies are just somewhat overtime (1.1x ~ 1.8x), 
    while a small fraction (10%) happens quickly (0.1x ~ 0.9x).
    """
    TOTAL_PER_PATIENT = 5

    print(f"Generating anomaly logs ({TOTAL_PER_PATIENT} per patient)...")
    now = datetime.now()
    total_anomalies = 0

    for p in patients:
        for _ in range(TOTAL_PER_PATIENT):
            _generate_single_anomaly(cursor, p, now)
            total_anomalies += 1

    print(f"Created {total_anomalies} anomaly logs successfully.")

# ==========================================
# Main Execution
# ==========================================
if __name__ == "__main__":
 

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        clear_database(cursor)
        patients_data = generate_patients_and_cards(cursor)
        generate_toilet_logs(cursor, patients_data)
        generate_anomaly_logs(cursor, patients_data)
        
        conn.commit()
    
    print("\nAll Mock Data Generated Successfully! Open Database Client to check the records.")
