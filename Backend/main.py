import json
import ssl
import paho.mqtt.client as mqtt
import db_manager
from dotenv import load_dotenv
import os

# Import AI predictor for dynamic threshold
try:
    from ai_predictor import get_predictor, compute_patient_threshold
    AI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import AI predictor: {e}")
    AI_AVAILABLE = False

# ==========================================
# Configuration
# ==========================================
load_dotenv()


MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

TOPIC_RFID = "Hospital/Room/1/01/Toilet/RFID"
TOPIC_THRESHOLD = "Hospital/Room/1/01/Toilet/Threshold"

# Global predictor (lazy initialized when needed)
_predictor = None

def get_or_init_predictor():
    """Lazy initialization of AI predictor."""
    global _predictor
    if _predictor is None and AI_AVAILABLE:
        try:
            _predictor = get_predictor()
        except Exception as e:
            print(f"Warning: Failed to initialize AI predictor: {e}")
    return _predictor

# ==========================================
# MQTT Callbacks
# ==========================================
def on_connect(client, userdata, flags, reason_code, properties):
    """Callback for when the client connects to the broker."""
    if reason_code == 0:
        print("Connected to HiveMQ Cloud successfully.")
        client.subscribe(TOPIC_RFID)
        print(f"Subscribed to: {TOPIC_RFID}")
    else:
        print(f"Connection failed with reason code: {reason_code}")

def compute_dynamic_threshold(patient_id):
    """
    Compute dynamic threshold for a patient using AI model.
    Falls back to default if AI not available.
    
    Args:
        patient_id: Patient ID to compute threshold for
    
    Returns:
        int: Recommended threshold in seconds
    """
    if not AI_AVAILABLE:
        print(f"AI not available, using default threshold: 1200s")
        return 1200
    
    try:
        # Get predictor
        predictor = get_or_init_predictor()
        if predictor is None:
            print(f"Predictor initialization failed, using default threshold: 1200s")
            return 1200
        
        # Get latest features for patient
        features = db_manager.get_patient_latest_features(patient_id)
        if features is None:
            print(f"No features found for {patient_id}, using default threshold: 1200s")
            return 1200
        
        # Compute patient-specific threshold via duration sweep
        result = predictor.compute_threshold_for_patient(features)
        
        threshold_duration = result.get('threshold_duration')
        if threshold_duration is not None:
            print(f"✓ AI computed threshold for {patient_id}: {threshold_duration:.1f}s")
            return int(threshold_duration)
        else:
            print(f"✗ AI threshold search inconclusive for {patient_id}, using default: 1200s")
            return 1200
            
    except Exception as e:
        print(f"Error computing AI threshold: {e}")
        print(f"Falling back to default threshold: 1200s")
        return 1200

def on_message(client, userdata, msg):
    """Callback for when a PUBLISH message is received from the server."""
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        uid = payload.get("uid")
        status = payload.get("status")
        timestamp = payload.get("timestamp")

        if not all([uid, status, timestamp]):
            return

        if status == "IN":
            # 1. Log to DB
            patient_id, time_of_day = db_manager.log_entry(uid, timestamp)
            
            # 2. Call AI Model to predict patient-specific threshold
            predicted_threshold = compute_dynamic_threshold(patient_id)
            print(f"Threshold for {patient_id}: {predicted_threshold}s")
            
            # 3. Send dynamic threshold back to ESP32
            response_payload = json.dumps({"threshold": predicted_threshold})
            client.publish(TOPIC_THRESHOLD, response_payload)
            print(f"Sent threshold {predicted_threshold}s to ESP32.")

        elif status == "OUT":
            db_manager.log_exit(uid, timestamp)

        elif status == "ACCIDENT":
            print("\nALARM: ACCIDENT DETECTED IN TOILET! 🚨🚨🚨\n")
            db_manager.mark_accident(uid, timestamp)

    except json.JSONDecodeError:
        print("Failed to parse JSON payload.")
    except Exception as e:
        print(f"Error processing message: {e}")


# ==========================================
# Main Execution
# ==========================================
if __name__ == "__main__":
    print("Initializing Database...")
    db_manager.init_db()

    # Setup MQTT Client (v2 API)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Python_Backend")
    
    # Configure TLS for secure connection
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Assign callbacks
    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT Broker...")
    client.connect(MQTT_BROKER, MQTT_PORT)
    
    # Blocking loop to listen continuously
    client.loop_forever()

