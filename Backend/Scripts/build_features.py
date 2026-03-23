import sqlite3
import pandas as pd
import numpy as np
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, '..'))
DB_FILE = os.path.join(backend_dir, 'hospital_iot.db')

WINDOW_DAYS = 7


def create_features_table(cursor):
    cursor.execute("DROP TABLE IF EXISTS Toilet_Log_Features")
    cursor.execute("""
    CREATE TABLE Toilet_Log_Features (
        feature_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id                       INTEGER UNIQUE,
        patient_id                   TEXT,

        -- Log-level temporal features
        duration_seconds             INTEGER,
        time_of_day_id               INTEGER,
        hour_of_day                  INTEGER,
        day_of_week                  INTEGER,
        is_weekend                   INTEGER,
        time_since_last_log_minutes  REAL,
        is_accident                  INTEGER,

        -- Aggregated 7-day rolling window features
        mean_duration_7d             REAL,
        max_duration_7d              REAL,
        min_duration_7d              REAL,
        std_duration_7d              REAL,
        log_count_7d                 INTEGER,
        tod_deep_night_count_7d      INTEGER,
        tod_early_morning_count_7d   INTEGER,
        tod_late_morning_count_7d    INTEGER,
        tod_afternoon_count_7d       INTEGER,
        tod_evening_count_7d         INTEGER,
        accident_ratio_7d            REAL,

        -- Interaction features
        age_x_mobility               REAL,
        gastro_x_duration            REAL,

        -- Denormalized static patient features
        age                          INTEGER,
        gender                       TEXT,
        mobility_level               INTEGER,
        has_gastro_issue             INTEGER,
        has_uro_issue                INTEGER,
        self_reported_max_seconds    INTEGER,
        report_minus_duration        REAL,
        duration_to_report_ratio     REAL,

        created_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(log_id)      REFERENCES Toilet_Logs(log_id),
        FOREIGN KEY(patient_id)  REFERENCES Patients(patient_id)
    )""")


def compute_window_features(entry_arr, dur_arr, acc_arr, tod_arr, current_idx, window_td):
    t = entry_arr[current_idx]
    mask = (entry_arr >= t - window_td) & (entry_arr < t)
    past_dur = dur_arr[mask]
    past_acc = acc_arr[mask]
    past_tod = tod_arr[mask]
    n = int(np.sum(mask))

    if n > 0:
        mean_d = float(np.mean(past_dur))
        max_d  = float(np.max(past_dur))
        min_d  = float(np.min(past_dur))
        std_d  = float(np.std(past_dur)) if n > 1 else 0.0
        acc_ratio = float(np.sum(past_acc) / n)
    else:
        mean_d = max_d = min_d = std_d = acc_ratio = None

    tod_counts = {v: int(np.sum(past_tod == v)) for v in [1, 2, 3, 4, 5]}

    return mean_d, max_d, min_d, std_d, n, tod_counts, acc_ratio


