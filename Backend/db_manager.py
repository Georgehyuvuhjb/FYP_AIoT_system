import sqlite3
from datetime import datetime, timedelta
import os
import random

current_dir = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(current_dir, 'hospital_iot.db')


def _to_positive_int(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer.")
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed

def _to_non_negative_int(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a non-negative integer (>= 0).")
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer (>= 0).")
    return parsed


def _to_binary_int(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be 0 or 1.")
    if parsed not in (0, 1):
        raise ValueError(f"{field_name} must be 0 or 1.")
    return parsed


def _validate_non_empty(value, field_name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return str(value).strip()


def _time_of_day_id_from_hour(hour):
    if 0 <= hour < 6:
        return 1
    if 6 <= hour < 9:
        return 2
    if 9 <= hour < 12:
        return 3
    if 12 <= hour < 18:
        return 4
    return 5


def _ensure_schema_updates(cursor):
    cursor.execute("PRAGMA table_info(Patients)")
    cols = [r[1] for r in cursor.fetchall()]
    if "self_reported_max_seconds" not in cols:
        cursor.execute("ALTER TABLE Patients ADD COLUMN self_reported_max_seconds INTEGER")

    cursor.execute("PRAGMA table_info(Toilet_Logs)")
    cols = [r[1] for r in cursor.fetchall()]
    if "time_of_day_id" not in cols:
        cursor.execute("ALTER TABLE Toilet_Logs ADD COLUMN time_of_day_id INTEGER")


def _generate_anomaly_logs(cursor, patient_id, self_reported_max_seconds, count=5):
    now = datetime.now()
    for _ in range(count):
        day_offset = random.randint(1, 30)
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)

        entry_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(days=day_offset)

        multiplier = random.uniform(2.5, 4.0)
        duration = int(max(1, self_reported_max_seconds * multiplier + random.gauss(0, 30)))
        exit_dt = entry_dt + timedelta(seconds=duration)

        entry_iso = entry_dt.isoformat() + "+08:00"
        exit_iso = exit_dt.isoformat() + "+08:00"

        cursor.execute(
            '''
            INSERT INTO Toilet_Logs (patient_id, entry_time, exit_time, duration_seconds, time_of_day_id, is_accident)
            VALUES (?, ?, ?, ?, ?, 1)
            ''',
            (patient_id, entry_iso, exit_iso, duration, _time_of_day_id_from_hour(hour)),
        )

def init_db():
    """Initialize the SQLite database and create necessary tables."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute('PRAGMA foreign_keys = ON;')

        # Table: TimeOfDay (Lookup Table)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS TimeOfDay (
            id INTEGER PRIMARY KEY,
            label TEXT UNIQUE NOT NULL
        )''')

        time_of_day_values = [
            (1, 'Deep Night'), (2, 'Early Morning'), (3, 'Late Morning'),
            (4, 'Afternoon'), (5, 'Evening')
        ]
        cursor.executemany('INSERT OR IGNORE INTO TimeOfDay (id, label) VALUES (?, ?)', time_of_day_values)

        # Table: Patients (Demographics and abstracted medical features)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Patients (
            patient_id TEXT PRIMARY KEY,
            age INTEGER,
            gender TEXT,
            mobility_level INTEGER,
            has_gastro_issue BOOLEAN,
            has_uro_issue BOOLEAN,
            self_reported_max_seconds INTEGER CHECK (self_reported_max_seconds > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Table: Card_Assignments (Mapping RFID to Patient)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Card_Assignments (
            card_uid TEXT PRIMARY KEY,
            patient_id TEXT,
            is_active BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES Patients(patient_id)
        )''')

        # Table: Toilet_Logs (Dynamic session records)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Toilet_Logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            entry_time TIMESTAMP,
            exit_time TIMESTAMP,
            duration_seconds INTEGER CHECK (duration_seconds >= 0),
            time_of_day_id INTEGER,
            is_accident BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES Patients(patient_id),
            FOREIGN KEY(time_of_day_id) REFERENCES TimeOfDay(id)
        )''')
        
        # Indexes for anomaly detection feature extraction
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_toilet_logs_patient_time ON Toilet_Logs (patient_id, entry_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_toilet_logs_duration ON Toilet_Logs (duration_seconds)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_patients_age_mobility ON Patients (age, mobility_level)')
        _ensure_schema_updates(cursor)
        

        print("DB Initialized successfully.")


def add_patient(patient_id, age, gender, mobility_level, has_gastro_issue, has_uro_issue, self_reported_max_seconds,
                auto_generate_anomalies=True, anomaly_count=5):
    patient_id = _validate_non_empty(patient_id, "patient_id")
    age = _to_positive_int(age, "age")
    gender = _validate_non_empty(gender, "gender")
    mobility_level = _to_non_negative_int(mobility_level, "mobility_level")
    if mobility_level > 2:
        raise ValueError("mobility_level must be between 0 and 2.")
    has_gastro_issue = _to_binary_int(has_gastro_issue, "has_gastro_issue")
    has_uro_issue = _to_binary_int(has_uro_issue, "has_uro_issue")
    self_reported_max_seconds = _to_positive_int(self_reported_max_seconds, "self_reported_max_seconds")
    anomaly_count = _to_positive_int(anomaly_count, "anomaly_count")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        cursor.execute("SELECT 1 FROM Patients WHERE patient_id=?", (patient_id,))
        if cursor.fetchone():
            raise ValueError(f"patient_id '{patient_id}' already exists.")

        cursor.execute(
            '''
            INSERT INTO Patients (
                patient_id, age, gender, mobility_level,
                has_gastro_issue, has_uro_issue, self_reported_max_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (patient_id, age, gender, mobility_level, has_gastro_issue, has_uro_issue, self_reported_max_seconds),
        )

        generated = 0
        if auto_generate_anomalies:
            _generate_anomaly_logs(cursor, patient_id, self_reported_max_seconds, anomaly_count)
            generated = anomaly_count

        conn.commit()
        return {"patient_id": patient_id, "anomalies_generated": generated}


def register_card(card_uid):
    """Register a new card without assigning it to any patient (is_active=0)."""
    card_uid = _validate_non_empty(card_uid, "card_uid")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Card_Assignments WHERE card_uid=?", (card_uid,))
        if cursor.fetchone():
            raise ValueError(f"card_uid '{card_uid}' already exists.")

        cursor.execute(
            "INSERT INTO Card_Assignments (card_uid, patient_id, is_active) VALUES (?, NULL, 0)",
            (card_uid,),
        )
        conn.commit()
        return {"card_uid": card_uid, "patient_id": None, "is_active": 0}


def assign_card(card_uid, patient_id):
    """Assign an inactive card to a patient and activate it.
    The card must already exist and be inactive (is_active=0).
    To reassign an active card, deactivate it first.
    """
    card_uid = _validate_non_empty(card_uid, "card_uid")
    patient_id = _validate_non_empty(patient_id, "patient_id")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        cursor.execute("SELECT is_active FROM Card_Assignments WHERE card_uid=?", (card_uid,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"card_uid '{card_uid}' not found. Register it first.")
        if row[0] == 1:
            raise ValueError(
                f"card_uid '{card_uid}' is already active. Deactivate it before reassigning."
            )

        cursor.execute("SELECT 1 FROM Patients WHERE patient_id=?", (patient_id,))
        if not cursor.fetchone():
            raise ValueError(f"patient_id '{patient_id}' does not exist.")

        cursor.execute(
            "UPDATE Card_Assignments SET patient_id=?, is_active=1, updated_at=CURRENT_TIMESTAMP WHERE card_uid=?",
            (patient_id, card_uid),
        )
        conn.commit()
        return {"card_uid": card_uid, "patient_id": patient_id, "is_active": 1}


def deactivate_card(card_uid):
    """Deactivate a card and remove its patient assignment."""
    card_uid = _validate_non_empty(card_uid, "card_uid")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM Card_Assignments WHERE card_uid=?", (card_uid,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"card_uid '{card_uid}' not found.")
        if row[0] == 0:
            raise ValueError(f"card_uid '{card_uid}' is already inactive.")

        cursor.execute(
            "UPDATE Card_Assignments SET patient_id=NULL, is_active=0, updated_at=CURRENT_TIMESTAMP WHERE card_uid=?",
            (card_uid,),
        )
        conn.commit()
        return {"card_uid": card_uid, "is_active": 0}


def generate_anomalies_for_patient(patient_id, count=5):
    patient_id = _validate_non_empty(patient_id, "patient_id")
    count = _to_positive_int(count, "count")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT self_reported_max_seconds FROM Patients WHERE patient_id=?", (patient_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"patient_id '{patient_id}' does not exist.")

        self_reported_max_seconds = row[0]
        if self_reported_max_seconds is None or int(self_reported_max_seconds) <= 0:
            raise ValueError("self_reported_max_seconds is missing or invalid for this patient.")

        _generate_anomaly_logs(cursor, patient_id, int(self_reported_max_seconds), count)
        conn.commit()
        return {"patient_id": patient_id, "anomalies_generated": count}

def get_time_of_day_info(timestamp_iso):
    """Categorize the ISO 8601 timestamp into specific times of day, returning (id, label)."""
    try:
        # Parse ISO 8601 string (e.g., 2026-03-01T23:15:00+08:00)
        dt = datetime.fromisoformat(timestamp_iso)
        hour = dt.hour
        
        if 0 <= hour < 6: return 1, 'Deep Night'
        elif 6 <= hour < 9: return 2, 'Early Morning'
        elif 9 <= hour < 12: return 3, 'Late Morning'
        elif 12 <= hour < 18: return 4, 'Afternoon'
        else: return 5, 'Evening'
    except ValueError:
        return None, 'Unknown'

def log_entry(card_uid, entry_time):
    """Log a patient's entry into the toilet."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 1. Map UID to Patient ID
        cursor.execute("SELECT patient_id FROM Card_Assignments WHERE card_uid=? AND is_active=1", (card_uid,))
        result = cursor.fetchone()
        patient_id = result[0] if result else f"Unknown_{card_uid}"
        
        # 2. Extract environmental feature
        tod_id, tod_label = get_time_of_day_info(entry_time)

        # 3. Create a new incomplete log entry
        cursor.execute('''
        INSERT INTO Toilet_Logs (patient_id, entry_time, time_of_day_id, is_accident)
        VALUES (?, ?, ?, 0)
        ''', (patient_id, entry_time, tod_id))

        
        print(f"📥 DB Log: {patient_id} entered during {tod_label}.")
        return patient_id, tod_label

def log_exit(card_uid, exit_time):
    """Log a patient's exit and calculate duration."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT patient_id FROM Card_Assignments WHERE card_uid=? AND is_active=1", (card_uid,))
        result = cursor.fetchone()
        patient_id = result[0] if result else f"Unknown_{card_uid}"

        # Find the latest open session for this patient
        cursor.execute('''
        SELECT log_id, entry_time FROM Toilet_Logs 
        WHERE patient_id=? AND exit_time IS NULL 
        ORDER BY log_id DESC LIMIT 1
        ''', (patient_id,))
        
        log = cursor.fetchone()
        if log:
            log_id, entry_time = log
            
            # Calculate duration in seconds
            entry_dt = datetime.fromisoformat(entry_time)
            exit_dt = datetime.fromisoformat(exit_time)
            duration = int((exit_dt - entry_dt).total_seconds())

            # Update the existing record
            cursor.execute('''
            UPDATE Toilet_Logs SET exit_time=?, duration_seconds=? WHERE log_id=?
            ''', (exit_time, duration, log_id))
            
            print(f"DB Log: {patient_id} exited. Total duration: {duration} seconds.")
        else:
            print(f"DB Warning: No matching entry found for {patient_id}.")


def mark_accident(card_uid, accident_time):
    """Mark the latest open session as an accident and calculate duration."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT patient_id FROM Card_Assignments WHERE card_uid=? AND is_active=1", (card_uid,))
        result = cursor.fetchone()
        patient_id = result[0] if result else f"Unknown_{card_uid}"

        cursor.execute('''
        SELECT log_id, entry_time FROM Toilet_Logs 
        WHERE patient_id=? AND exit_time IS NULL 
        ORDER BY log_id DESC LIMIT 1
        ''', (patient_id,))
        
        log = cursor.fetchone()
        if log:
            log_id, entry_time = log
            
            entry_dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
            accident_dt = datetime.fromisoformat(accident_time.replace("Z", "+00:00"))
            duration = int((accident_dt - entry_dt).total_seconds())

            cursor.execute('''
            UPDATE Toilet_Logs 
            SET is_accident=1, exit_time=?, duration_seconds=? 
            WHERE log_id=?
            ''', (accident_time, duration, log_id))
            
            conn.commit()
            print(f"DB Log: Accident flagged for {patient_id}. Duration until accident: {duration} seconds.")
        else:
            print(f"DB Warning: Accident reported but no open entry found for {patient_id}.")



def get_patient_latest_features(patient_id):
    """
    Get the latest engineered features for a patient from Toilet_Log_Features.
    Used for AI model threshold computation.
    
    Args:
        patient_id: Patient ID
    
    Returns:
        pd.Series: Feature row (if exists), or None (if no features for patient)
    """
    import pandas as pd
    
    patient_id = _validate_non_empty(patient_id, "patient_id")
    
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get latest feature row for this patient
        cursor.execute('''
        SELECT * FROM Toilet_Log_Features 
        WHERE patient_id=? 
        ORDER BY feature_id DESC 
        LIMIT 1
        ''', (patient_id,))
        
        row = cursor.fetchone()
        
        if row:
            # Convert sqlite3.Row to pandas Series
            feature_dict = dict(row)
            return pd.Series(feature_dict)
        else:
            return None


if __name__ == "__main__":
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Toilet_Logs")
        rows = cursor.fetchall()
        print(f"The database currently contains {len(rows)} records")