def build_features():
    with sqlite3.connect(DB_FILE) as conn:
        query = """
        SELECT
            tl.log_id,
            tl.patient_id,
            tl.entry_time,
            tl.duration_seconds,
            tl.time_of_day_id,
            tl.is_accident,
            p.age,
            p.gender,
            p.mobility_level,
            p.has_gastro_issue,
            p.has_uro_issue,
            p.self_reported_max_seconds
        FROM Toilet_Logs tl
        JOIN Patients p ON tl.patient_id = p.patient_id
        WHERE tl.exit_time IS NOT NULL
        ORDER BY tl.patient_id, tl.entry_time
        """
        df = pd.read_sql_query(query, conn)

    if df.empty:
        print("No completed logs found. Run data_generator.py first.")
        return

    print(f"Loaded {len(df)} completed log records from DB.")

    df['entry_dt'] = pd.to_datetime(df['entry_time'])
    df = df.sort_values(['patient_id', 'entry_dt']).reset_index(drop=True)

    df['hour_of_day'] = df['entry_dt'].dt.hour
    df['day_of_week'] = df['entry_dt'].dt.dayofweek
    df['is_weekend']  = (df['day_of_week'] >= 5).astype(int)

    df['prev_entry_dt'] = df.groupby('patient_id')['entry_dt'].shift(1)
    df['time_since_last_log_minutes'] = (
        (df['entry_dt'] - df['prev_entry_dt']).dt.total_seconds() / 60.0
    )

    window_td = np.timedelta64(WINDOW_DAYS, 'D')
    rows = []

    for patient_id, grp in df.groupby('patient_id'):
        grp = grp.sort_values('entry_dt').reset_index(drop=True)

        entry_arr = grp['entry_dt'].values.astype('datetime64[ns]')
        dur_arr   = grp['duration_seconds'].values.astype(float)
        acc_arr   = grp['is_accident'].values.astype(float)
        tod_arr   = grp['time_of_day_id'].values.astype(float)

        for i, row in grp.iterrows():
            mean_d, max_d, min_d, std_d, n, tod_counts, acc_ratio = compute_window_features(
                entry_arr, dur_arr, acc_arr, tod_arr, i, window_td
            )

            rows.append({
                'log_id':                       int(row['log_id']),
                'patient_id':                   row['patient_id'],
                'duration_seconds':             int(row['duration_seconds']),
                'time_of_day_id':               int(row['time_of_day_id']),
                'hour_of_day':                  int(row['hour_of_day']),
                'day_of_week':                  int(row['day_of_week']),
                'is_weekend':                   int(row['is_weekend']),
                'time_since_last_log_minutes':  row['time_since_last_log_minutes'],
                'is_accident':                  int(row['is_accident']),
                'mean_duration_7d':             mean_d,
                'max_duration_7d':              max_d,
                'min_duration_7d':              min_d,
                'std_duration_7d':              std_d,
                'log_count_7d':                 n,
                'tod_deep_night_count_7d':      tod_counts[1],
                'tod_early_morning_count_7d':   tod_counts[2],
                'tod_late_morning_count_7d':    tod_counts[3],
                'tod_afternoon_count_7d':       tod_counts[4],
                'tod_evening_count_7d':         tod_counts[5],
                'accident_ratio_7d':            acc_ratio,
                'age_x_mobility':               int(row['age']) * int(row['mobility_level']),
                'gastro_x_duration':            int(row['has_gastro_issue']) * int(row['duration_seconds']),
                'age':                          int(row['age']),
                'gender':                       row['gender'],
                'mobility_level':               int(row['mobility_level']),
                'has_gastro_issue':             int(row['has_gastro_issue']),
                'has_uro_issue':                int(row['has_uro_issue']),
                'self_reported_max_seconds':    int(row['self_reported_max_seconds']) if pd.notna(row['self_reported_max_seconds']) else np.nan,
                'report_minus_duration':        (float(row['self_reported_max_seconds']) - float(row['duration_seconds'])) if pd.notna(row['self_reported_max_seconds']) else np.nan,
                'duration_to_report_ratio':     (float(row['duration_seconds']) / float(row['self_reported_max_seconds'])) if pd.notna(row['self_reported_max_seconds']) and float(row['self_reported_max_seconds']) > 0 else np.nan,
            })

    features_df = pd.DataFrame(rows)

    # Drop cold-start rows that have no 7-day history at all.
    before = len(features_df)
    features_df = features_df[features_df['log_count_7d'] > 0].reset_index(drop=True)
    dropped = before - len(features_df)
    print(f"Dropped {dropped} cold-start rows (log_count_7d == 0). Remaining: {len(features_df)}")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        create_features_table(cursor)
        conn.commit()
        features_df.to_sql('Toilet_Log_Features', conn, if_exists='append', index=False)

    print(f"Feature engineering complete.")
    print(f"  Rows written     : {len(features_df)}")
    print(f"  Columns produced : {len(features_df.columns)}")
    print(f"  Columns          : {list(features_df.columns)}")
    print(f"  Sample (first row):\n{features_df.iloc[0].to_string()}")


if __name__ == "__main__":
    build_features()
